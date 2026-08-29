"""Human-ground-truth regressions for Phase 5 document-date priority."""

from __future__ import annotations

import csv
from copy import deepcopy
from pathlib import Path

import pytest

import app.parsers.supplier_validator as supplier_validator
from app.parsers.invoice_parser import parse_invoice_text
from app.parsers.pdf_layout import apply_positional_supplier_override
from app.parsers.pdf_parser import extract_text_from_pdf
from app.services.pdf_corpus_service import correctness_for_record


CORPUS = Path(__file__).parent / "fixtures" / "pdf"
MANIFEST = CORPUS / "pdf_manifest.csv"

MORE_DAN_DATE_SHAS = (
    "cf15d077e50df9ea159fc7ae3626e44ebe0b94fece5e9fe4da474c8aa7fcc4b6",
    "4b6eda114d53ba373269a44dc5498cc54bd9691cfa0c071f5b1f340599860a1f",
    "e4224b6b09e7170f4d56f5170977dbab849ca618a71a66f7641a82be27d0e6c5",
)


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


@pytest.mark.parametrize("sha256", MORE_DAN_DATE_SHAS)
def test_structured_business_date_matches_human_ground_truth(
    sha256: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _manifest_row(sha256)
    path = CORPUS / Path(row["relative_path"])
    if not path.is_file():
        pytest.skip("private real-PDF fixture not available locally")

    rules = deepcopy(supplier_validator._DEFAULT_BASE_RULES)
    rules["learned"] = []
    monkeypatch.setattr(supplier_validator, "_rules_cache", rules)

    text = extract_text_from_pdf(str(path))
    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})
    assert parsed is not None
    apply_positional_supplier_override(parsed, text, pdf_path=path)

    correctness = correctness_for_record({"parser_result": parsed}, row)
    assert row["reviewed"] == "true"
    assert parsed["invoice_date"] == row["expected_invoice_date"]
    assert correctness["supplier_correct"] is True
    assert correctness["invoice_number_correct"] is True
    assert correctness["amount_correct"] is True
