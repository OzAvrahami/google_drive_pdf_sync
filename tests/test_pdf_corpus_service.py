from __future__ import annotations

import csv
from pathlib import Path

import pytest

import app.services.pdf_corpus_service as corpus


def _analyzer(path: Path, root: Path) -> dict:
    return {
        "filename": path.name,
        "relative_path": path.relative_to(root).as_posix(),
        "parser_result": {
            "business_name": "Panda Supplier",
            "invoice_number": "08/010307",
            "invoice_date": "06/04/2026",
            "amount": 8260.0,
        },
        "source_detection": {
            "source_system": "Morning",
            "source_confidence": "high",
            "source_evidence": ["synthetic test"],
        },
        "extraction_metrics": {"native_text": True, "meaningful_chars": 100},
        "confidence": 0.9,
        "status": "processed",
        "errors": {"extraction": None, "parser": None},
        "warnings": [],
    }


def _service(tmp_path: Path, name: str = "invoice.pdf") -> tuple[corpus.PdfCorpusService, str]:
    pdf = tmp_path / name
    pdf.write_bytes(b"synthetic private pdf identity")
    service = corpus.PdfCorpusService(
        tmp_path,
        benchmark_path=tmp_path / "missing-benchmark.json",
        analyzer=_analyzer,
    )
    records = service.reload()
    return service, str(records[0]["sha256"])


def test_zero_corpus_loads_without_manifest_or_fake_records(tmp_path: Path) -> None:
    service = corpus.PdfCorpusService(tmp_path, benchmark_path=tmp_path / "missing.json")

    assert service.reload() == ()
    assert service.accuracy()["reviewed"] == 0
    assert not service.manifest_path.exists()


def test_everything_correct_is_explicit_and_persists_all_panda_values(tmp_path: Path) -> None:
    service, digest = _service(tmp_path)

    assert service.record_by_sha(digest)["reviewed"] is False
    saved = service.everything_correct(digest)

    assert saved["reviewed"] is True
    assert saved["expected_supplier"] == "Panda Supplier"
    assert saved["expected_invoice_number"] == "08/010307"
    assert saved["expected_invoice_date"] == "06/04/2026"
    assert saved["expected_amount"] == "8260.00"
    assert saved["fully_correct"] is True


def test_manual_correction_records_mismatch_without_changing_panda_result(tmp_path: Path) -> None:
    service, digest = _service(tmp_path)
    analyzed = service.analyze(digest)

    saved = service.save_review(
        digest,
        {
            "expected_supplier": "Correct Supplier",
            "expected_invoice_number": "92804",
            "expected_invoice_date": "06/04/2026",
            "expected_amount": "8260.00",
        },
    )

    assert saved["parser_result"] == analyzed["parser_result"]
    assert saved["supplier_correct"] is False
    assert saved["invoice_number_correct"] is False
    assert saved["fully_correct"] is False
    assert service.filtered_records(review_state="mismatches") == [saved]


def test_intentional_blank_is_distinct_from_unreviewed(tmp_path: Path) -> None:
    service, digest = _service(tmp_path)
    service.analyze(digest)

    saved = service.save_review(
        digest,
        {
            "expected_supplier": "",
            "expected_invoice_number": "08/010307",
            "expected_invoice_date": "06/04/2026",
            "expected_amount": "8260.00",
        },
    )

    assert saved["reviewed"] is True
    assert saved["expected_supplier"] == ""
    assert saved["supplier_correct"] is False


def test_review_filters_and_sorting_use_shared_record_state(tmp_path: Path) -> None:
    first = tmp_path / "zeta.pdf"
    second = tmp_path / "alpha.pdf"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    service = corpus.PdfCorpusService(
        tmp_path,
        benchmark_path=tmp_path / "missing.json",
        analyzer=_analyzer,
    )
    records = service.reload()
    for record in records:
        service.analyze(str(record["sha256"]))
    digest = str(service.records[0]["sha256"])
    service.everything_correct(digest)

    assert len(service.filtered_records(review_state="reviewed")) == 1
    assert len(service.filtered_records(review_state="unreviewed")) == 1
    assert [record["filename"] for record in service.filtered_records(sort_by="filename")] == [
        "alpha.pdf",
        "zeta.pdf",
    ]


def test_sha_identity_preserves_review_after_path_change(tmp_path: Path) -> None:
    service, digest = _service(tmp_path)
    service.everything_correct(digest)
    source = tmp_path / "invoice.pdf"
    destination = tmp_path / "morning" / "renamed.pdf"
    destination.parent.mkdir()
    source.rename(destination)

    records = service.reload()

    assert len(records) == 1
    assert records[0]["sha256"] == digest
    assert records[0]["relative_path"] == "morning/renamed.pdf"
    assert records[0]["reviewed"] is True


def test_atomic_manifest_failure_preserves_original(tmp_path: Path, monkeypatch) -> None:
    manifest = tmp_path / "pdf_manifest.csv"
    manifest.write_bytes(b"original")
    monkeypatch.setattr(corpus.os, "replace", lambda *_args: (_ for _ in ()).throw(PermissionError("locked")))

    with pytest.raises(corpus.ManifestWriteError, match="Close Excel"):
        corpus.atomic_write_manifest([], manifest)

    assert manifest.read_bytes() == b"original"
    assert list(tmp_path.glob("*.tmp")) == []


def test_manifest_save_keeps_one_row_for_sha(tmp_path: Path) -> None:
    service, digest = _service(tmp_path)
    service.everything_correct(digest)
    service.save_review(digest, {field: "" for field, _label, _parser in corpus.REVIEW_FIELDS})

    with service.manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["sha256"] == digest
