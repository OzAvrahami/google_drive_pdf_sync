"""Ground-truth regression for the bounded Phase 4 Shira supplier fix."""

from __future__ import annotations

import csv
from copy import deepcopy
from pathlib import Path

import pytest

import app.parsers.supplier_validator as supplier_validator
from app.parsers.invoice_parser import parse_invoice_text
from app.parsers.pdf_parser import extract_text_from_pdf
from app.services.pdf_corpus_service import correctness_for_record


CORPUS = Path(__file__).parent / "fixtures" / "pdf"
MANIFEST = CORPUS / "pdf_manifest.csv"
SHIRA_SHA256 = "a72ff621a74de820d3308fbec5f85d09e1b50be9cf1d227421bd64852eec2b46"


def _manifest_row() -> dict[str, str]:
    if not MANIFEST.is_file():
        pytest.skip("private real-PDF manifest not available locally")
    with MANIFEST.open(encoding="utf-8-sig", newline="") as stream:
        row = next(
            (
                item
                for item in csv.DictReader(stream)
                if item.get("sha256") == SHIRA_SHA256
            ),
            None,
        )
    if row is None:
        pytest.skip("private real-PDF fixture is not registered locally")
    return row


def test_shira_matches_human_verified_supplier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _manifest_row()
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
    assert row["reviewed"] == "true"
    assert parsed["business_name"] == row["expected_supplier"]
    assert correctness_for_record({"parser_result": parsed}, row)["supplier_correct"] is True
    assert parsed["invoice_date"] == row["expected_invoice_date"]
    assert str(parsed["invoice_number"]) == row["expected_invoice_number"]
    assert float(parsed["amount"]) == pytest.approx(float(row["expected_amount"]))
