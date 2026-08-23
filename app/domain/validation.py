"""Pure validation primitives for review drafts and approval decisions."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Mapping


class ValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class FieldState(str, Enum):
    NORMAL = "normal"
    CORRECTED = "corrected"
    LOW_CONFIDENCE = "low_confidence"
    MISSING = "missing"
    INVALID = "invalid"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message_he: str
    severity: ValidationSeverity
    field_name: str | None = None
    blocking: bool = False


@dataclass(frozen=True)
class FieldValidation:
    field_name: str
    state: FieldState
    value: Any
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def has_blocking_errors(self) -> bool:
        return any(issue.blocking for issue in self.issues)

    @property
    def is_valid(self) -> bool:
        return not self.has_blocking_errors


@dataclass(frozen=True)
class ValidationResult:
    fields: Mapping[str, FieldValidation] = field(default_factory=dict)
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def blockers(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.blocking)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if not issue.blocking and issue.severity is ValidationSeverity.WARNING
        )

    @property
    def has_blocking_errors(self) -> bool:
        return bool(self.blockers)

    @property
    def is_approvable(self) -> bool:
        return not self.has_blocking_errors

    def for_field(self, field_name: str) -> FieldValidation | None:
        return self.fields.get(field_name)


@dataclass(frozen=True)
class ValidationRules:
    """Configurable rules; Panda has no approved universal required set yet."""

    required_fields: frozenset[str] = frozenset()
    date_fields: frozenset[str] = frozenset({"invoice_date"})
    numeric_fields: frozenset[str] = frozenset({"subtotal", "vat", "total"})


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def parse_numeric_input(value: Any) -> float | None:
    """Parse the current legacy-compatible decimal input representation."""
    if is_missing(value):
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a numeric draft value")
    if isinstance(value, (int, float)):
        parsed = float(value)
    else:
        text = str(value).strip().replace(",", ".")
        parsed = float(text)
    if not math.isfinite(parsed):
        raise ValueError("numeric draft value must be finite")
    return parsed


def is_valid_date_input(value: Any) -> bool:
    if is_missing(value):
        return False
    try:
        datetime.strptime(str(value).strip(), "%d/%m/%Y")
    except (TypeError, ValueError):
        return False
    return True


def validate_review_values(
    values: Mapping[str, Any],
    *,
    rules: ValidationRules | None = None,
    corrected_fields: Iterable[str] = (),
    low_confidence_fields: Iterable[str] = (),
) -> ValidationResult:
    rules = rules or ValidationRules()
    corrected = frozenset(corrected_fields)
    low_confidence = frozenset(low_confidence_fields)
    field_names = (
        set(values)
        | set(rules.required_fields)
        | set(rules.date_fields)
        | set(rules.numeric_fields)
        | set(corrected)
        | set(low_confidence)
    )

    field_results: dict[str, FieldValidation] = {}
    all_issues: list[ValidationIssue] = []

    for field_name in sorted(field_names):
        value = values.get(field_name)
        field_issues: list[ValidationIssue] = []
        missing = is_missing(value)

        if missing and field_name in rules.required_fields:
            field_issues.append(
                ValidationIssue(
                    code="required_missing",
                    field_name=field_name,
                    message_he="שדה חובה חסר — לא ניתן לאשר",
                    severity=ValidationSeverity.ERROR,
                    blocking=True,
                )
            )
        elif not missing and field_name in rules.numeric_fields:
            try:
                parse_numeric_input(value)
            except (TypeError, ValueError):
                field_issues.append(
                    ValidationIssue(
                        code="invalid_number",
                        field_name=field_name,
                        message_he="יש להזין ערך מספרי תקין",
                        severity=ValidationSeverity.ERROR,
                        blocking=True,
                    )
                )
        elif not missing and field_name in rules.date_fields:
            if not is_valid_date_input(value):
                field_issues.append(
                    ValidationIssue(
                        code="invalid_date",
                        field_name=field_name,
                        message_he="יש להזין תאריך תקין בפורמט DD/MM/YYYY",
                        severity=ValidationSeverity.ERROR,
                        blocking=True,
                    )
                )

        if field_name in low_confidence:
            field_issues.append(
                ValidationIssue(
                    code="low_confidence",
                    field_name=field_name,
                    message_he="זוהה בביטחון נמוך — מומלץ לוודא מול המקור",
                    severity=ValidationSeverity.WARNING,
                    blocking=False,
                )
            )

        if any(issue.blocking for issue in field_issues):
            state = FieldState.INVALID if not missing else FieldState.MISSING
        elif missing:
            state = FieldState.MISSING
        elif field_name in corrected:
            state = FieldState.CORRECTED
        elif field_name in low_confidence:
            state = FieldState.LOW_CONFIDENCE
        else:
            state = FieldState.NORMAL

        result = FieldValidation(field_name, state, value, tuple(field_issues))
        field_results[field_name] = result
        all_issues.extend(field_issues)

    return ValidationResult(field_results, tuple(all_issues))


def validate_document(
    document: Any,
    *,
    rules: ValidationRules | None = None,
    low_confidence_fields: Iterable[str] = (),
) -> ValidationResult:
    rules = rules or ValidationRules()
    field_names = set(rules.required_fields) | set(rules.date_fields) | set(
        rules.numeric_fields
    )
    values = {
        name: document.effective(name)
        for name in field_names
    }
    corrected = {
        name
        for name in getattr(document, "corrected_data", {})
        if getattr(document, "corrected_data", {}).get(name) not in (None, "")
    }
    return validate_review_values(
        values,
        rules=rules,
        corrected_fields=corrected,
        low_confidence_fields=low_confidence_fields,
    )
