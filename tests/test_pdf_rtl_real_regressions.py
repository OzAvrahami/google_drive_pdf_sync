"""Real digital-PDF regressions for mixed Hebrew/LTR token normalization."""

from pathlib import Path

import pytest

from app.parsers.invoice_parser import parse_invoice_text
from app.parsers.pdf_parser import extract_text_from_pdf


CORPUS = Path(__file__).parent / "fixtures" / "pdf"


def _fixture(folder: str, filename: str) -> Path:
    path = CORPUS / folder / filename
    if not path.is_file():
        pytest.skip("private real-PDF fixture not available locally")
    return path


def test_racheli_identifier_survives_production_normalization() -> None:
    path = _fixture("_unknown", "40039 רחלי רוימי- חשבון עסקה מרץ.pdf")

    text = extract_text_from_pdf(str(path))

    assert "עוסק פטור:308474246" in text
    assert "עוסק פטור:642474803" not in text


def test_bteen_numbers_survive_production_normalization() -> None:
    path = _fixture("_unknown", "6260004 ביטין- חשבון עסקה מרץ.pdf")

    text = extract_text_from_pdf(str(path))

    for expected in ("3,307.00", "595.26", "3,902.26", "516349982"):
        assert expected in text
    for corrupted in ("00.703,3", "62.595", "62.209,3", "289943615"):
        assert corrupted not in text

    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})
    assert parsed is not None
    assert parsed["document_type"] == "transaction_invoice"


def test_itm_work_dates_survive_production_normalization() -> None:
    path = _fixture("_unknown", "92804 סשא- חשבון עסקה מרץ.pdf")

    text = extract_text_from_pdf(str(path))

    assert "תאריך עבודה:01/03/2026" in text
    assert "תאריך עבודה:30/03/2026" in text
    assert "6202/30/10" not in text
    assert "6202/30/03" not in text

    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})
    assert parsed is not None
    assert parsed["document_type"] == "transaction_invoice"
