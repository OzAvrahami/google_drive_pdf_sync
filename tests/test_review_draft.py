"""Tests for ReviewDraft state, provenance, validation, and dirty tracking."""

from __future__ import annotations

from app.domain.review_draft import REVIEW_FIELDS, ReviewDraft
from app.domain.validation import FieldState, ValidationRules
from app.models.document import Document


def _document(**overrides) -> Document:
    values = {
        "drive_file_id": "drive-1",
        "file_name": "invoice.pdf",
        "folder_path": "invoices",
        "status": "needs_review",
        "supplier_name": "Extracted Supplier",
        "invoice_number": "INV-100",
        "invoice_date": "22/08/2026",
        "total": 125.5,
        "vat": 20.0,
        "subtotal": 105.5,
        "description": None,
    }
    values.update(overrides)
    return Document(**values)


def test_initialization_supports_exact_legacy_review_fields() -> None:
    draft = ReviewDraft.from_document(_document())

    assert draft.field_names == REVIEW_FIELDS
    assert draft.source_document_id == "drive-1"
    assert draft.current_value("supplier_name") == "Extracted Supplier"
    assert draft.current_value("total") == "125.5"
    assert draft.is_dirty is False


def test_existing_correction_is_visible_with_provenance() -> None:
    draft = ReviewDraft.from_document(
        _document(corrected_data={"supplier_name": "Corrected Supplier"})
    )

    field = draft.field("supplier_name")
    assert field.displayed_value == "Corrected Supplier"
    assert field.extracted_value == "Extracted Supplier"
    assert field.persisted_corrected_value == "Corrected Supplier"
    assert field.has_existing_correction is True
    assert field.changed_in_session is False
    assert field.presentation_state is FieldState.CORRECTED


def test_editing_changes_current_value_and_marks_dirty() -> None:
    draft = ReviewDraft.from_document(_document())

    draft.set_value("supplier_name", "New Supplier")

    assert draft.current_value("supplier_name") == "New Supplier"
    assert draft.changed_fields == frozenset({"supplier_name"})
    assert draft.field("supplier_name").changed_in_session is True
    assert draft.is_dirty is True


def test_no_op_assignment_is_not_dirty() -> None:
    draft = ReviewDraft.from_document(_document())

    draft.set_value("supplier_name", "Extracted Supplier")

    assert draft.is_dirty is False


def test_reverting_exactly_to_baseline_clears_dirty_state() -> None:
    draft = ReviewDraft.from_document(_document())
    draft.set_value("supplier_name", "New Supplier")

    draft.set_value("supplier_name", "Extracted Supplier")

    assert draft.changed_fields == frozenset()
    assert draft.is_dirty is False


def test_revert_field_restores_existing_corrected_baseline() -> None:
    draft = ReviewDraft.from_document(
        _document(corrected_data={"supplier_name": "Prior Correction"})
    )
    draft.set_value("supplier_name", "Session Edit")

    draft.revert_field("supplier_name")

    assert draft.current_value("supplier_name") == "Prior Correction"
    assert draft.is_dirty is False


def test_explicit_clear_of_populated_field_is_distinct_and_dirty() -> None:
    draft = ReviewDraft.from_document(_document())

    draft.clear_field("invoice_number")

    field = draft.field("invoice_number")
    assert field.displayed_value == ""
    assert field.explicitly_cleared is True
    assert draft.explicitly_cleared_fields == frozenset({"invoice_number"})
    assert draft.is_dirty is True


def test_whitespace_only_input_is_an_explicit_clear_not_a_persistable_value() -> None:
    draft = ReviewDraft.from_document(_document())

    draft.set_value("invoice_number", "   ")

    assert draft.current_value("invoice_number") == "   "
    assert draft.explicitly_cleared_fields == frozenset({"invoice_number"})
    assert draft.is_dirty is True


def test_reverting_explicit_clear_removes_clear_marker() -> None:
    draft = ReviewDraft.from_document(_document())
    draft.clear_field("invoice_number")

    draft.revert_field("invoice_number")

    assert draft.explicitly_cleared_fields == frozenset()
    assert draft.is_dirty is False


def test_clear_of_already_empty_field_records_intent_without_false_dirty_state() -> None:
    draft = ReviewDraft.from_document(_document(description=None))

    draft.clear_field("description")

    assert draft.field("description").explicitly_cleared is True
    assert draft.is_dirty is False


def test_multiple_changed_fields_are_tracked_independently() -> None:
    draft = ReviewDraft.from_document(_document())

    draft.set_value("supplier_name", "New Supplier")
    draft.set_value("invoice_date", "23/08/2026")
    draft.set_value("total", "130.00")

    assert draft.changed_fields == frozenset(
        {"supplier_name", "invoice_date", "total"}
    )


def test_validation_result_updates_with_draft_input() -> None:
    rules = ValidationRules(required_fields=frozenset({"invoice_number", "total"}))
    draft = ReviewDraft.from_document(_document(), validation_rules=rules)

    draft.set_value("total", "not numeric")

    assert draft.validation_result.is_approvable is False
    assert draft.field("total").presentation_state is FieldState.INVALID


def test_low_confidence_remains_non_blocking_in_draft() -> None:
    rules = ValidationRules(required_fields=frozenset({"total"}))
    draft = ReviewDraft.from_document(
        _document(), validation_rules=rules, low_confidence_fields={"total"}
    )

    assert draft.field("total").presentation_state is FieldState.LOW_CONFIDENCE
    assert draft.validation_result.is_approvable is True
