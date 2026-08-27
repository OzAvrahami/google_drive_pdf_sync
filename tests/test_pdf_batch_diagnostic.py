from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import scripts.diagnose_pdf_batch as batch


def record(
    relative_path: str = "invoice.pdf",
    *,
    source: str = "Unknown",
    source_confidence: str = "unknown",
    status: str = "needs_review",
    parser_result: dict | None = None,
) -> dict:
    path = Path(relative_path)
    return {
        "filename": path.name,
        "relative_path": path.as_posix(),
        "metadata": {"Creator": "", "Producer": "", "xmp": {}},
        "pdf_engine": "Unknown",
        "source_detection": {
            "source_system": source,
            "source_confidence": source_confidence,
            "source_evidence": ["test evidence"],
            "conflicting": source == "Conflicting",
            "candidates": [],
        },
        "extraction_metrics": {
            "pages": 1,
            "raw_chars": 100,
            "meaningful_chars": 80,
            "native_text": True,
        },
        "rtl_diagnostics": batch.characterize_rtl("hello"),
        "layout_diagnostics": batch.analyze_layout([]),
        "parser_result": parser_result,
        "supplier_validation": None,
        "confidence": 0.5,
        "status": status,
        "warnings": [],
        "errors": {"extraction": None, "parser": None},
    }


def test_directory_scanning_is_recursive_and_pdf_only(tmp_path: Path) -> None:
    (tmp_path / "root.pdf").write_bytes(b"pdf")
    nested = tmp_path / "morning"
    nested.mkdir()
    (nested / "nested.PDF").write_bytes(b"pdf")
    (nested / "notes.txt").write_text("not a PDF", encoding="utf-8")

    paths = batch.scan_pdf_files(tmp_path)

    assert [path.relative_to(tmp_path).as_posix() for path in paths] == [
        "morning/nested.PDF",
        "root.pdf",
    ]


class FakeStream:
    def get_data(self) -> bytes:
        return b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><CreatorTool>Morning XMP</CreatorTool></x:xmpmeta>'


class FakePdf:
    metadata = {
        "Creator": "morning",
        "Producer": "mPDF 8.2.7",
        "CreationDate": "D:20260412",
    }

    class Doc:
        catalog = {"Metadata": FakeStream()}

    doc = Doc()


def test_metadata_and_xmp_are_collected() -> None:
    metadata, warnings = batch.collect_metadata(FakePdf())

    assert metadata["Creator"] == "morning"
    assert metadata["Producer"] == "mPDF 8.2.7"
    assert metadata["CreationDate"] == "D:20260412"
    assert metadata["xmp"]["CreatorTool"] == "Morning XMP"
    assert warnings == []


def test_missing_metadata_is_explicitly_empty() -> None:
    pdf = FakePdf()
    pdf.metadata = None
    pdf.doc = type("Doc", (), {"catalog": {}})()

    metadata, warnings = batch.collect_metadata(pdf)

    assert metadata["Creator"] == ""
    assert metadata["Producer"] == ""
    assert metadata["xmp"] == {}
    assert warnings == []


def test_source_detection_uses_strong_metadata_evidence() -> None:
    result = batch.detect_source_system({"Creator": "morning", "xmp": {}}, "")

    assert result.source_system == "Morning"
    assert result.source_confidence == "high"
    assert "Creator metadata" in result.source_evidence[0]


def test_source_detection_uses_explicit_text_branding() -> None:
    result = batch.detect_source_system(
        {"xmp": {}},
        "רוקמ - 10302 הקסע ןובשח iCount תועצמאב תילטיגיד םתחנו קפוה",
    )

    assert result.source_system == "iCount"
    assert result.source_confidence == "medium"


def test_source_detection_uses_explicit_rivhit_footer_as_high_confidence() -> None:
    result = batch.detect_source_system(
        {"xmp": {}},
        'מסמך זה הופק ע"י תוכנת ריווחית - ניהול עסקי www.rivhit.co.il',
    )

    assert result.source_system == "Rivhit"
    assert result.source_confidence == "high"
    assert any("rivhit.co.il" in evidence for evidence in result.source_evidence)


def test_source_detection_reports_conflicting_evidence() -> None:
    result = batch.detect_source_system(
        {"Creator": "morning", "xmp": {}},
        "באמצעות iCount",
    )

    assert result.source_system == "Conflicting"
    assert result.source_confidence == "low"
    assert result.conflicting is True
    assert result.candidates == ("Morning", "iCount")


def test_source_detection_prefers_unknown_to_supplier_inference() -> None:
    result = batch.detect_source_system(
        {"Author": "Morning Bakery Ltd", "xmp": {}},
        "Supplier: Morning Bakery Ltd",
    )

    assert result.source_system == "Unknown"
    assert result.source_confidence == "unknown"


def test_pdf_engine_is_separate_from_source_system() -> None:
    metadata = {"Creator": "morning", "Producer": "mPDF 8.2.7", "xmp": {}}

    assert batch.detect_source_system(metadata, "").source_system == "Morning"
    assert batch.detect_pdf_engine(metadata) == "mPDF"


def test_rtl_diagnostic_falls_back_to_unknown_without_strong_evidence() -> None:
    result = batch.characterize_rtl("מילים אקראיות ללא עוגנים מוכרים")

    assert result["pattern"] == "unknown"
    assert result["normalization_potentially_harmful"] is False


def test_rtl_diagnostic_identifies_known_visual_and_logical_anchors() -> None:
    visual = batch.characterize_rtl("תינובשח רפסמ םולשתל")
    logical = batch.characterize_rtl("חשבונית מספר לתשלום")

    assert visual["pattern"] == "visual_order"
    assert logical["pattern"] == "logical_order"
    assert logical["normalization_potentially_harmful"] is True


def test_rtl_diagnostic_clears_numeric_reversal_after_safe_normalization() -> None:
    result = batch.characterize_rtl('3,307.00:כ"הס')

    assert result["suspicious_numeric_reversals"] == 0
    assert result["normalization_potentially_harmful"] is False
    assert result["numeric_reversal_evidence"] == []


def test_layout_diagnostics_flag_repeated_wide_regions() -> None:
    words = []
    for row in range(5):
        top = row * 20
        words.extend(
            [
                {"text": "a", "x0": 10, "x1": 30, "top": top},
                {"text": "b", "x0": 180, "x1": 200, "top": top},
                {"text": "c", "x0": 350, "x1": 370, "top": top},
                {"text": "d", "x0": 520, "x1": 540, "top": top},
            ]
        )

    result = batch.analyze_layout([{"width": 600, "words": words}])

    assert "widely_separated_same_line_regions" in result["flags"]
    assert "possible_multi_column_layout" in result["flags"]
    assert "possible_table_layout" in result["flags"]


def test_csv_and_json_reports_are_machine_readable(tmp_path: Path) -> None:
    item = record(
        source="Morning",
        source_confidence="high",
        status="processed",
        parser_result={
            "document_type": "tax_invoice",
            "business_name": "ספק",
            "invoice_date": "12/04/2026",
            "invoice_number": "50008",
            "amount": 1770.0,
        },
    )
    csv_path = tmp_path / "benchmark.csv"
    json_path = tmp_path / "benchmark.json"
    batch.attach_manifest_state([item], [])

    batch.write_benchmark_reports([item], csv_path, json_path)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert csv_rows[0]["invoice_number"] == "50008"
    assert csv_rows[0]["supplier_correct"] == ""
    assert json_data["document_count"] == 1
    assert json_data["documents"][0]["parser_result"]["amount"] == 1770.0
    assert json_data["documents"][0]["supplier_correct"] is None


def test_manifest_defaults_reviewed_and_does_not_copy_parser_values(tmp_path: Path) -> None:
    manifest = tmp_path / "pdf_manifest.csv"
    item = record(
        parser_result={
            "business_name": "unreviewed parser supplier",
            "invoice_number": "999",
            "invoice_date": "01/01/2026",
            "amount": 42.0,
        }
    )

    batch.write_manifest([item], manifest)

    with manifest.open("r", encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["reviewed"] == "false"
    assert row["expected_supplier"] == ""
    assert row["expected_invoice_number"] == ""
    assert row["expected_invoice_date"] == ""
    assert row["expected_amount"] == ""


def test_manifest_does_not_infer_ground_truth_from_known_filename(tmp_path: Path) -> None:
    manifest = tmp_path / "pdf_manifest.csv"
    item = record("morning/shahar_gefen_invoice_apr_2026.pdf")

    batch.write_manifest([item], manifest)

    with manifest.open("r", encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["reviewed"] == "false"
    assert row["expected_invoice_number"] == ""
    assert row["expected_amount"] == ""
    assert row["expected_supplier"] == ""
    assert row["expected_invoice_date"] == ""


@pytest.mark.parametrize(
    ("source", "confidence", "expected_folder"),
    [
        ("Morning", "high", "morning"),
        ("iCount", "medium", "_review"),
        ("Unknown", "unknown", "_unknown"),
        ("Conflicting", "low", "_review"),
    ],
)
def test_organization_routes_by_source_confidence(
    tmp_path: Path,
    source: str,
    confidence: str,
    expected_folder: str,
) -> None:
    pdf = tmp_path / f"{source}.pdf"
    pdf.write_bytes(b"pdf")
    item = record(pdf.name, source=source, source_confidence=confidence)
    if source == "Conflicting":
        item["source_detection"]["conflicting"] = True

    move = batch.plan_organization(tmp_path, [item])[0]

    assert move.destination.parent.name == expected_folder
    assert move.conflict is None


def test_organization_detects_filename_collision_without_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"original")
    destination = tmp_path / "morning" / "invoice.pdf"
    destination.parent.mkdir()
    destination.write_bytes(b"existing")
    item = record("invoice.pdf", source="Morning", source_confidence="high")

    move = batch.plan_organization(tmp_path, [item])[0]

    assert move.conflict == "destination already exists"
    assert destination.read_bytes() == b"existing"
    assert source.read_bytes() == b"original"


def test_dry_run_makes_zero_filesystem_changes(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"unchanged")
    item = record("invoice.pdf", source="Morning", source_confidence="high")
    monkeypatch.setattr(batch, "analyze_corpus", lambda _root, _paths=None: [item])
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    result = batch.run(
        tmp_path,
        organize=True,
        dry_run=True,
        csv_path=tmp_path / "benchmark.csv",
        json_path=tmp_path / "benchmark.json",
    )

    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert result == 0
    assert after == before


def test_broken_pdf_does_not_abort_batch(tmp_path: Path, monkeypatch) -> None:
    good = tmp_path / "good.pdf"
    broken = tmp_path / "broken.pdf"
    good.write_bytes(b"good")
    broken.write_bytes(b"broken")
    monkeypatch.setattr(batch, "_prime_supplier_rules_read_only", lambda: None)
    monkeypatch.setattr(batch, "load_correction_map", lambda: {"version": 1, "fields": {}})

    def fake_analyze(path, root, **_kwargs):
        if path.name == "broken.pdf":
            raise ValueError("malformed")
        return record(path.relative_to(root).as_posix(), status="processed")

    monkeypatch.setattr(batch, "analyze_pdf", fake_analyze)

    records = batch.analyze_corpus(tmp_path)

    assert len(records) == 2
    failed = next(item for item in records if item["filename"] == "broken.pdf")
    assert failed["status"] == "failed"
    assert "malformed" in failed["errors"]["extraction"]


def test_apply_organization_moves_each_pdf_once_without_changing_bytes(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first.write_bytes(b"first bytes")
    second.write_bytes(b"second bytes")
    records = [
        record("first.pdf", source="Morning", source_confidence="high"),
        record("second.pdf", source="Unknown", source_confidence="unknown"),
    ]
    moves = batch.plan_organization(tmp_path, records)

    assert batch.validate_organization_plan(tmp_path, records, moves) == []
    assert batch.apply_organization(tmp_path, moves) == 2
    assert (tmp_path / "morning" / "first.pdf").read_bytes() == b"first bytes"
    assert (tmp_path / "_unknown" / "second.pdf").read_bytes() == b"second bytes"
    assert len(list(tmp_path.rglob("*.pdf"))) == 2


def test_manifest_initializes_with_sha_size_and_blank_ground_truth(tmp_path: Path) -> None:
    manifest = tmp_path / "pdf_manifest.csv"
    item = record("_incoming/new.pdf", parser_result={"business_name": "Panda value"})
    item["sha256"] = "a" * 64
    item["file_size"] = 321

    rows = batch.write_manifest([item], manifest)

    assert rows[0]["sha256"] == "a" * 64
    assert rows[0]["file_size"] == "321"
    assert rows[0]["reviewed"] == "false"
    assert rows[0]["expected_supplier"] == ""


def test_manifest_keeps_one_row_per_unique_sha(tmp_path: Path) -> None:
    first = record("_incoming/first.pdf")
    second = record("_incoming/copy.pdf")
    first.update({"sha256": "c" * 64, "file_size": 5})
    second.update({"sha256": "c" * 64, "file_size": 5})

    rows = batch.write_manifest([first, second], tmp_path / "pdf_manifest.csv")

    assert len(rows) == 1


def test_manifest_preserves_review_by_sha_after_rename(tmp_path: Path) -> None:
    manifest = tmp_path / "pdf_manifest.csv"
    digest = "b" * 64
    old = record("_incoming/renamed.pdf")
    old.update({"sha256": digest, "file_size": 7})
    rows = batch.write_manifest([old], manifest)
    rows[0]["reviewed"] = "true"
    rows[0]["expected_invoice_number"] = "08/010307"
    batch.atomic_write_manifest(rows, manifest)

    moved = record("rivhit/renamed.pdf")
    moved.update({"sha256": digest, "file_size": 7})
    updated = batch.write_manifest([moved], manifest)

    assert len(updated) == 1
    assert updated[0]["relative_path"] == "rivhit/renamed.pdf"
    assert updated[0]["reviewed"] == "true"
    assert updated[0]["expected_invoice_number"] == "08/010307"


def test_discovery_recognizes_renamed_existing_pdf_by_sha(tmp_path: Path) -> None:
    pdf = tmp_path / "renamed.pdf"
    pdf.write_bytes(b"same invoice bytes")
    digest = batch.sha256_file(pdf)
    manifest_rows = [{field: "" for field in batch.MANIFEST_FIELDS}]
    manifest_rows[0].update(
        {"filename": "old.pdf", "relative_path": "morning/old.pdf", "sha256": digest}
    )

    paths, duplicates, identities = batch.discover_unique_pdfs(tmp_path, manifest_rows)

    assert paths == [pdf]
    assert duplicates == []
    assert identities[pdf][0] == digest
    by_sha, _by_path = batch.manifest_indexes(manifest_rows)
    assert digest in by_sha


def test_duplicate_sha_is_reported_and_existing_path_is_canonical(tmp_path: Path) -> None:
    existing = tmp_path / "morning" / "original.pdf"
    incoming = tmp_path / "_incoming" / "copy.pdf"
    existing.parent.mkdir()
    incoming.parent.mkdir()
    existing.write_bytes(b"identical")
    incoming.write_bytes(b"identical")
    digest = batch.sha256_file(existing)
    manifest_rows = [{field: "" for field in batch.MANIFEST_FIELDS}]
    manifest_rows[0].update(
        {"filename": existing.name, "relative_path": "morning/original.pdf", "sha256": digest}
    )

    paths, duplicates, _identities = batch.discover_unique_pdfs(tmp_path, manifest_rows)

    assert paths == [existing]
    assert duplicates == [batch.DuplicatePdf(incoming, existing, digest)]
    assert incoming.exists()


def test_new_only_snapshot_keeps_new_and_unreviewed_incoming_visible() -> None:
    new = record("morning/new.pdf")
    new.update({"sha256": "new", "reviewed": False})
    incoming = record("_incoming/staged.pdf")
    incoming.update({"sha256": "known", "reviewed": False})
    old = record("morning/old.pdf")
    old.update({"sha256": "old", "reviewed": False})

    selected = batch.select_new_records([old, incoming, new], {"new"})

    assert [item["relative_path"] for item in selected] == ["_incoming/staged.pdf", "morning/new.pdf"]


def test_empty_corpus_initializes_manifest_and_reports_zero(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(batch, "analyze_corpus", lambda _root, _paths=None: [])

    result = batch.run(
        tmp_path,
        csv_path=tmp_path / "benchmark.csv",
        json_path=tmp_path / "benchmark.json",
    )

    assert result == 0
    assert (tmp_path / "pdf_manifest.csv").is_file()
    assert json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))["document_count"] == 0
    assert "PDFs analyzed: 0" in capsys.readouterr().out


def test_aggregate_report_separates_native_and_non_native_results(capsys) -> None:
    native = record("native.pdf", status="processed")
    non_native = record("scan.pdf", status="needs_review")
    non_native["extraction_metrics"]["native_text"] = False

    aggregate = batch.aggregate_statistics([native, non_native])
    batch.print_aggregate_report([native, non_native])

    assert aggregate["native_digital_count"] == 1
    assert aggregate["non_native_count"] == 1
    assert aggregate["native_digital_status"] == {"processed": 1}
    assert aggregate["non_native_status"] == {"needs_review": 1}
    output = capsys.readouterr().out
    assert "Native digital PDFs: 1" in output
    assert "Non-native / no meaningful text: 1" in output
    assert "Native digital operational result" in output
    assert "Non-native operational result" in output


def test_atomic_manifest_replace_failure_preserves_original(tmp_path: Path, monkeypatch) -> None:
    manifest = tmp_path / "pdf_manifest.csv"
    manifest.write_bytes(b"original manifest")
    monkeypatch.setattr(batch.os, "replace", lambda *_args: (_ for _ in ()).throw(PermissionError("locked")))

    with pytest.raises(batch.ManifestWriteError, match="Close Excel"):
        batch.atomic_write_manifest([], manifest)

    assert manifest.read_bytes() == b"original manifest"
    assert list(tmp_path.glob("*.tmp")) == []


def test_incoming_organization_updates_manifest_path_and_preserves_sha(tmp_path: Path) -> None:
    incoming = tmp_path / "_incoming" / "invoice.pdf"
    incoming.parent.mkdir()
    incoming.write_bytes(b"private invoice")
    digest = batch.sha256_file(incoming)
    item = record("_incoming/invoice.pdf", source="Morning", source_confidence="high")
    item.update({"sha256": digest, "file_size": incoming.stat().st_size})
    moves = batch.plan_organization(tmp_path, [item])

    assert batch.validate_organization_plan(tmp_path, [item], moves) == []
    assert batch.apply_organization(tmp_path, moves) == 1
    batch.update_record_paths_after_organization(tmp_path, [item], moves)
    rows = batch.write_manifest([item], tmp_path / "pdf_manifest.csv")

    destination = tmp_path / "morning" / "invoice.pdf"
    assert destination.is_file()
    assert batch.sha256_file(destination) == digest
    assert rows[0]["relative_path"] == "morning/invoice.pdf"


def test_reviewed_accuracy_uses_only_reviewed_documents() -> None:
    reviewed = record(
        parser_result={
            "business_name": "חברה בע''מ",
            "invoice_number": "08/010307",
            "invoice_date": "06.04.2026",
            "amount": 8260.0,
        }
    )
    manifest = {field: "" for field in batch.MANIFEST_FIELDS}
    manifest.update(
        {
            "reviewed": "true",
            "expected_supplier": 'חברה בע"מ',
            "expected_invoice_number": "08/010307",
            "expected_invoice_date": "06/04/2026",
            "expected_amount": "8260.00",
        }
    )
    reviewed.update(batch.correctness_for_record(reviewed, manifest))
    reviewed["reviewed"] = True
    unreviewed = record(parser_result={"business_name": "wrong"})
    unreviewed.update(batch.correctness_for_record(unreviewed, None))
    unreviewed["reviewed"] = False

    accuracy = batch.verified_accuracy([reviewed, unreviewed])

    assert reviewed["fully_correct"] is True
    assert unreviewed["supplier_correct"] is None
    assert accuracy["reviewed"] == 1
    assert accuracy["fully_correct"] == 1


def test_invoice_number_accuracy_preserves_leading_zeroes_and_slash() -> None:
    item = record(parser_result={"invoice_number": "10307"})
    manifest = {field: "" for field in batch.MANIFEST_FIELDS}
    manifest.update({"reviewed": "true", "expected_invoice_number": "08/010307"})

    result = batch.correctness_for_record(item, manifest)

    assert result["invoice_number_correct"] is False


def test_private_data_is_ignored_but_tooling_is_trackable() -> None:
    root = Path(__file__).resolve().parents[1]

    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", "tests/fixtures/pdf/_incoming/private.pdf", "tests/fixtures/pdf/pdf_manifest.csv", "artifacts/pdf_benchmark.json"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    script = subprocess.run(
        ["git", "check-ignore", "--no-index", "scripts/diagnose_pdf_batch.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert ignored.returncode == 0
    assert script.returncode == 1
