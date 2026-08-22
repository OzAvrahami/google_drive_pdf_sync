"""Characterization tests for the current duplicate-matching rules."""

from app.models.document import Document
from app.services.duplicate_detection_service import detect_and_mark_duplicate


class _StoreStub:
    def __init__(self, documents: list[Document]) -> None:
        self._documents = documents

    def all(self) -> list[Document]:
        return self._documents


def _document(drive_id: str, **overrides) -> Document:
    values = {
        "drive_file_id": drive_id,
        "file_name": f"{drive_id}.pdf",
        "folder_path": "invoices",
        "status": "processed",
        "supplier_name": "Example Supplier",
        "invoice_number": "INV-100",
        "invoice_date": "01/02/2026",
        "total": 250.0,
    }
    values.update(overrides)
    return Document(**values)


def test_exact_match_uses_supplier_number_and_compatible_date() -> None:
    existing = _document("existing", invoice_number="INV / 100")
    current = _document("current", invoice_number="inv-100")

    detect_and_mark_duplicate(current, _StoreStub([existing]))

    assert current.is_duplicate_suspected is True
    assert current.duplicate_confidence == "exact"
    assert current.suspected_duplicate_of == ["existing"]


def test_exact_number_match_is_rejected_when_both_dates_differ() -> None:
    existing = _document("existing", invoice_date="01/02/2026")
    current = _document("current", invoice_date="02/02/2026")

    detect_and_mark_duplicate(current, _StoreStub([existing]))

    assert current.is_duplicate_suspected is False
    assert current.suspected_duplicate_of is None


def test_exact_number_match_allows_one_missing_date() -> None:
    existing = _document("existing", invoice_date=None)
    current = _document("current", invoice_date="02/02/2026")

    detect_and_mark_duplicate(current, _StoreStub([existing]))

    assert current.duplicate_confidence == "exact"


def test_high_match_uses_supplier_date_and_amount_when_number_absent() -> None:
    existing = _document("existing", invoice_number=None, total=99.99)
    current = _document("current", invoice_number=None, total=99.99)

    detect_and_mark_duplicate(current, _StoreStub([existing]))

    assert current.is_duplicate_suspected is True
    assert current.duplicate_confidence == "high"
    assert current.suspected_duplicate_of == ["existing"]


def test_clearly_different_record_does_not_match() -> None:
    existing = _document("existing")
    current = _document(
        "current",
        supplier_name="Different Supplier",
        invoice_number=None,
        total=999.0,
    )

    detect_and_mark_duplicate(current, _StoreStub([existing]))

    assert current.is_duplicate_suspected is False


def test_candidate_in_new_status_is_not_eligible_for_comparison() -> None:
    existing = _document("existing", status="new")
    current = _document("current")

    detect_and_mark_duplicate(current, _StoreStub([existing]))

    assert current.is_duplicate_suspected is False


def test_current_document_is_not_compared_with_itself() -> None:
    current = _document("same-id")

    detect_and_mark_duplicate(current, _StoreStub([current]))

    assert current.is_duplicate_suspected is False
