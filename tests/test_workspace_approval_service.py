from __future__ import annotations

from copy import deepcopy

from app.application.approval_service import ApprovalService
from app.application.document_review_service import DocumentReviewService
from app.application.workspace_approval_service import WorkspaceApprovalService
from app.domain.validation import ValidationRules
from app.models.document import Document


class MemoryRepository:
    def __init__(self, document: Document, *, fail_on_write: int | None = None) -> None:
        self.document = deepcopy(document)
        self.write_count = 0
        self.fail_on_write = fail_on_write

    def get_by_drive_id(self, document_id: str) -> Document | None:
        if self.document.drive_file_id != document_id:
            return None
        return deepcopy(self.document)

    def upsert(self, document: Document) -> None:
        self.write_count += 1
        if self.fail_on_write == self.write_count:
            raise OSError("synthetic persistence failure")
        stored = deepcopy(document)
        stored.touch()
        self.document = stored

    def upsert_many(self, documents) -> None:
        for document in documents:
            self.upsert(document)


def make_document(status: str = "processed", **overrides) -> Document:
    values = {
        "drive_file_id": "drive-1",
        "id": "record-1",
        "file_name": "invoice.pdf",
        "folder_path": "Drive / 2026",
        "status": status,
        "supplier_name": "Original Supplier",
        "invoice_number": "INV-1",
        "invoice_date": "24/08/2026",
        "subtotal": 100.0,
        "vat": 17.0,
        "total": 117.0,
        "confidence": 0.31,
        "extracted_data": {
            "business_name": "Original Supplier",
            "invoice_number": "INV-1",
            "invoice_date": "24/08/2026",
            "amount": 117.0,
        },
    }
    values.update(overrides)
    return Document(**values)


def services(repository: MemoryRepository, learning=None):
    rules = ValidationRules()
    review = DocumentReviewService(
        repository,
        validation_rules=rules,
        learning_recorder=learning or (lambda **_kwargs: None),
    )
    approval = ApprovalService(repository, validation_rules=rules)
    return review, WorkspaceApprovalService(repository, review, approval)


def test_clean_processed_draft_approves_with_one_status_write() -> None:
    repository = MemoryRepository(make_document())
    review, workspace = services(repository)

    result = workspace.approve_draft(review.load_draft("drive-1"))

    assert result.approved is True
    assert result.corrections_saved is False
    assert repository.write_count == 1
    assert repository.document.status == "approved"


def test_needs_review_can_approve_directly_without_processed_transition() -> None:
    repository = MemoryRepository(make_document("needs_review"))
    review, workspace = services(repository)

    result = workspace.approve_draft(review.load_draft("drive-1"))

    assert result.approved is True
    assert repository.document.status == "approved"
    assert repository.write_count == 1


def test_dirty_draft_is_saved_then_approved_and_learning_runs() -> None:
    calls: list[dict] = []
    repository = MemoryRepository(make_document())
    review, workspace = services(repository, lambda **kwargs: calls.append(kwargs))
    draft = review.load_draft("drive-1")
    draft.set_value("supplier_name", "Updated Supplier")

    result = workspace.approve_draft(draft)

    assert result.approved is True
    assert result.corrections_saved is True
    assert repository.write_count == 2
    assert repository.document.corrected_data["supplier_name"] == "Updated Supplier"
    assert repository.document.was_manually_corrected is True
    assert repository.document.status == "approved"
    assert calls[0]["corrected_value"] == "Updated Supplier"


def test_learning_failure_does_not_roll_back_save_or_approval() -> None:
    def fail_learning(**_kwargs):
        raise RuntimeError("synthetic learning failure")

    repository = MemoryRepository(make_document())
    review, workspace = services(repository, fail_learning)
    draft = review.load_draft("drive-1")
    draft.set_value("supplier_name", "Updated Supplier")

    result = workspace.approve_draft(draft)

    assert result.approved is True
    assert result.corrections_saved is True
    assert result.learning_failures[0].error_type == "RuntimeError"
    assert repository.document.status == "approved"


def test_invalid_numeric_draft_blocks_every_write() -> None:
    repository = MemoryRepository(make_document())
    review, workspace = services(repository)
    draft = review.load_draft("drive-1")
    draft.set_value("total", "not-a-number")

    result = workspace.approve_draft(draft)

    assert result.approved is False
    assert "invalid_number" in result.reason_codes
    assert repository.write_count == 0
    assert repository.document.status == "processed"


def test_unsupported_explicit_clear_blocks_save_and_approval() -> None:
    repository = MemoryRepository(make_document())
    review, workspace = services(repository)
    draft = review.load_draft("drive-1")
    draft.clear_field("supplier_name")

    result = workspace.approve_draft(draft)

    assert result.approved is False
    assert result.reason_codes == ("explicit_clear_not_persistable",)
    assert repository.write_count == 0


def test_save_failure_prevents_approval_attempt() -> None:
    repository = MemoryRepository(make_document(), fail_on_write=1)
    review, workspace = services(repository)
    draft = review.load_draft("drive-1")
    draft.set_value("description", "Updated")

    result = workspace.approve_draft(draft)

    assert result.approved is False
    assert result.failure_stage == "save"
    assert result.reason_codes == ("save_failed",)
    assert repository.write_count == 1
    assert repository.document.status == "processed"


def test_approval_failure_preserves_saved_correction_without_approval() -> None:
    repository = MemoryRepository(make_document(), fail_on_write=2)
    review, workspace = services(repository)
    draft = review.load_draft("drive-1")
    draft.set_value("description", "Persisted correction")

    result = workspace.approve_draft(draft)

    assert result.approved is False
    assert result.corrections_saved is True
    assert result.failure_stage == "approval"
    assert result.reason_codes == ("approval_persistence_failed",)
    assert repository.document.corrected_data["description"] == "Persisted correction"
    assert repository.document.status == "processed"


def test_low_document_confidence_is_not_an_approval_blocker() -> None:
    repository = MemoryRepository(make_document(confidence=0.05))
    review, workspace = services(repository)

    result = workspace.approve_draft(review.load_draft("drive-1"))

    assert result.approved is True


def test_stale_terminal_status_blocks_dirty_approval_without_write() -> None:
    repository = MemoryRepository(make_document())
    review, workspace = services(repository)
    draft = review.load_draft("drive-1")
    draft.set_value("description", "Draft")
    repository.document.status = "exported"
    repository.document.touch()

    result = workspace.approve_draft(draft)

    assert result.approved is False
    assert "stale_document_status" in result.reason_codes
    assert repository.write_count == 0


def test_configured_required_field_blocks_approval_without_becoming_global_policy() -> None:
    repository = MemoryRepository(make_document(supplier_name=None))
    rules = ValidationRules(required_fields=frozenset({"supplier_name"}))
    review = DocumentReviewService(
        repository, validation_rules=rules, learning_recorder=lambda **_kwargs: None
    )
    workspace = WorkspaceApprovalService(
        repository, review, ApprovalService(repository, validation_rules=rules)
    )

    result = workspace.approve_draft(review.load_draft("drive-1"))

    assert result.approved is False
    assert result.reason_codes == ("required_missing",)
    assert repository.write_count == 0
