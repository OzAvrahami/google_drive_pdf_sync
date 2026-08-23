"""Application tests for single and all-or-block batch approval."""

from __future__ import annotations

import pytest

from app.application.approval_service import ApprovalService
from app.domain.validation import ValidationRules
from app.models.document import Document


class MemoryRepository:
    def __init__(self, *documents: Document) -> None:
        self.documents = {doc.drive_file_id: doc for doc in documents}
        self.upsert_calls: list[Document] = []
        self.upsert_many_calls: list[list[Document]] = []
        self.events: list[str] = []

    def get_by_drive_id(self, drive_file_id: str) -> Document | None:
        self.events.append(f"get:{drive_file_id}")
        return self.documents.get(drive_file_id)

    def upsert(self, document: Document) -> None:
        self.events.append(f"upsert:{document.drive_file_id}")
        self.upsert_calls.append(document)
        self.documents[document.drive_file_id] = document

    def upsert_many(self, documents: list[Document]) -> None:
        self.events.append("upsert_many")
        self.upsert_many_calls.append(documents)
        for document in documents:
            self.documents[document.drive_file_id] = document


RULES = ValidationRules(
    required_fields=frozenset(
        {"supplier_name", "invoice_number", "invoice_date", "total"}
    )
)


def _document(drive_file_id: str, status: str = "processed", **overrides) -> Document:
    values = {
        "drive_file_id": drive_file_id,
        "file_name": f"{drive_file_id}.pdf",
        "folder_path": "invoices",
        "status": status,
        "supplier_name": "Supplier",
        "invoice_number": f"INV-{drive_file_id}",
        "invoice_date": "22/08/2026",
        "total": 117.0,
    }
    values.update(overrides)
    return Document(**values)


def _service(*documents: Document) -> tuple[ApprovalService, MemoryRepository]:
    repository = MemoryRepository(*documents)
    return ApprovalService(repository, validation_rules=RULES), repository


@pytest.mark.parametrize("status", ["processed", "needs_review"])
def test_valid_structurally_eligible_document_is_approved(status: str) -> None:
    service, repository = _service(_document("one", status))

    result = service.approve("one")

    assert result.approved is True
    assert repository.documents["one"].status == "approved"
    assert len(repository.upsert_calls) == 1


@pytest.mark.parametrize("status", ["processed", "needs_review"])
def test_validation_blocker_rejects_single_approval(status: str) -> None:
    service, repository = _service(
        _document("one", status, invoice_number=None)
    )

    result = service.approve("one")

    assert result.approved is False
    assert result.reason_codes == ("required_missing",)
    assert repository.documents["one"].status == status
    assert repository.upsert_calls == []


@pytest.mark.parametrize("status", ["new", "failed", "skipped"])
def test_non_approvable_processing_status_is_rejected(status: str) -> None:
    service, repository = _service(_document("one", status))

    result = service.approve("one")

    assert result.approved is False
    assert result.reason_codes == ("status_not_approvable",)
    assert repository.upsert_calls == []


def test_already_approved_document_is_not_reapproved() -> None:
    service, repository = _service(_document("one", "approved"))

    result = service.approve("one")

    assert result.approved is False
    assert result.already_approved is True
    assert result.reason_codes == ("already_approved",)
    assert repository.upsert_calls == []


@pytest.mark.parametrize(
    "status, reason",
    [
        ("exported", "read_only_status"),
        ("confirmed_irrelevant", "terminal_status"),
        ("excluded", "read_only_status"),
    ],
)
def test_read_only_or_irrelevant_document_is_rejected(
    status: str, reason: str
) -> None:
    service, repository = _service(_document("one", status))

    result = service.approve("one")

    assert result.approved is False
    assert result.reason_codes == (reason,)
    assert repository.upsert_calls == []


def test_batch_all_valid_uses_one_bulk_persistence_operation() -> None:
    service, repository = _service(
        _document("one", "processed"),
        _document("two", "needs_review"),
    )

    result = service.approve_batch(["one", "two"])

    assert result.approved_ids == ("one", "two")
    assert result.plan.blocker_count == 0
    assert repository.upsert_calls == []
    assert len(repository.upsert_many_calls) == 1
    assert [doc.status for doc in repository.upsert_many_calls[0]] == [
        "approved",
        "approved",
    ]


def test_batch_one_validation_blocker_causes_zero_writes() -> None:
    one = _document("one")
    two = _document("two", invoice_number=None)
    service, repository = _service(one, two)

    result = service.approve_batch(["one", "two"])

    assert result.approved_ids == ()
    assert result.plan.blocker_ids == ("two",)
    assert result.plan.blocker_count == 1
    assert repository.upsert_calls == []
    assert repository.upsert_many_calls == []
    assert one.status == "processed"
    assert two.status == "processed"


def test_batch_mixed_valid_and_already_approved_skips_approved_document() -> None:
    service, repository = _service(
        _document("one"), _document("done", "approved")
    )

    result = service.approve_batch(["one", "done"])

    assert result.approved_ids == ("one",)
    assert result.plan.already_approved_ids == ("done",)
    assert [doc.drive_file_id for doc in repository.upsert_many_calls[0]] == ["one"]


def test_batch_blocker_still_reports_already_approved_without_writes() -> None:
    service, repository = _service(
        _document("blocked", invoice_number=None),
        _document("done", "approved"),
    )

    result = service.approve_batch(["blocked", "done"])

    assert result.approved_ids == ()
    assert result.plan.blocker_ids == ("blocked",)
    assert result.plan.already_approved_ids == ("done",)
    assert repository.upsert_many_calls == []


def test_otherwise_ineligible_ids_are_reported_separately() -> None:
    service, repository = _service(
        _document("valid"),
        _document("failed", "failed"),
    )

    result = service.approve_batch(["valid", "failed", "missing"])

    assert result.approved_ids == ("valid",)
    assert result.plan.blocker_ids == ()
    assert result.plan.ineligible_reasons == {
        "failed": ("status_not_approvable",),
        "missing": ("document_not_found",),
    }
    assert len(repository.upsert_many_calls) == 1


def test_batch_deduplicates_selected_ids_without_reapproval() -> None:
    service, repository = _service(_document("one"))

    result = service.approve_batch(["one", "one"])

    assert result.approved_ids == ("one",)
    assert len(repository.upsert_many_calls[0]) == 1


def test_batch_performs_complete_preflight_before_any_write() -> None:
    service, repository = _service(
        _document("one"), _document("two"), _document("three")
    )

    service.approve_batch(["one", "two", "three"])

    assert repository.events == [
        "get:one",
        "get:two",
        "get:three",
        "upsert_many",
    ]


def test_missing_single_document_is_reported_without_a_write() -> None:
    service, repository = _service()

    result = service.approve("missing")

    assert result.approved is False
    assert result.reason_codes == ("document_not_found",)
    assert repository.upsert_calls == []
