from __future__ import annotations

from copy import deepcopy

from app.models.document import Document
from app.ui.theme.direction import TextKind
from app.ui.workspace.presentation import (
    WorkspaceFieldState,
    build_workspace_presentation,
)


def document(**overrides) -> Document:
    values = {
        "drive_file_id": "drive-1",
        "id": "record-1",
        "file_name": "invoice.pdf",
        "folder_path": "Drive / 2026",
        "status": "needs_review",
        "confidence": 0.62,
        "supplier_name": "Extracted Supplier",
        "invoice_number": "INV-17",
        "invoice_date": "24/08/2026",
        "subtotal": 100.0,
        "vat": 17.0,
        "total": 117.0,
        "description": None,
        "extracted_data": {"document_type": "חשבונית מס"},
    }
    values.update(overrides)
    return Document(**values)


def fields_by_name(document: Document):
    return {
        field.name: field for field in build_workspace_presentation(document).fields
    }


def test_workspace_snapshot_uses_effective_values_and_provenance() -> None:
    source = document(corrected_data={"supplier_name": "Corrected Supplier"})
    fields = fields_by_name(source)

    assert fields["supplier_name"].value == "Corrected Supplier"
    assert fields["supplier_name"].extracted_value == "Extracted Supplier"
    assert fields["supplier_name"].corrected_value == "Corrected Supplier"
    assert fields["supplier_name"].state is WorkspaceFieldState.CORRECTED
    assert fields["invoice_number"].state is WorkspaceFieldState.EXTRACTED
    assert fields["description"].state is WorkspaceFieldState.MISSING


def test_document_type_comes_only_from_existing_extracted_data() -> None:
    fields = fields_by_name(document())

    assert fields["document_type"].value == "חשבונית מס"
    assert fields["document_type"].state is WorkspaceFieldState.EXTRACTED
    assert fields["document_type"].text_kind is TextKind.HEBREW


def test_safe_existing_validator_marks_malformed_values_without_required_policy() -> None:
    fields = fields_by_name(document(invoice_date="2026-08-24", total="not-money"))

    assert fields["invoice_date"].state is WorkspaceFieldState.INVALID
    assert fields["total"].state is WorkspaceFieldState.INVALID
    assert fields["description"].state is WorkspaceFieldState.MISSING


def test_overall_context_exposes_status_attention_duplicate_manual_and_error() -> None:
    presentation = build_workspace_presentation(
        document(
            status="failed",
            error_message="PDF parse failed",
            is_duplicate_suspected=True,
            suspected_duplicate_of=["other-1", "other-2"],
            was_manually_corrected=True,
        )
    )

    assert presentation.status == "failed"
    assert presentation.status_label
    assert presentation.confidence == 0.62
    assert presentation.attention_text
    assert presentation.error_message == "PDF parse failed"
    assert presentation.is_duplicate_suspected is True
    assert presentation.duplicate_candidate_count == 2
    assert presentation.was_manually_corrected is True


def test_building_workspace_snapshot_does_not_mutate_document() -> None:
    source = document(corrected_data={"total": 119.0})
    before = deepcopy(source.to_dict())

    presentation = build_workspace_presentation(source)

    assert source.to_dict() == before
    assert presentation.document_id == "drive-1"
