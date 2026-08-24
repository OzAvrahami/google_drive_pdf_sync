"""Immutable document snapshots consumed by Panda 2.0 queue models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from math import isfinite
from typing import Any

from app.domain.status_presentation import SemanticCategory, presentation_for
from app.models.document import Document


class AttentionReason(str, Enum):
    NONE = "none"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    SKIPPED = "skipped"
    SUSPECTED_DUPLICATE = "suspected_duplicate"


def parse_document_date(value: object) -> date | None:
    """Parse Panda's current persisted DD/MM/YYYY date representation."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def parse_document_amount(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def parse_confidence(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _attention_reason(document: Document, confidence: float | None) -> tuple[AttentionReason, str]:
    if document.status == "failed":
        message = document.error_message or "שגיאת עיבוד"
        return AttentionReason.FAILED, message[:90] + ("…" if len(message) > 90 else "")

    if document.status == "skipped":
        message = document.error_message or ""
        prefix = "מסמך לא רלוונטי: "
        if message.startswith(prefix):
            return AttentionReason.SKIPPED, f"סווג אוטומטית: {message[len(prefix):]}"
        return AttentionReason.SKIPPED, message or "סווג אוטומטית כלא-רלוונטי"

    if document.is_duplicate_suspected:
        label = "התאמה מדויקת" if document.duplicate_confidence == "exact" else "ביטחון גבוה"
        suffix = " — כפול של מסמך קיים" if document.suspected_duplicate_of else ""
        return AttentionReason.SUSPECTED_DUPLICATE, f"כפול חשוד ({label}){suffix}"

    if document.status == "needs_review":
        labels = {
            "supplier_name": "ספק",
            "invoice_date": "תאריך",
            "invoice_number": "מספר חשבונית",
            "total": "סכום",
        }
        missing = [label for field, label in labels.items() if not document.effective(field)]
        confidence_percent = int((confidence or 0.0) * 100)
        if missing:
            return (
                AttentionReason.NEEDS_REVIEW,
                f"חסר: {', '.join(missing)}  •  ביטחון {confidence_percent}%",
            )
        return AttentionReason.NEEDS_REVIEW, f"ביטחון נמוך ({confidence_percent}%)"

    return AttentionReason.NONE, ""


@dataclass(frozen=True, slots=True)
class DocumentPresentationRecord:
    """Small immutable snapshot; never exposes mutable persistence dictionaries."""

    document_id: str
    record_id: str
    file_name: str
    folder_path: str
    local_path: str
    supplier_name: str | None
    document_number: str | None
    document_date: str | None
    date_sort_value: date | None
    total: Decimal | None
    status: str
    status_label: str
    status_category: SemanticCategory
    confidence: float | None
    attention_reason: AttentionReason
    attention_text: str
    is_duplicate_suspected: bool
    suspected_duplicate_of: tuple[str, ...]
    duplicate_confidence: str | None
    was_manually_corrected: bool

    @classmethod
    def from_document(cls, document: Document) -> "DocumentPresentationRecord":
        if not document.drive_file_id:
            raise ValueError("A queue document requires a non-empty drive_file_id")

        presentation = presentation_for(document.status)
        document_date = _text(document.effective("invoice_date"))
        confidence = parse_confidence(document.confidence)
        reason, reason_text = _attention_reason(document, confidence)
        return cls(
            document_id=str(document.drive_file_id),
            record_id=str(document.id),
            file_name=document.file_name or "",
            folder_path=document.folder_path or "",
            local_path=document.local_path or "",
            supplier_name=_text(document.effective("supplier_name")),
            document_number=_text(document.effective("invoice_number")),
            document_date=document_date,
            date_sort_value=parse_document_date(document_date),
            total=parse_document_amount(document.effective("total")),
            status=document.status,
            status_label=presentation.label_he,
            status_category=presentation.semantic_category,
            confidence=confidence,
            attention_reason=reason,
            attention_text=reason_text,
            is_duplicate_suspected=bool(document.is_duplicate_suspected),
            suspected_duplicate_of=tuple(document.suspected_duplicate_of or ()),
            duplicate_confidence=document.duplicate_confidence,
            was_manually_corrected=bool(document.was_manually_corrected),
        )
