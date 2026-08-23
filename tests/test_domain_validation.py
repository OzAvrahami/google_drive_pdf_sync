"""Tests for Panda's configurable validation foundation."""

from __future__ import annotations

import pytest

from app.domain.validation import (
    FieldState,
    ValidationRules,
    ValidationSeverity,
    parse_numeric_input,
    validate_review_values,
)


RULES = ValidationRules(
    required_fields=frozenset({"supplier_name", "invoice_number", "invoice_date", "total"})
)


def _valid_values() -> dict[str, object]:
    return {
        "supplier_name": "Example Supplier",
        "invoice_number": "INV-100",
        "invoice_date": "22/08/2026",
        "total": "125.50",
        "vat": "20.00",
        "subtotal": "105.50",
        "description": "Services",
    }


def test_valid_values_have_no_issues_and_are_approvable() -> None:
    result = validate_review_values(_valid_values(), rules=RULES)

    assert result.issues == ()
    assert result.has_blocking_errors is False
    assert result.is_approvable is True


def test_missing_required_value_is_a_blocker() -> None:
    values = _valid_values()
    values["invoice_number"] = "  "

    result = validate_review_values(values, rules=RULES)

    field = result.for_field("invoice_number")
    assert field.state is FieldState.MISSING
    assert field.issues[0].code == "required_missing"
    assert field.issues[0].blocking is True
    assert result.is_approvable is False


@pytest.mark.parametrize("value", ["2026-08-22", "31/02/2026", "not-a-date"])
def test_invalid_date_draft_input_is_blocking(value: str) -> None:
    values = _valid_values()
    values["invoice_date"] = value

    result = validate_review_values(values, rules=RULES)

    assert result.for_field("invoice_date").state is FieldState.INVALID
    assert result.for_field("invoice_date").issues[0].code == "invalid_date"


@pytest.mark.parametrize("value", ["abc", "12.3.4", float("inf"), True])
def test_invalid_numeric_draft_input_is_blocking(value: object) -> None:
    values = _valid_values()
    values["total"] = value

    result = validate_review_values(values, rules=RULES)

    assert result.for_field("total").state is FieldState.INVALID
    assert result.for_field("total").issues[0].code == "invalid_number"


def test_legacy_decimal_comma_is_accepted() -> None:
    assert parse_numeric_input("125,50") == 125.5


def test_low_confidence_is_a_warning_not_a_validity_blocker() -> None:
    result = validate_review_values(
        _valid_values(), rules=RULES, low_confidence_fields={"total"}
    )

    field = result.for_field("total")
    assert field.state is FieldState.LOW_CONFIDENCE
    assert field.issues[0].severity is ValidationSeverity.WARNING
    assert field.issues[0].blocking is False
    assert result.is_approvable is True
    assert len(result.warnings) == 1


def test_corrected_field_has_corrected_provenance_state() -> None:
    result = validate_review_values(
        _valid_values(), rules=RULES, corrected_fields={"supplier_name"}
    )

    assert result.for_field("supplier_name").state is FieldState.CORRECTED


def test_required_fields_are_policy_driven_not_universal() -> None:
    result = validate_review_values(
        {"supplier_name": "", "invoice_number": ""}, rules=ValidationRules()
    )

    assert result.blockers == ()
    assert result.is_approvable is True


def test_blockers_and_warnings_are_available_separately() -> None:
    values = _valid_values()
    values["invoice_number"] = ""
    result = validate_review_values(
        values, rules=RULES, low_confidence_fields={"total"}
    )

    assert [issue.code for issue in result.blockers] == ["required_missing"]
    assert [issue.code for issue in result.warnings] == ["low_confidence"]
