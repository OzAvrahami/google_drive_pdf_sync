"""Application tests for review save planning and learning parity."""

from __future__ import annotations

import pytest

from app.application.document_review_service import DocumentReviewService
from app.domain.validation import ValidationRules
from app.models.document import Document


class MemoryRepository:
    def __init__(self, *documents: Document, fail_writes: bool = False) -> None:
        self.documents = {doc.drive_file_id: doc for doc in documents}
        self.fail_writes = fail_writes
        self.upsert_calls: list[Document] = []
        self.upsert_many_calls: list[list[Document]] = []

    def get_by_drive_id(self, drive_file_id: str) -> Document | None:
        return self.documents.get(drive_file_id)

    def upsert(self, document: Document) -> None:
        if self.fail_writes:
            raise OSError("simulated store failure")
        self.upsert_calls.append(document)
        self.documents[document.drive_file_id] = document

    def upsert_many(self, documents: list[Document]) -> None:
        self.upsert_many_calls.append(documents)
        for document in documents:
            self.documents[document.drive_file_id] = document


def _document(**overrides) -> Document:
    values = {
        "drive_file_id": "drive-1",
        "file_name": "invoice.pdf",
        "folder_path": "invoices",
        "status": "needs_review",
        "supplier_name": "Extracted Supplier",
        "invoice_number": "INV-100",
        "invoice_date": "22/08/2026",
        "subtotal": 100.0,
        "vat": 17.0,
        "total": 117.0,
        "description": None,
        "extracted_data": {
            "business_name": "Extracted Supplier",
            "invoice_number": "INV-100",
            "invoice_date": "22/08/2026",
            "amount": 117.0,
        },
    }
    values.update(overrides)
    return Document(**values)


def test_safe_correction_persists_without_changing_workflow_status() -> None:
    repository = MemoryRepository(_document())
    service = DocumentReviewService(repository, learning_recorder=lambda **_: None)
    draft = service.load_draft("drive-1")
    draft.set_value("supplier_name", "Correct Supplier")

    result = service.save_draft(draft)

    stored = repository.documents["drive-1"]
    assert result.saved is True
    assert stored.corrected_data == {"supplier_name": "Correct Supplier"}
    assert stored.was_manually_corrected is True
    assert stored.status == "needs_review"
    assert len(repository.upsert_calls) == 1


def test_no_op_save_performs_no_write_and_no_learning() -> None:
    document = _document()
    repository = MemoryRepository(document)
    learning_calls: list[dict] = []
    service = DocumentReviewService(
        repository, learning_recorder=lambda **kwargs: learning_calls.append(kwargs)
    )

    result = service.save_draft(service.load_draft("drive-1"))

    assert result.saved is False
    assert result.plan.can_save is True
    assert result.plan.requires_write is False
    assert repository.upsert_calls == []
    assert learning_calls == []


def test_no_op_save_does_not_normalise_legacy_manual_flag() -> None:
    document = _document(
        corrected_data={"supplier_name": "Prior Correction"},
        was_manually_corrected=False,
    )
    repository = MemoryRepository(document)
    service = DocumentReviewService(repository, learning_recorder=lambda **_: None)

    result = service.save_draft(service.load_draft("drive-1"))

    assert result.saved is False
    assert result.plan.requires_write is False
    assert repository.upsert_calls == []
    assert document.was_manually_corrected is False


def test_reverting_existing_correction_to_extracted_value_clears_manual_flag() -> None:
    repository = MemoryRepository(
        _document(
            corrected_data={"supplier_name": "Prior Correction"},
            was_manually_corrected=True,
        )
    )
    service = DocumentReviewService(repository, learning_recorder=lambda **_: None)
    draft = service.load_draft("drive-1")
    draft.set_value("supplier_name", "Extracted Supplier")

    result = service.save_draft(draft)

    assert result.saved is True
    assert result.document.corrected_data == {}
    assert result.document.was_manually_corrected is False


def test_learning_calls_match_legacy_field_mapping_and_payload() -> None:
    repository = MemoryRepository(_document())
    calls: list[dict] = []
    service = DocumentReviewService(
        repository, learning_recorder=lambda **kwargs: calls.append(kwargs)
    )
    draft = service.load_draft("drive-1")
    draft.set_value("supplier_name", "Correct Supplier")
    draft.set_value("total", "120,50")
    draft.set_value("subtotal", "103.50")

    result = service.save_draft(draft)

    assert result.saved is True
    assert calls == [
        {
            "field_name": "supplier_name",
            "original_value": "Extracted Supplier",
            "corrected_value": "Correct Supplier",
            "drive_file_id": "drive-1",
            "file_name": "invoice.pdf",
        },
        {
            "field_name": "total",
            "original_value": "117.0",
            "corrected_value": "120.5",
            "drive_file_id": "drive-1",
            "file_name": "invoice.pdf",
        },
    ]


def test_learning_runs_only_after_successful_store_write() -> None:
    repository = MemoryRepository(_document(), fail_writes=True)
    calls: list[dict] = []
    service = DocumentReviewService(
        repository, learning_recorder=lambda **kwargs: calls.append(kwargs)
    )
    draft = service.load_draft("drive-1")
    draft.set_value("supplier_name", "Correct Supplier")

    with pytest.raises(OSError, match="simulated store failure"):
        service.save_draft(draft)

    assert calls == []
    assert repository.documents["drive-1"].corrected_data == {}


def test_learning_failure_is_reported_without_undoing_successful_save() -> None:
    repository = MemoryRepository(_document())

    def fail_learning(**_kwargs) -> None:
        raise RuntimeError("simulated learning failure")

    service = DocumentReviewService(repository, learning_recorder=fail_learning)
    draft = service.load_draft("drive-1")
    draft.set_value("supplier_name", "Correct Supplier")

    result = service.save_draft(draft)

    assert result.saved is True
    assert [(failure.field_name, failure.error_type) for failure in result.learning_failures] == [
        ("supplier_name", "RuntimeError")
    ]


def test_populated_explicit_clear_is_rejected_without_a_write() -> None:
    repository = MemoryRepository(_document())
    service = DocumentReviewService(repository, learning_recorder=lambda **_: None)
    draft = service.load_draft("drive-1")
    draft.clear_field("invoice_number")

    result = service.save_draft(draft)

    assert result.saved is False
    assert result.plan.can_save is False
    assert result.plan.reason_codes == ("explicit_clear_not_persistable",)
    assert repository.upsert_calls == []
    assert repository.documents["drive-1"].invoice_number == "INV-100"


def test_invalid_numeric_draft_input_is_rejected_without_a_write() -> None:
    repository = MemoryRepository(_document())
    service = DocumentReviewService(repository, learning_recorder=lambda **_: None)
    draft = service.load_draft("drive-1")
    draft.set_value("total", "not-a-number")

    result = service.save_draft(draft)

    assert result.saved is False
    assert result.plan.reason_codes == ("invalid_draft_input",)
    assert repository.upsert_calls == []


def test_missing_required_value_does_not_prevent_safe_partial_correction_save() -> None:
    document = _document(invoice_number=None)
    repository = MemoryRepository(document)
    rules = ValidationRules(required_fields=frozenset({"invoice_number"}))
    service = DocumentReviewService(
        repository,
        validation_rules=rules,
        learning_recorder=lambda **_: None,
    )
    draft = service.load_draft("drive-1")
    draft.set_value("description", "Needs invoice number")

    result = service.save_draft(draft)

    assert result.saved is True
    assert result.plan.validation.has_blocking_errors is True
    assert result.document.corrected_data["description"] == "Needs invoice number"


def test_non_reviewable_status_cannot_persist_a_draft() -> None:
    repository = MemoryRepository(_document(status="approved"))
    service = DocumentReviewService(repository, learning_recorder=lambda **_: None)
    draft = service.load_draft("drive-1")
    draft.set_value("description", "changed")

    result = service.save_draft(draft)

    assert result.saved is False
    assert result.plan.reason_codes == ("review_not_allowed",)
    assert repository.upsert_calls == []
