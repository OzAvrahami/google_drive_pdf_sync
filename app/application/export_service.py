"""Qt-independent selected-document Excel export orchestration."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from app.application.document_repository import DocumentRepository
from app.writers.excel_writer import ExportResult, export_documents


class ExportOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    NOTHING_TO_EXPORT = "nothing_to_export"


@dataclass(frozen=True, slots=True)
class ApplicationExportResult:
    requested_ids: tuple[str, ...]
    eligible_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    ineligible_ids: tuple[str, ...]
    ineligible_reasons: Mapping[str, str] = field(default_factory=dict)
    written_ids: tuple[str, ...] = ()
    already_present_ids: tuple[str, ...] = ()
    transitioned_ids: tuple[str, ...] = ()
    workbook_path: str = ""
    outcome: ExportOutcome = ExportOutcome.NOTHING_TO_EXPORT
    status_persistence_error: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "ineligible_reasons", MappingProxyType(dict(self.ineligible_reasons))
        )

    @property
    def confirmed_ids(self) -> tuple[str, ...]:
        return self.written_ids + tuple(
            value for value in self.already_present_ids if value not in self.written_ids
        )

    @property
    def exported_count(self) -> int:
        return len(self.transitioned_ids)


Writer = Callable[[list, str], ExportResult]


class ExportService:
    """Reload, classify, export, and transition only workbook-confirmed IDs."""

    def __init__(
        self,
        repository: DocumentRepository,
        output_path: str | Path,
        *,
        writer: Writer = export_documents,
    ) -> None:
        self._repository = repository
        self.output_path = str(output_path)
        self._writer = writer

    def export_selected(self, drive_file_ids: Sequence[str]) -> ApplicationExportResult:
        requested = tuple(dict.fromkeys(str(value) for value in drive_file_ids))
        eligible = []
        missing: list[str] = []
        ineligible: list[str] = []
        reasons: dict[str, str] = {}
        for document_id in requested:
            document = self._repository.get_by_drive_id(document_id)
            if document is None:
                missing.append(document_id)
                continue
            if document.status != "approved":
                ineligible.append(document_id)
                reasons[document_id] = f"status:{document.status}"
                continue
            eligible.append(document)

        if not eligible:
            return ApplicationExportResult(
                requested,
                (),
                tuple(missing),
                tuple(ineligible),
                reasons,
                workbook_path=self.output_path,
                outcome=ExportOutcome.NOTHING_TO_EXPORT,
            )

        writer_result = self._writer(eligible, self.output_path)
        eligible_ids = tuple(document.drive_file_id for document in eligible)
        eligible_set = set(eligible_ids)
        confirmed_ids = tuple(
            value for value in writer_result.confirmed_ids if value in eligible_set
        )
        updates = []
        documents_by_id = {document.drive_file_id: document for document in eligible}
        for document_id in confirmed_ids:
            updated = deepcopy(documents_by_id[document_id])
            updated.status = "exported"
            updated.exported_to_excel = True
            updates.append(updated)

        persistence_error = ""
        transitioned: tuple[str, ...] = ()
        if updates:
            try:
                self._repository.upsert_many(updates)
                transitioned = tuple(document.drive_file_id for document in updates)
            except Exception as exc:
                persistence_error = f"{type(exc).__name__}: {exc}"

        all_requested_confirmed = set(confirmed_ids) == set(requested)
        if persistence_error:
            outcome = ExportOutcome.PARTIAL
        elif transitioned and all_requested_confirmed:
            outcome = ExportOutcome.SUCCEEDED
        elif transitioned or confirmed_ids:
            outcome = ExportOutcome.PARTIAL
        else:
            outcome = ExportOutcome.FAILED
        return ApplicationExportResult(
            requested_ids=requested,
            eligible_ids=eligible_ids,
            missing_ids=tuple(missing),
            ineligible_ids=tuple(ineligible),
            ineligible_reasons=reasons,
            written_ids=writer_result.written_ids,
            already_present_ids=writer_result.already_present_ids,
            transitioned_ids=transitioned,
            workbook_path=writer_result.workbook_path,
            outcome=outcome,
            status_persistence_error=persistence_error,
        )
