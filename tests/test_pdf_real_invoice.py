"""Characterization of Panda's current pipeline on a real digital invoice."""

from pathlib import Path
from copy import deepcopy

import pytest

import app.parsers.supplier_validator as supplier_validator
from app.parsers.invoice_parser import parse_invoice_text
from app.parsers.pdf_parser import extract_text_from_pdf
from app.services.processing_service import _confidence


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "pdf"
    / "morning"
    / "shahar_gefen_invoice_apr_2026.pdf"
)


@pytest.fixture
def shahar_gefen_invoice() -> Path:
    if not FIXTURE.is_file():
        pytest.skip("private real-PDF fixture not available locally")
    return FIXTURE


def test_shahar_gefen_april_2026_current_production_pipeline(
    shahar_gefen_invoice: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protect known values without pretending subtotal/VAT are parsed today."""
    rules = deepcopy(supplier_validator._DEFAULT_BASE_RULES)
    rules["learned"] = []
    monkeypatch.setattr(supplier_validator, "_rules_cache", rules)

    text = extract_text_from_pdf(str(shahar_gefen_invoice))
    parsed = parse_invoice_text(
        text,
        correction_map={"version": 1, "fields": {}},
    )

    assert parsed is not None
    assert parsed["invoice_number"] == "50008"
    assert parsed["amount"] == pytest.approx(1770.00)

    # Known source values: subtotal=1500.00 and VAT=270.00.  The current
    # production parser has no subtotal/VAT output keys, so this deliberately
    # characterizes that limitation instead of inventing extraction behavior.
    assert "subtotal" not in parsed
    assert "vat" not in parsed
    assert 0.0 <= _confidence(parsed) <= 1.0
