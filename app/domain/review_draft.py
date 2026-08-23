"""UI-independent state for one Panda document-review editing session."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.domain.validation import (
    FieldState,
    ValidationResult,
    ValidationRules,
    validate_review_values,
)
from app.models.document import Document


REVIEW_FIELDS = (
    "supplier_name",
    "invoice_number",
    "invoice_date",
    "total",
    "vat",
    "subtotal",
    "description",
)


class UnknownReviewFieldError(ValueError):
    pass


@dataclass(frozen=True)
class ReviewField:
    field_name: str
    displayed_value: str
    extracted_value: Any
    persisted_corrected_value: Any
    baseline_value: str
    has_existing_correction: bool
    changed_in_session: bool
    explicitly_cleared: bool
    presentation_state: FieldState


def _display_value(value: Any) -> str:
    return "" if value is None else str(value)


class ReviewDraft:
    """A mutable draft that never persists or mutates its source Document."""

    def __init__(
        self,
        *,
        source_document_id: str,
        source_record_id: str,
        source_status: str,
        file_name: str,
        extracted_values: Mapping[str, Any],
        persisted_corrected_values: Mapping[str, Any],
        baseline_values: Mapping[str, str],
        validation_rules: ValidationRules | None = None,
        low_confidence_fields: Iterable[str] = (),
    ) -> None:
        self.source_document_id = source_document_id
        self.source_record_id = source_record_id
        self.source_status = source_status
        self.file_name = file_name
        self._extracted_values = dict(extracted_values)
        self._persisted_corrected_values = dict(persisted_corrected_values)
        self._baseline_values = dict(baseline_values)
        self._values = dict(baseline_values)
        self._explicitly_cleared: set[str] = set()
        self._validation_rules = validation_rules or ValidationRules()
        self._low_confidence_fields = frozenset(low_confidence_fields)

    @classmethod
    def from_document(
        cls,
        document: Document,
        *,
        validation_rules: ValidationRules | None = None,
        low_confidence_fields: Iterable[str] = (),
    ) -> "ReviewDraft":
        extracted = {name: getattr(document, name, None) for name in REVIEW_FIELDS}
        corrected = {
            name: document.corrected_data[name]
            for name in REVIEW_FIELDS
            if name in document.corrected_data
        }
        baseline = {
            name: _display_value(document.effective(name)) for name in REVIEW_FIELDS
        }
        return cls(
            source_document_id=document.drive_file_id,
            source_record_id=document.id,
            source_status=document.status,
            file_name=document.file_name,
            extracted_values=extracted,
            persisted_corrected_values=corrected,
            baseline_values=baseline,
            validation_rules=validation_rules,
            low_confidence_fields=low_confidence_fields,
        )

    @property
    def field_names(self) -> tuple[str, ...]:
        return REVIEW_FIELDS

    @property
    def baseline_values(self) -> dict[str, str]:
        return dict(self._baseline_values)

    @property
    def current_values(self) -> dict[str, str]:
        return dict(self._values)

    @property
    def changed_fields(self) -> frozenset[str]:
        return frozenset(
            name
            for name in REVIEW_FIELDS
            if self._values[name] != self._baseline_values[name]
        )

    @property
    def explicitly_cleared_fields(self) -> frozenset[str]:
        return frozenset(self._explicitly_cleared)

    @property
    def is_dirty(self) -> bool:
        return bool(self.changed_fields)

    @property
    def validation_result(self) -> ValidationResult:
        corrected_fields = {
            *self._persisted_corrected_values.keys(),
            *(self.changed_fields - self.explicitly_cleared_fields),
        }
        return validate_review_values(
            self._values,
            rules=self._validation_rules,
            corrected_fields=corrected_fields,
            low_confidence_fields=self._low_confidence_fields,
        )

    def _require_field(self, field_name: str) -> None:
        if field_name not in REVIEW_FIELDS:
            raise UnknownReviewFieldError(field_name)

    def current_value(self, field_name: str) -> str:
        self._require_field(field_name)
        return self._values[field_name]

    def set_value(self, field_name: str, value: Any) -> None:
        self._require_field(field_name)
        displayed = _display_value(value)
        self._values[field_name] = displayed
        if not displayed and self._baseline_values[field_name]:
            self._explicitly_cleared.add(field_name)
        else:
            self._explicitly_cleared.discard(field_name)

    def clear_field(self, field_name: str) -> None:
        self._require_field(field_name)
        self._values[field_name] = ""
        self._explicitly_cleared.add(field_name)

    def revert_field(self, field_name: str) -> None:
        self._require_field(field_name)
        self._values[field_name] = self._baseline_values[field_name]
        self._explicitly_cleared.discard(field_name)

    def field(self, field_name: str) -> ReviewField:
        self._require_field(field_name)
        validation = self.validation_result.for_field(field_name)
        assert validation is not None
        return ReviewField(
            field_name=field_name,
            displayed_value=self._values[field_name],
            extracted_value=self._extracted_values.get(field_name),
            persisted_corrected_value=self._persisted_corrected_values.get(field_name),
            baseline_value=self._baseline_values[field_name],
            has_existing_correction=field_name in self._persisted_corrected_values,
            changed_in_session=field_name in self.changed_fields,
            explicitly_cleared=field_name in self._explicitly_cleared,
            presentation_state=validation.state,
        )
