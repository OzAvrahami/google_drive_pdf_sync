"""Classification-first regressions for real digital PDF variants."""

from pathlib import Path
from copy import deepcopy

import pytest

import app.parsers.supplier_validator as supplier_validator
from app.parsers.invoice_parser import classify_document_type, parse_invoice_text
from app.parsers.pdf_parser import extract_text_from_pdf
from app.services.processing_service import _confidence


CORPUS = Path(__file__).parent / "fixtures" / "pdf"


def _text(filename: str) -> str:
    matches = list(CORPUS.rglob(filename)) if CORPUS.is_dir() else []
    if not matches:
        pytest.skip("private real-PDF fixture not available locally")
    if len(matches) != 1:
        pytest.fail(f"private fixture filename is ambiguous: {filename}")
    path = matches[0]
    return extract_text_from_pdf(str(path))


def _use_base_supplier_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    rules = deepcopy(supplier_validator._DEFAULT_BASE_RULES)
    rules["learned"] = []
    monkeypatch.setattr(supplier_validator, "_rules_cache", rules)


def test_bteen_is_classified_from_normalized_document_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _text("6260004 ביטין- חשבון עסקה מרץ.pdf")

    assert "חשבונית עיסקה" in text
    assert classify_document_type(text) == "חשבון עסקה"

    _use_base_supplier_rules(monkeypatch)
    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})
    assert parsed is not None
    assert parsed["document_type"] == "transaction_invoice"
    assert parsed["business_name"] == "B.Teen Design. ltd"
    assert parsed["invoice_date"] == "10/04/2026"
    assert parsed["invoice_number"] == "6260004"
    assert parsed["amount"] == pytest.approx(3902.26)
    assert _confidence(parsed) == pytest.approx(0.86)


def test_itm_is_classified_from_normalized_document_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _text("92804 סשא- חשבון עסקה מרץ.pdf")

    assert "חשבונית עסקה מספר 92804" in text
    assert classify_document_type(text) == "חשבון עסקה"

    _use_base_supplier_rules(monkeypatch)
    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})
    assert parsed is not None
    assert parsed["document_type"] == "transaction_invoice"
    assert parsed["business_name"] == 'איי.טי.אם מודלס בע"מ'
    assert parsed["invoice_date"] == "31/03/2026"
    assert parsed["invoice_number"] == "92804"
    assert parsed["amount"] == pytest.approx(7512.00)
    assert _confidence(parsed) == pytest.approx(0.99)


def test_inbal_payment_request_ground_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _text("דרישת תשלום #1000 מאת ענבל - ענבל גלבר ליווי עסקי.pdf")

    _use_base_supplier_rules(monkeypatch)
    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})
    assert parsed is not None
    assert parsed["document_type"] == "payment_request"
    assert parsed["business_name"] == "ענבל גלבר ליווי עסקי"
    assert parsed["invoice_number"] == "1000"
    assert parsed["invoice_date"] == "12/04/2026"
    assert parsed["amount"] == pytest.approx(8850.00)
    assert _confidence(parsed) == pytest.approx(0.86)


def test_shilat_transaction_invoice_ground_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _text("שילת דדשי 1009  - חשבון עסקה מרץ .pdf")

    _use_base_supplier_rules(monkeypatch)
    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})
    assert parsed is not None
    assert parsed["document_type"] == "transaction_invoice"
    assert parsed["business_name"] == "שילת דדשי"
    assert parsed["invoice_number"] == "1009"
    assert parsed["invoice_date"] == "09/04/2026"
    assert parsed["amount"] == pytest.approx(1119.00)
    assert _confidence(parsed) == pytest.approx(0.86)


def test_avia_payment_request_ground_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _text("אביה הוכמן חודש מרץ דרישת תשלום 40011   .pdf")

    _use_base_supplier_rules(monkeypatch)
    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})
    assert parsed is not None
    assert parsed["document_type"] == "payment_request"
    assert parsed["business_name"] == "אביה הוכמן"
    assert parsed["invoice_number"] == "40011"
    assert parsed["invoice_date"] == "18/03/2026"
    assert parsed["amount"] == pytest.approx(7439.90)
    assert _confidence(parsed) == pytest.approx(0.86)


def test_yael_rotem_payment_request_ground_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _text("דרישת תשלום #1010 מאת יעל רותם.pdf")

    assert '802\nסה"כ כולל מע"מ ₪' in text

    _use_base_supplier_rules(monkeypatch)
    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})
    assert parsed is not None
    assert parsed["document_type"] == "payment_request"
    assert parsed["business_name"] == "יעל רותם"
    assert parsed["invoice_number"] == "1010"
    assert parsed["invoice_date"] == "29/01/2026"
    assert parsed["amount"] == pytest.approx(802.00)


def test_10307_charge_account_complete_ground_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _text("10307 או2או- חשבון עסקה מרץ.pdf")

    assert "חשבון חיוב מספר: 08/010307" in text
    assert classify_document_type(text) == "חשבון עסקה"

    _use_base_supplier_rules(monkeypatch)
    parsed = parse_invoice_text(text, correction_map={"version": 1, "fields": {}})
    assert parsed is not None
    assert parsed["document_type"] == "transaction_invoice"
    assert parsed["business_name"] == 'מ.ב.ר.נ אחזקות בע"מ'
    assert parsed["invoice_number"] == "08/010307"
    assert parsed["invoice_date"] == "06/04/2026"
    assert parsed["amount"] == pytest.approx(8260.00)
