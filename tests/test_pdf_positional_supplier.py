"""Production integration regressions for positional supplier resolution."""

from __future__ import annotations

import csv
from copy import deepcopy
from pathlib import Path

import pytest

import app.parsers.supplier_validator as supplier_validator
from app.parsers.invoice_parser import parse_invoice_text
from app.parsers.pdf_layout import (
    apply_positional_supplier_override,
    has_positional_supplier_ambiguity,
)
from app.parsers.pdf_parser import extract_text_from_pdf
from app.services.pdf_corpus_service import correctness_for_record


CORPUS = Path(__file__).parent / "fixtures" / "pdf"
MANIFEST = CORPUS / "pdf_manifest.csv"

POSITIONAL_TARGET_SHAS = (
    "1b6d3ec465fc76547797be2aed7256f6d9e15fda0f04f20f643a52a06478e351",
    "cf15d077e50df9ea159fc7ae3626e44ebe0b94fece5e9fe4da474c8aa7fcc4b6",
    "4b6eda114d53ba373269a44dc5498cc54bd9691cfa0c071f5b1f340599860a1f",
    "e4224b6b09e7170f4d56f5170977dbab849ca618a71a66f7641a82be27d0e6c5",
    "777845dfbfd3cd3c6fa33ed2ce54482a986cc1ed3891aea529ef2c75598f307d",
)

POSITIONAL_NEGATIVE_CONTROL_SHAS = (
    # Latin issuer in the same Morning/mPDF family.
    "629ef18fd3132854d2c3c279fee8f22679785123e99a09c51293b999b1cfc4b2",
    # Hebrew personal and legal-entity issuers.
    "03a12fc0a446c5dfa9f205a3f01c9a281cb6bf4ceccb3014b3ce150f1566a3cf",
    "08575c2f9a9a7601146917218355c8b21b943f85b562a48a5e677acc1a2a3a50",
    "b4b19e90a0394166f66289a4663c93858badd86cd90027950055402166fdd88f",
    # Phase 4 source-prefix issuer.
    "a72ff621a74de820d3308fbec5f85d09e1b50be9cf1d227421bd64852eec2b46",
    # Other source/template controls.
    "874f91f62fd7847b18b0169ce9645c1bd1e87b013c9c7680ec400f9210c92256",
    "df63fea9a07ae5208e55ca7b90a30b7f57f6c9405fa2832c9d594502ce87025f",
    "213eba333d41e258a88573153efcd46f43794e5334f27f948fc010a5eef1d53e",
    # Single-token Hebrew supplier.
    "efd18c4e21fce102ce2eeb47c611ddc3e8281b4f56619c63bbda4897702c21f6",
)


def _manifest_rows() -> dict[str, dict[str, str]]:
    if not MANIFEST.is_file():
        pytest.skip("private real-PDF manifest not available locally")
    with MANIFEST.open(encoding="utf-8-sig", newline="") as stream:
        return {
            row["sha256"]: row
            for row in csv.DictReader(stream)
            if row.get("sha256")
        }


def _fixture(sha256: str) -> tuple[dict[str, str], Path]:
    row = _manifest_rows().get(sha256)
    if row is None:
        pytest.skip("private real-PDF fixture is not registered locally")
    path = CORPUS / Path(row["relative_path"])
    if not path.is_file():
        pytest.skip("private real-PDF fixture not available locally")
    return row, path


@pytest.fixture(autouse=True)
def stable_supplier_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    rules = deepcopy(supplier_validator._DEFAULT_BASE_RULES)
    rules["learned"] = []
    monkeypatch.setattr(supplier_validator, "_rules_cache", rules)


@pytest.mark.parametrize("sha256", POSITIONAL_TARGET_SHAS)
def test_verified_positional_target_uses_ground_truth_supplier(sha256: str) -> None:
    row, path = _fixture(sha256)
    text = extract_text_from_pdf(str(path))
    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})
    assert parsed is not None
    before = deepcopy(parsed)

    resolution = apply_positional_supplier_override(parsed, text, pdf_path=path)

    assert before["business_name"] != row["expected_supplier"]
    assert resolution is not None
    assert resolution.before_supplier == before["business_name"]
    assert resolution.after_supplier == row["expected_supplier"]
    assert parsed["business_name"] == row["expected_supplier"]
    assert parsed["supplier_validation"]["is_valid"] is True
    assert parsed["supplier_validation"]["fallback_used"] is False
    assert correctness_for_record({"parser_result": parsed}, row)["supplier_correct"] is True
    for field in ("document_type", "invoice_date", "invoice_number", "amount"):
        assert parsed[field] == before[field]


@pytest.mark.parametrize("sha256", POSITIONAL_TARGET_SHAS)
def test_text_preflight_retains_verified_positional_target(sha256: str) -> None:
    _row, path = _fixture(sha256)
    text = extract_text_from_pdf(str(path))
    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})

    assert parsed is not None
    assert has_positional_supplier_ambiguity(text, parsed["business_name"]) is True


@pytest.mark.parametrize("sha256", POSITIONAL_NEGATIVE_CONTROL_SHAS)
def test_verified_correct_supplier_is_not_overridden(sha256: str) -> None:
    row, path = _fixture(sha256)
    text = extract_text_from_pdf(str(path))
    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})
    assert parsed is not None
    assert correctness_for_record({"parser_result": parsed}, row)["supplier_correct"] is True
    before = deepcopy(parsed)

    resolution = apply_positional_supplier_override(parsed, text, pdf_path=path)

    assert resolution is None
    assert parsed == before


@pytest.mark.parametrize("sha256", POSITIONAL_NEGATIVE_CONTROL_SHAS)
def test_text_preflight_rejects_verified_correct_supplier(sha256: str) -> None:
    _row, path = _fixture(sha256)
    text = extract_text_from_pdf(str(path))
    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})

    assert parsed is not None
    assert has_positional_supplier_ambiguity(text, parsed["business_name"]) is False


def test_text_preflight_requires_supplier_on_next_substantive_addressee_row() -> None:
    text = (
        "לכבוד: ספק שנמצא בצד הנגדי\n"
        "לקוח ממוזג BRAND\n"
        "עוסק מורשה 123456789\n"
        "ח.פ/ת.ז 987654321\n"
        "חשבון עסקה 1000\n"
    )

    assert has_positional_supplier_ambiguity(text, "לקוח ממוזג BRAND") is True
    assert has_positional_supplier_ambiguity(text, "ספק שנמצא בצד הנגדי") is False


def test_skipped_document_cannot_receive_positional_supplier_override() -> None:
    assert apply_positional_supplier_override(
        None,
        "לכבוד פנדה הום עוסק מורשה ח.פ/ת.ז",
        pages=[{"page": 1, "width": 595.0, "height": 842.0, "words": []}],
    ) is None


def test_missing_text_signals_do_not_open_pdf_or_change_supplier(tmp_path: Path) -> None:
    parsed = {
        "business_name": "Existing Supplier",
        "supplier_validation": {"score": 40, "is_valid": True},
    }
    before = deepcopy(parsed)

    resolution = apply_positional_supplier_override(
        parsed,
        "ordinary invoice text without the required two-sided header signals",
        pdf_path=tmp_path / "not-a-real.pdf",
    )

    assert resolution is None
    assert parsed == before
