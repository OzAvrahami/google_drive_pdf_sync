"""Immutable read-only presentation snapshots for Document Workspace."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.domain.review_draft import ReviewDraft
from app.models.document import Document
from app.ui.models.document_record import DocumentPresentationRecord
from app.ui.theme.direction import TextKind


class WorkspaceFieldState(str, Enum):
    EXTRACTED = "extracted"
    CORRECTED = "corrected"
    MISSING = "missing"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class WorkspaceField:
    name: str
    label_he: str
    value: str
    extracted_value: Any
    corrected_value: Any
    state: WorkspaceFieldState
    text_kind: TextKind
    helper_text: str = ""


@dataclass(frozen=True, slots=True)
class WorkspaceDocumentPresentation:
    document_id: str
    file_name: str
    folder_path: str
    local_path: str
    raw_text_path: str
    status: str
    status_label: str
    confidence: float | None
    attention_text: str
    error_message: str
    is_duplicate_suspected: bool
    duplicate_candidate_count: int
    was_manually_corrected: bool
    fields: tuple[WorkspaceField, ...]


_FIELD_DEFINITIONS = (
    ("supplier_name", "ספק", TextKind.HEBREW),
    ("document_type", "סוג מסמך", TextKind.HEBREW),
    ("invoice_date", "תאריך מסמך", TextKind.DATE),
    ("invoice_number", "מספר מסמך", TextKind.DOCUMENT_NUMBER),
    ("subtotal", "סכום לפני מע״מ", TextKind.AMOUNT),
    ("vat", "מע״מ", TextKind.AMOUNT),
    ("total", "סכום כולל", TextKind.AMOUNT),
    ("description", "תיאור", TextKind.HEBREW),
)


def _display(value: Any) -> str:
    return "" if value is None else str(value)


def build_workspace_presentation(document: Document) -> WorkspaceDocumentPresentation:
    """Snapshot current effective values without retaining a mutable Document."""

    draft = ReviewDraft.from_document(document)
    record = DocumentPresentationRecord.from_document(document)
    fields: list[WorkspaceField] = []
    for name, label, text_kind in _FIELD_DEFINITIONS:
        if name == "document_type":
            extracted = document.extracted_data.get("document_type")
            value = _display(extracted)
            state = WorkspaceFieldState.MISSING if not value.strip() else WorkspaceFieldState.EXTRACTED
            corrected = None
            helper = "לא זוהה סוג מסמך" if state is WorkspaceFieldState.MISSING else "חולץ מהמסמך"
        else:
            field = draft.field(name)
            value = field.displayed_value
            extracted = field.extracted_value
            corrected = field.persisted_corrected_value
            validation = draft.validation_result.for_field(name)
            if validation is not None and validation.state.value == "invalid":
                state = WorkspaceFieldState.INVALID
            elif not value.strip():
                state = WorkspaceFieldState.MISSING
            elif field.has_existing_correction:
                state = WorkspaceFieldState.CORRECTED
            else:
                state = WorkspaceFieldState.EXTRACTED
            helper = {
                WorkspaceFieldState.EXTRACTED: "ערך שחולץ",
                WorkspaceFieldState.CORRECTED: "תוקן בעבר",
                WorkspaceFieldState.MISSING: "לא נמצא ערך",
                WorkspaceFieldState.INVALID: "ערך שמור בפורמט לא תקין",
            }[state]
        fields.append(
            WorkspaceField(
                name=name,
                label_he=label,
                value=value,
                extracted_value=extracted,
                corrected_value=corrected,
                state=state,
                text_kind=text_kind,
                helper_text=helper,
            )
        )

    return WorkspaceDocumentPresentation(
        document_id=document.drive_file_id,
        file_name=document.file_name or "",
        folder_path=document.folder_path or "",
        local_path=document.local_path or "",
        raw_text_path=document.raw_text_path or "",
        status=document.status,
        status_label=record.status_label,
        confidence=record.confidence,
        attention_text=record.attention_text,
        error_message=document.error_message or "",
        is_duplicate_suspected=record.is_duplicate_suspected,
        duplicate_candidate_count=len(record.suspected_duplicate_of),
        was_manually_corrected=record.was_manually_corrected,
        fields=tuple(fields),
    )

