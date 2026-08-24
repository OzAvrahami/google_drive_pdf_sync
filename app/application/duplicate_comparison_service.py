"""Read-only duplicate comparison derived from the existing detector rules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.document_repository import DocumentRepository
from app.models.document import Document
from app.services.duplicate_detection_service import (
    normalize_duplicate_date,
    normalize_duplicate_invoice_number,
    normalize_duplicate_supplier,
)


@dataclass(frozen=True)
class DuplicateFieldComparison:
    field_name: str
    current_value: Any
    candidate_value: Any
    current_normalized: Any
    candidate_normalized: Any
    matches: bool
    participates_in_rule: bool


@dataclass(frozen=True)
class DuplicateComparison:
    current_document_id: str
    candidate_document_id: str
    current_document: Document | None
    candidate_document: Document | None
    confidence: str | None
    reason_code: str
    fields: tuple[DuplicateFieldComparison, ...] = ()

    @property
    def candidate_available(self) -> bool:
        return self.candidate_document is not None

    def field(self, field_name: str) -> DuplicateFieldComparison:
        return next(item for item in self.fields if item.field_name == field_name)


class DuplicateComparisonService:
    """Build comparisons without mutating documents or rerunning detection."""

    def __init__(self, repository: DocumentRepository) -> None:
        self._repository = repository

    def compare(self, current_id: str, candidate_id: str) -> DuplicateComparison:
        current = self._repository.get_by_drive_id(current_id)
        if current is None:
            return DuplicateComparison(
                current_id, candidate_id, None, None, None, "current_document_missing"
            )
        candidate_ids = tuple(current.suspected_duplicate_of or ())
        if candidate_id not in candidate_ids:
            return DuplicateComparison(
                current_id,
                candidate_id,
                current,
                None,
                current.duplicate_confidence,
                "candidate_not_suspected",
            )
        candidate = self._repository.get_by_drive_id(candidate_id)
        if candidate is None:
            return DuplicateComparison(
                current_id,
                candidate_id,
                current,
                None,
                current.duplicate_confidence,
                "candidate_missing",
            )

        confidence = current.duplicate_confidence
        participants = {
            "exact": {"supplier_name", "invoice_number", "invoice_date"},
            "high": {"supplier_name", "invoice_date", "total"},
        }.get(confidence, set())
        fields = tuple(
            self._field_comparison(current, candidate, name, name in participants)
            for name in (
                "supplier_name",
                "invoice_number",
                "invoice_date",
                "total",
                "file_name",
                "folder_path",
                "status",
            )
        )
        reason = {
            "exact": "exact_supplier_number_date",
            "high": "high_supplier_date_amount",
        }.get(confidence, "persisted_duplicate_suspicion")
        return DuplicateComparison(
            current_id,
            candidate_id,
            current,
            candidate,
            confidence,
            reason,
            fields,
        )

    def compare_all(self, current_id: str) -> tuple[DuplicateComparison, ...]:
        current = self._repository.get_by_drive_id(current_id)
        if current is None:
            return ()
        return tuple(
            self.compare(current_id, candidate_id)
            for candidate_id in tuple(current.suspected_duplicate_of or ())
        )

    @staticmethod
    def _field_comparison(
        current: Document,
        candidate: Document,
        field_name: str,
        participates: bool,
    ) -> DuplicateFieldComparison:
        current_value = DuplicateComparisonService._value(current, field_name)
        candidate_value = DuplicateComparisonService._value(candidate, field_name)
        normalizer = {
            "supplier_name": normalize_duplicate_supplier,
            "invoice_number": normalize_duplicate_invoice_number,
            "invoice_date": normalize_duplicate_date,
        }.get(field_name)
        if normalizer:
            current_normalized = normalizer(current_value)
            candidate_normalized = normalizer(candidate_value)
        else:
            current_normalized = current_value
            candidate_normalized = candidate_value

        if field_name == "total":
            matches = (
                current_value is not None
                and candidate_value is not None
                and abs(candidate_value - current_value) < 0.01
            )
        else:
            matches = bool(current_normalized) and current_normalized == candidate_normalized
        return DuplicateFieldComparison(
            field_name,
            current_value,
            candidate_value,
            current_normalized,
            candidate_normalized,
            matches,
            participates,
        )

    @staticmethod
    def _value(document: Document, field_name: str) -> Any:
        if field_name in {
            "supplier_name",
            "invoice_number",
            "invoice_date",
            "total",
        }:
            return document.effective(field_name)
        return getattr(document, field_name, None)
