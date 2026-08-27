from __future__ import annotations

from collections.abc import Iterator

import scripts.diagnose_pdf_batch as batch
import scripts.review_pdf_corpus as review


def _record(path: str = "_incoming/invoice.pdf", *, reviewed: bool = False) -> dict:
    return {
        "relative_path": path,
        "sha256": "a" * 64,
        "reviewed": reviewed,
        "source_detection": {"source_system": "Morning", "source_confidence": "high"},
        "parser_result": {
            "business_name": "Verified Supplier",
            "invoice_number": "08/010307",
            "invoice_date": "06/04/2026",
            "amount": 1770.0,
        },
        "confidence": 0.9,
        "status": "processed",
    }


def _row() -> dict[str, str]:
    row = {field: "" for field in batch.MANIFEST_FIELDS}
    row.update(
        {
            "filename": "invoice.pdf",
            "relative_path": "_incoming/invoice.pdf",
            "sha256": "a" * 64,
            "reviewed": "false",
        }
    )
    return row


def _inputs(values: list[str]):
    iterator: Iterator[str] = iter(values)
    return lambda _prompt: next(iterator)


def test_enter_explicitly_accepts_all_panda_values() -> None:
    updated = review.review_record(
        _row(),
        _record(),
        input_fn=_inputs(["", "", "", "", "y"]),
        output_fn=lambda _message: None,
    )

    assert updated is not None
    assert updated["reviewed"] == "true"
    assert updated["expected_supplier"] == "Verified Supplier"
    assert updated["expected_invoice_number"] == "08/010307"
    assert updated["expected_invoice_date"] == "06/04/2026"
    assert updated["expected_amount"] == "1770.00"


def test_typed_review_value_overrides_panda_without_changing_parser() -> None:
    record = _record()
    updated = review.review_record(
        _row(),
        record,
        input_fn=_inputs(["Correct Supplier", "92804", "31/03/2026", "7512.00", "yes"]),
        output_fn=lambda _message: None,
    )

    assert updated is not None
    assert updated["expected_supplier"] == "Correct Supplier"
    assert updated["expected_invoice_number"] == "92804"
    assert record["parser_result"]["invoice_number"] == "08/010307"


def test_abort_does_not_mark_document_reviewed() -> None:
    original = _row()

    updated = review.review_record(
        original,
        _record(),
        input_fn=_inputs(["q"]),
        output_fn=lambda _message: None,
    )

    assert updated is None
    assert original["reviewed"] == "false"


def test_review_queue_excludes_reviewed_by_default_and_supports_all() -> None:
    pending = _record("_incoming/pending.pdf")
    complete = _record("morning/complete.pdf", reviewed=True)

    assert review.select_review_records([complete, pending]) == [pending]
    assert review.select_review_records([complete, pending], include_all=True) == [pending, complete]


def test_new_only_limits_review_to_unreviewed_incoming() -> None:
    incoming = _record("_incoming/new.pdf")
    organized = _record("morning/unreviewed.pdf")

    selected = review.select_review_records([organized, incoming], new_only=True)

    assert selected == [incoming]


def test_file_selection_is_exact_and_can_include_reviewed() -> None:
    complete = _record("morning/complete.pdf", reviewed=True)

    selected = review.select_review_records(
        [complete], relative_path="morning/complete.pdf"
    )

    assert selected == [complete]


def test_missing_file_is_reported_clearly(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(review.batch, "analyze_corpus", lambda _root, _paths=None: [])
    output: list[str] = []

    result = review.run(
        tmp_path,
        relative_path="_incoming/missing.pdf",
        output_fn=output.append,
    )

    assert result == 1
    assert output == ["PDF not found in corpus: _incoming/missing.pdf"]
