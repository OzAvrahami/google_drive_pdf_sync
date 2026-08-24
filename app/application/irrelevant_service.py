"""Application orchestration for Panda's single-document irrelevant action."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from app.application.document_repository import DocumentRepository
from app.domain.workflow_policy import can_mark_irrelevant
from app.models.document import Document
from app.services.exclusion_service import (
    LocalPdfDeletionPlan,
    LocalPdfDeletionResult,
    delete_local_pdf_safely,
    record_exclusion,
    remove_exclusion,
    validate_local_pdf_deletion_target,
)


class IrrelevantReason(str, Enum):
    GENERAL = "general"
    CONFIRMED_DUPLICATE = "confirmed_duplicate"


@dataclass(frozen=True)
class IrrelevantResult:
    succeeded: bool
    document_id: str
    reason_code: str | None
    document: Document | None
    registry_recorded: bool = False
    registry_created: bool = False
    pdf_deleted: bool = False
    store_updated: bool = False
    partial_failure: bool = False
    rollback_failed: bool = False
    error_type: str | None = None


class IrrelevantService:
    """Coordinate eligibility, exclusion, safe deletion and status persistence.

    Current file-backed storage cannot provide a transaction across the
    registry, PDF and document store. The service therefore validates first,
    compensates a newly-created registry entry when no PDF was deleted, and
    reports any unavoidable partial side effect explicitly.
    """

    def __init__(
        self,
        repository: DocumentRepository,
        *,
        downloads_root: str | Path | None = None,
        validate_target: Callable[..., LocalPdfDeletionPlan] =
        validate_local_pdf_deletion_target,
        registry_add: Callable[[Document], bool] = record_exclusion,
        registry_remove: Callable[[str], bool] = remove_exclusion,
        pdf_delete: Callable[..., LocalPdfDeletionResult] = delete_local_pdf_safely,
    ) -> None:
        self._repository = repository
        self._downloads_root = downloads_root
        self._validate_target = validate_target
        self._registry_add = registry_add
        self._registry_remove = registry_remove
        self._pdf_delete = pdf_delete

    def mark_irrelevant(
        self,
        document_id: str,
        *,
        reason: IrrelevantReason = IrrelevantReason.GENERAL,
        expected_status: str | None = None,
        expected_updated_at: str | None = None,
    ) -> IrrelevantResult:
        current = self._repository.get_by_drive_id(document_id)
        if current is None:
            return self._failure(document_id, "document_not_found", None)
        if expected_status is not None and current.status != expected_status:
            return self._failure(document_id, "stale_document", current)
        if expected_updated_at is not None and current.updated_at != expected_updated_at:
            return self._failure(document_id, "stale_document", current)
        if not can_mark_irrelevant(current):
            return self._failure(document_id, "status_not_eligible", current)

        try:
            plan = self._validate_target(current.local_path, self._downloads_root)
        except Exception as exc:
            return self._failure(
                document_id, "unsafe_local_path", current, error_type=type(exc).__name__
            )

        try:
            registry_created = self._registry_add(current)
        except Exception as exc:
            return self._failure(
                document_id,
                "exclusion_registry_failed",
                current,
                error_type=type(exc).__name__,
            )

        try:
            deletion = self._pdf_delete(plan=plan)
        except Exception as exc:
            rollback_failed = False
            if registry_created:
                try:
                    self._registry_remove(document_id)
                except Exception:
                    rollback_failed = True
            return IrrelevantResult(
                False,
                document_id,
                "local_pdf_deletion_failed",
                current,
                registry_recorded=not registry_created or rollback_failed,
                registry_created=registry_created,
                partial_failure=rollback_failed,
                rollback_failed=rollback_failed,
                error_type=type(exc).__name__,
            )

        updated = deepcopy(current)
        updated.status = "confirmed_irrelevant"
        updated.confirmed_irrelevant_at = datetime.now(timezone.utc).isoformat()
        updated.local_path = ""
        # A terminal irrelevant record must not retain the secondary duplicate
        # override, otherwise shared route policy would keep it in Attention.
        updated.is_duplicate_suspected = False
        updated.suspected_duplicate_of = None
        updated.duplicate_confidence = None

        try:
            self._repository.upsert(updated)
        except Exception as exc:
            rollback_failed = False
            registry_remains = True
            if registry_created and not deletion.deleted:
                try:
                    self._registry_remove(document_id)
                    registry_remains = False
                except Exception:
                    rollback_failed = True
            partial = deletion.deleted or rollback_failed
            return IrrelevantResult(
                False,
                document_id,
                "document_persistence_failed",
                current,
                registry_recorded=registry_remains,
                registry_created=registry_created,
                pdf_deleted=deletion.deleted,
                partial_failure=partial,
                rollback_failed=rollback_failed,
                error_type=type(exc).__name__,
            )

        persisted = self._repository.get_by_drive_id(document_id) or updated
        return IrrelevantResult(
            True,
            document_id,
            None,
            persisted,
            registry_recorded=True,
            registry_created=registry_created,
            pdf_deleted=deletion.deleted,
            store_updated=True,
        )

    @staticmethod
    def _failure(
        document_id: str,
        reason_code: str,
        document: Document | None,
        *,
        error_type: str | None = None,
    ) -> IrrelevantResult:
        return IrrelevantResult(
            False,
            document_id,
            reason_code,
            document,
            error_type=error_type,
        )
