"""
Tests for app.parsers.supplier_validator.

Covers:
  - is_probable_address  (address detection heuristics)
  - is_probable_supplier (supplier detection)
  - validate_supplier    (full pipeline: rejection, fallback, scoring)
  - _confidence          (updated weighted scorer in processing_service)
"""

import pytest
from app.parsers.supplier_validator import (
    is_probable_address,
    is_probable_supplier,
    validate_supplier,
)


# ─── is_probable_address ──────────────────────────────────────────────────────

class TestIsProbableAddress:

    def test_canonical_address_with_city(self):
        # "David Elazar 23, Herzliya" — the example from the bug report
        assert is_probable_address("דוד אלעזר 23, הרצליה") is True

    def test_street_number_comma_city(self):
        assert is_probable_address("רוטשילד 12, תל אביב") is True

    def test_hebrew_words_number_comma_city(self):
        assert is_probable_address("שדרות ירושלים 5, רחובות") is True

    def test_address_line_from_real_fixture(self):
        # Taken directly from the CHESHBON_ESEK_ICOUNT test fixture
        assert is_probable_address("ח.פ/ת.ז 515781219 יהודה הימית ,21 תל אביב - יפו") is True

    def test_clean_hebrew_name_is_not_address(self):
        assert is_probable_address("רועי זמיר") is False

    def test_company_with_be_am_is_not_address(self):
        assert is_probable_address('פריוריטי סופטוור בע"מ') is False

    def test_single_word_city_is_not_address(self):
        # A city name alone is NOT an address (no street/number context)
        assert is_probable_address("הרצליה") is False

    def test_empty_string_is_not_address(self):
        assert is_probable_address("") is False

    def test_english_name_is_not_address(self):
        assert is_probable_address("Microsoft Israel") is False

    def test_business_name_with_number_is_not_address(self):
        # A company name like "בית 1 לייעוץ" should NOT trigger address detection
        # (no comma + city pattern)
        assert is_probable_address("בית 1 לייעוץ") is False


# ─── is_probable_supplier ─────────────────────────────────────────────────────

class TestIsProbableSupplier:

    def test_company_with_be_am(self):
        assert is_probable_supplier('פריוריטי סופטוור בע"מ') is True

    def test_company_with_be_am_short(self):
        assert is_probable_supplier('היי ביז בע"מ') is True

    def test_clean_two_word_name(self):
        assert is_probable_supplier("רועי זמיר") is True

    def test_address_is_not_supplier(self):
        assert is_probable_supplier("דוד אלעזר 23, הרצליה") is False

    def test_empty_is_not_supplier(self):
        assert is_probable_supplier("") is False

    def test_none_is_not_supplier(self):
        # is_probable_supplier receives a str; passing empty string covers this
        assert is_probable_supplier("  ") is False


# ─── validate_supplier ────────────────────────────────────────────────────────

FULL_TEXT_WITH_COMPANY = """\
--- PAGE 1 ---
חברת בזק בינלאומי בע"מ
כתובת: יהודה הלוי 38, תל אביב
תאריך: 01/02/2026
חשבונית מס 12345
לכבוד: לקוח כלשהו
"""

FULL_TEXT_ADDRESS_ONLY = """\
--- PAGE 1 ---
דוד אלעזר 23, הרצליה
חשבון עסקה 40331
"""


class TestValidateSupplier:

    # ── Valid supplier passthrough ─────────────────────────────────────────────

    def test_valid_supplier_with_be_am_passes(self):
        result = validate_supplier('פריוריטי סופטוור בע"מ', FULL_TEXT_WITH_COMPANY)
        assert result.is_valid is True
        assert result.name == 'פריוריטי סופטוור בע"מ'
        assert result.fallback_used is False
        assert result.rejection_reason is None

    def test_valid_supplier_score_is_high(self):
        result = validate_supplier('חברת בזק בינלאומי בע"מ', FULL_TEXT_WITH_COMPANY)
        assert result.is_valid is True
        assert result.score >= 50

    # ── Address rejection ──────────────────────────────────────────────────────

    def test_address_is_rejected_and_original_reason_recorded(self):
        # When the original is an address but a fallback IS found, is_valid becomes
        # True (the document now has a valid supplier).  rejection_reason records why
        # the original candidate was replaced.
        result = validate_supplier("דוד אלעזר 23, הרצליה", FULL_TEXT_WITH_COMPANY)
        assert result.rejection_reason is not None
        assert "address" in result.rejection_reason.lower()
        assert result.triggered_rule is not None

    def test_address_rejection_records_address_score(self):
        result = validate_supplier("דוד אלעזר 23, הרצליה", FULL_TEXT_WITH_COMPANY)
        assert result.address_score >= 40

    def test_address_triggers_fallback_when_available(self):
        result = validate_supplier("דוד אלעזר 23, הרצליה", FULL_TEXT_WITH_COMPANY)
        # FULL_TEXT_WITH_COMPANY has "חברת בזק בינלאומי בע"מ" which should be found
        assert result.fallback_used is True
        assert result.name is not None
        assert "בע" in result.name   # found the company line

    def test_address_with_no_fallback_returns_none_name(self):
        result = validate_supplier("דוד אלעזר 23, הרצליה", FULL_TEXT_ADDRESS_ONLY)
        assert result.is_valid is False
        assert result.name is None
        assert result.fallback_used is False

    # ── None / empty candidate ─────────────────────────────────────────────────

    def test_none_candidate_attempts_fallback(self):
        result = validate_supplier(None, FULL_TEXT_WITH_COMPANY)
        # Should find the company line in the text
        assert result.fallback_used is True
        assert result.name is not None

    def test_none_candidate_in_sparse_text_returns_none(self):
        result = validate_supplier(None, "")
        assert result.name is None
        assert result.is_valid is False

    # ── Debug info ─────────────────────────────────────────────────────────────

    def test_debug_notes_are_populated(self):
        result = validate_supplier("דוד אלעזר 23, הרצליה", FULL_TEXT_WITH_COMPANY)
        assert isinstance(result.debug_notes, list)
        assert len(result.debug_notes) > 0

    def test_triggered_rule_set_on_address_rejection(self):
        result = validate_supplier("דוד אלעזר 23, הרצליה", FULL_TEXT_WITH_COMPANY)
        assert result.triggered_rule is not None

    # ── Score sanity ───────────────────────────────────────────────────────────

    def test_score_in_range(self):
        result = validate_supplier('היי ביז בע"מ', FULL_TEXT_WITH_COMPANY)
        assert 0 <= result.score <= 100

    def test_rejected_address_has_low_score(self):
        result = validate_supplier("דוד אלעזר 23, הרצליה", FULL_TEXT_ADDRESS_ONLY)
        assert result.score == 0   # rejected with no fallback → score 0


# ─── Integration: parse_invoice_text now includes supplier_validation ─────────

class TestParseInvoiceTextIncludesValidation:

    def test_result_has_supplier_validation_key(self):
        from app.parsers.invoice_parser import parse_invoice_text
        text = """\
--- PAGE 1 ---
חשבון עסקה 40331
חברת הדוגמה בע"מ
לכבוד: לקוח
03/02/2026
סה"כ לתשלום ₪7,500.00
הופק ב 03/02/2026 | חשבון עסקה 40331 | עמוד 1
"""
        result = parse_invoice_text(text)
        assert result is not None
        assert "supplier_validation" in result

    def test_supplier_validation_has_expected_keys(self):
        from app.parsers.invoice_parser import parse_invoice_text
        text = """\
--- PAGE 1 ---
חשבון עסקה 40331
חברת הדוגמה בע"מ
לכבוד: לקוח
03/02/2026
סה"כ לתשלום ₪7,500.00
הופק ב 03/02/2026 | חשבון עסקה 40331 | עמוד 1
"""
        result = parse_invoice_text(text)
        v = result["supplier_validation"]
        for key in ("original", "score", "is_valid", "rejection_reason",
                    "triggered_rule", "fallback_used", "address_score"):
            assert key in v, f"Missing key: {key}"


# ─── Integration: updated confidence scorer ───────────────────────────────────

class TestConfidenceScoring:

    def _make_parsed(self, **override) -> dict:
        """Build a minimal parsed dict with all fields found."""
        base = {
            "document_type": "tax_invoice",
            "business_name": 'חברת הדוגמה בע"מ',
            "invoice_date":  "01/02/2026",
            "invoice_number": "12345",
            "amount": 1000.0,
            "supplier_validation": {
                "score": 65,
                "is_valid": True,
                "fallback_used": False,
            },
        }
        base.update(override)
        return base

    def test_full_valid_result_has_high_confidence(self):
        from app.services.processing_service import _confidence
        parsed = self._make_parsed()
        assert _confidence(parsed) >= 0.75

    def test_address_supplier_lowers_confidence(self):
        from app.services.processing_service import _confidence
        parsed = self._make_parsed(
            business_name=None,
            supplier_validation={
                "score": 0,
                "is_valid": False,
                "fallback_used": False,
            },
        )
        # date + number + amount = 0.75, supplier = 0 → total 0.75
        # Supplier rejected adds nothing → confidence drops below perfect
        conf = _confidence(parsed)
        assert conf <= 0.75

    def test_no_parsed_returns_zero(self):
        from app.services.processing_service import _confidence
        assert _confidence(None) == 0.0

    def test_missing_fields_reduce_confidence(self):
        from app.services.processing_service import _confidence
        parsed = self._make_parsed(invoice_date=None, amount=None)
        conf = _confidence(parsed)
        assert conf < 0.75   # two base fields missing → below threshold
