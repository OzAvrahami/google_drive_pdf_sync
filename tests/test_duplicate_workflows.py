from __future__ import annotations

from copy import deepcopy
from unittest.mock import Mock

from app.application.duplicate_comparison_service import DuplicateComparisonService
from app.application.duplicate_resolution_service import DuplicateResolutionService
from app.application.irrelevant_service import IrrelevantResult
from app.models.document import Document
from app.services.duplicate_detection_service import detect_and_mark_duplicate
from app.ui.models.queue_policy import QueueRoute, route_for


class MemoryRepository:
    def __init__(self, *documents: Document, fail_upsert: bool = False) -> None:
        self.documents = {doc.drive_file_id: deepcopy(doc) for doc in documents}
        self.fail_upsert = fail_upsert
        self.upsert_calls = 0

    def get_by_drive_id(self, drive_file_id: str) -> Document | None:
        document = self.documents.get(drive_file_id)
        return deepcopy(document) if document else None

    def upsert(self, document: Document) -> None:
        self.upsert_calls += 1
        if self.fail_upsert:
            raise OSError("store failed")
        document.touch()
        self.documents[document.drive_file_id] = deepcopy(document)

    def upsert_many(self, documents: list[Document]) -> None:
        for document in documents:
            self.upsert(document)


def document(drive_id: str, **overrides) -> Document:
    values = {
        "drive_file_id": drive_id,
        "file_name": f"{drive_id}.pdf",
        "folder_path": "2026/invoices",
        "status": "processed",
        "supplier_name": "Example Supplier",
        "invoice_number": "INV-100",
        "invoice_date": "01/02/2026",
        "total": 250.0,
    }
    values.update(overrides)
    return Document(**values)


def suspected(current_id: str = "current", candidate_ids=None, confidence="exact", **overrides):
    result = document(current_id, **overrides)
    result.is_duplicate_suspected = True
    result.suspected_duplicate_of = candidate_ids or ["candidate"]
    result.duplicate_confidence = confidence
    return result


class TestDuplicateComparison:
    def test_exact_comparison_reuses_normalized_supplier_number_and_date(self) -> None:
        current = suspected(
            supplier_name=" Example   Supplier ",
            invoice_number="inv / 100",
        )
        candidate = document("candidate")
        repository = MemoryRepository(current, candidate)

        result = DuplicateComparisonService(repository).compare("current", "candidate")

        assert result.reason_code == "exact_supplier_number_date"
        assert result.field("supplier_name").matches is True
        assert result.field("invoice_number").matches is True
        assert result.field("invoice_date").matches is True
        assert result.field("total").participates_in_rule is False
        assert repository.upsert_calls == 0

    def test_high_comparison_marks_only_supplier_date_amount_as_participants(self) -> None:
        current = suspected(
            confidence="high", invoice_number=None, total=99.99
        )
        candidate = document("candidate", invoice_number=None, total=99.99)
        result = DuplicateComparisonService(MemoryRepository(current, candidate)).compare(
            "current", "candidate"
        )
        assert result.reason_code == "high_supplier_date_amount"
        assert result.field("supplier_name").participates_in_rule is True
        assert result.field("invoice_date").participates_in_rule is True
        assert result.field("total").participates_in_rule is True
        assert result.field("invoice_number").participates_in_rule is False

    def test_comparison_exposes_differing_and_missing_values(self) -> None:
        current = suspected(total=None, invoice_date=None)
        candidate = document(
            "candidate", total=500.0, invoice_date="02/02/2026", folder_path="archive"
        )
        result = DuplicateComparisonService(MemoryRepository(current, candidate)).compare(
            "current", "candidate"
        )
        assert result.field("total").matches is False
        assert result.field("invoice_date").matches is False
        assert result.field("folder_path").matches is False
        assert result.field("total").current_value is None

    def test_missing_candidate_is_explicit(self) -> None:
        result = DuplicateComparisonService(MemoryRepository(suspected())).compare(
            "current", "candidate"
        )
        assert result.candidate_available is False
        assert result.reason_code == "candidate_missing"

    def test_unlisted_candidate_is_not_compared(self) -> None:
        result = DuplicateComparisonService(
            MemoryRepository(suspected(), document("other"))
        ).compare("current", "other")
        assert result.reason_code == "candidate_not_suspected"
        assert result.fields == ()

    def test_multiple_persisted_candidate_ids_are_preserved_in_order(self) -> None:
        current = suspected(candidate_ids=["one", "missing", "two"])
        comparisons = DuplicateComparisonService(
            MemoryRepository(current, document("one"), document("two"))
        ).compare_all("current")
        assert [item.candidate_document_id for item in comparisons] == [
            "one",
            "missing",
            "two",
        ]
        assert [item.candidate_available for item in comparisons] == [True, False, True]


class TestDuplicateResolution:
    def service(self, repository: MemoryRepository, irrelevant=None):
        return DuplicateResolutionService(repository, irrelevant or Mock())

    def test_dismiss_clears_flags_once_without_changing_primary_status(self) -> None:
        repository = MemoryRepository(suspected())
        result = self.service(repository).dismiss("current")
        persisted = repository.get_by_drive_id("current")
        assert result.succeeded is True
        assert repository.upsert_calls == 1
        assert persisted.status == "processed"
        assert persisted.is_duplicate_suspected is False
        assert persisted.suspected_duplicate_of is None
        assert persisted.duplicate_confidence is None

    def test_dismiss_processed_reroutes_from_attention_to_ready(self) -> None:
        repository = MemoryRepository(suspected())
        assert route_for(repository.get_by_drive_id("current")) is QueueRoute.ATTENTION
        self.service(repository).dismiss("current")
        assert route_for(repository.get_by_drive_id("current")) is QueueRoute.READY

    def test_dismiss_needs_review_remains_attention(self) -> None:
        repository = MemoryRepository(suspected(status="needs_review"))
        self.service(repository).dismiss("current")
        assert route_for(repository.get_by_drive_id("current")) is QueueRoute.ATTENTION

    def test_dismissal_can_be_rediscovered_by_future_detection(self) -> None:
        repository = MemoryRepository(suspected(), document("candidate"))
        self.service(repository).dismiss("current")
        current = repository.get_by_drive_id("current")

        class Store:
            def all(self):
                return [repository.get_by_drive_id("candidate")]

        detect_and_mark_duplicate(current, Store())
        assert current.is_duplicate_suspected is True

    def test_dismiss_persistence_failure_does_not_mutate_source(self) -> None:
        repository = MemoryRepository(suspected(), fail_upsert=True)
        result = self.service(repository).dismiss("current")
        assert result.reason_code == "duplicate_persistence_failed"
        assert repository.get_by_drive_id("current").is_duplicate_suspected is True

    def test_stale_or_ineligible_document_is_blocked(self) -> None:
        repository = MemoryRepository(suspected(status="approved"))
        result = self.service(repository).dismiss("current")
        assert result.succeeded is False
        assert result.reason_code == "status_not_eligible"
        assert repository.upsert_calls == 0

    def test_confirm_requires_explicit_confirmation(self) -> None:
        repository = MemoryRepository(suspected(), document("candidate"))
        irrelevant = Mock()
        result = self.service(repository, irrelevant).confirm("current", "candidate")
        assert result.reason_code == "confirmation_required"
        irrelevant.mark_irrelevant.assert_not_called()

    def test_confirm_requires_resolvable_persisted_candidate(self) -> None:
        repository = MemoryRepository(suspected())
        irrelevant = Mock()
        result = self.service(repository, irrelevant).confirm(
            "current", "candidate", confirmed=True
        )
        assert result.reason_code == "candidate_missing"
        irrelevant.mark_irrelevant.assert_not_called()

    def test_confirm_uses_common_irrelevant_service_and_leaves_candidate_untouched(self) -> None:
        current = suspected()
        candidate = document("candidate", status="approved")
        repository = MemoryRepository(current, candidate)
        confirmed_document = deepcopy(current)
        confirmed_document.status = "confirmed_irrelevant"
        irrelevant_result = IrrelevantResult(
            True, "current", None, confirmed_document, store_updated=True
        )
        irrelevant = Mock()
        irrelevant.mark_irrelevant.return_value = irrelevant_result

        result = self.service(repository, irrelevant).confirm(
            "current", "candidate", confirmed=True
        )

        assert result.succeeded is True
        assert result.candidate_document.status == "approved"
        irrelevant.mark_irrelevant.assert_called_once()
        call = irrelevant.mark_irrelevant.call_args
        assert call.args == ("current",)
        assert call.kwargs["reason"].value == "confirmed_duplicate"
        assert repository.get_by_drive_id("candidate") == candidate

    def test_confirm_propagates_irrelevant_failure_without_false_success(self) -> None:
        repository = MemoryRepository(suspected(), document("candidate"))
        irrelevant = Mock()
        irrelevant.mark_irrelevant.return_value = IrrelevantResult(
            False,
            "current",
            "local_pdf_deletion_failed",
            repository.get_by_drive_id("current"),
            partial_failure=True,
        )
        result = self.service(repository, irrelevant).confirm(
            "current", "candidate", confirmed=True
        )
        assert result.succeeded is False
        assert result.reason_code == "local_pdf_deletion_failed"
        assert result.irrelevant_result.partial_failure is True
