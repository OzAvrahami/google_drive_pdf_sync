"""Human-ground-truth regressions for Phase 1 parser accuracy fixes."""

from __future__ import annotations

import csv
from copy import deepcopy
from pathlib import Path

import pytest

import app.parsers.supplier_validator as supplier_validator
from app.parsers.invoice_parser import parse_invoice_text
from app.services.pdf_corpus_service import correctness_for_record
from app.parsers.pdf_parser import extract_text_from_pdf


CORPUS = Path(__file__).parent / "fixtures" / "pdf"
MANIFEST = CORPUS / "pdf_manifest.csv"

FOOTER_DATE_SHAS = (
    "629ef18fd3132854d2c3c279fee8f22679785123e99a09c51293b999b1cfc4b2",
    "3c28d85d90632615a1284148e44786407cbe1e7b1fed874a9834cf6debf6d409",
    "b97315c99077d8079888547b5d8174b80ff223d69426fd35344262518d903666",
    "884f063a33bcff9840c66f63a1439a1525ee860013a956eb50e8a92eacff799e",
    "08575c2f9a9a7601146917218355c8b21b943f85b562a48a5e677acc1a2a3a50",
    "b4b19e90a0394166f66289a4663c93858badd86cd90027950055402166fdd88f",
    "a72ff621a74de820d3308fbec5f85d09e1b50be9cf1d227421bd64852eec2b46",
)

SOURCE_MARKER_SHAS = (
    "e0b24b8c9c1c51a86134587462eedb9528f98d23c70520b575dd1ef27de4e773",
    "46f2a5c6b711e7aee511f8b79cc04132638d319a6a7f6e0a838a7cad03650212",
    "bb1930b74c8ec6209ec586fa6b50622f360edb056c80f75c4ead94719a262211",
    "b1087e7e9ac017521bd947d90244e39cf0928681842e5b6d7ba59c126c7e227d",
)


def test_supplier_correctness_allows_harmless_hebrew_quote_glyphs() -> None:
    result = correctness_for_record(
        {"parser_result": {"business_name": "חברת דוגמה בע״מ"}},
        {"reviewed": "true", "expected_supplier": 'חברת דוגמה בע"מ'},
    )

    assert result["supplier_correct"] is True


def _manifest_row(sha256: str) -> dict[str, str]:
    if not MANIFEST.is_file():
        pytest.skip("private real-PDF manifest not available locally")
    with MANIFEST.open(encoding="utf-8-sig", newline="") as stream:
        row = next(
            (item for item in csv.DictReader(stream) if item.get("sha256") == sha256),
            None,
        )
    if row is None:
        pytest.skip("private real-PDF fixture is not registered locally")
    return row


def _parse_manifest_pdf(
    sha256: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, str], dict]:
    row = _manifest_row(sha256)
    path = CORPUS / Path(row["relative_path"])
    if not path.is_file():
        pytest.skip("private real-PDF fixture not available locally")
    rules = deepcopy(supplier_validator._DEFAULT_BASE_RULES)
    rules["learned"] = []
    monkeypatch.setattr(supplier_validator, "_rules_cache", rules)
    parsed = parse_invoice_text(
        extract_text_from_pdf(str(path)),
        correction_map={"version": 1, "fields": {}},
    )
    assert parsed is not None
    return row, parsed


@pytest.mark.parametrize("sha256", FOOTER_DATE_SHAS)
def test_verified_business_date_precedes_generation_footer(
    sha256: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    row, parsed = _parse_manifest_pdf(sha256, monkeypatch)

    assert row["reviewed"] == "true"
    assert parsed["invoice_date"] == row["expected_invoice_date"]
    assert str(parsed["invoice_number"]) == row["expected_invoice_number"]
    assert float(parsed["amount"]) == pytest.approx(float(row["expected_amount"]))


@pytest.mark.parametrize("sha256", SOURCE_MARKER_SHAS)
def test_verified_supplier_wins_over_standalone_source_marker(
    sha256: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    row, parsed = _parse_manifest_pdf(sha256, monkeypatch)

    assert row["reviewed"] == "true"
    assert correctness_for_record({"parser_result": parsed}, row)["supplier_correct"] is True
    assert str(parsed["invoice_number"]) == row["expected_invoice_number"]
    assert float(parsed["amount"]) == pytest.approx(float(row["expected_amount"]))
