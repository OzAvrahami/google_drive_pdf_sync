"""
Unit tests for app.utils.text_helpers — Hebrew RTL normalization.

Each test is named for the scenario it covers so failures are self-describing.
Run from the project root:  pytest tests/test_text_helpers.py -v
"""

import pytest
from app.utils.text_helpers import _fix_rtl_line, normalize_rtl_text


# ---------------------------------------------------------------------------
# _fix_rtl_line
# ---------------------------------------------------------------------------

class TestFixRtlLine:

    # --- pass-through cases -------------------------------------------------

    def test_empty_string_unchanged(self):
        assert _fix_rtl_line("") == ""

    def test_pure_ltr_ascii_unchanged(self):
        assert _fix_rtl_line("hello world") == "hello world"

    def test_digits_only_unchanged(self):
        assert _fix_rtl_line("12345") == "12345"

    def test_date_only_unchanged(self):
        assert _fix_rtl_line("02/02/2026") == "02/02/2026"

    def test_currency_only_unchanged(self):
        assert _fix_rtl_line("₪2,921.68") == "₪2,921.68"

    def test_email_only_unchanged(self):
        assert _fix_rtl_line("user@example.com") == "user@example.com"

    def test_page_separator_unchanged(self):
        assert _fix_rtl_line("--- PAGE 1 ---") == "--- PAGE 1 ---"

    # --- core Hebrew reversal cases -----------------------------------------

    def test_single_hebrew_word_reversed(self):
        # "דובכל" is "לכבוד" (To the honorable) stored in visual order
        assert _fix_rtl_line("דובכל") == "לכבוד"

    def test_multi_word_hebrew_phrase(self):
        # Each word's chars reversed AND word order reversed
        assert _fix_rtl_line('מ"עב םוה הדנפ') == 'פנדה הום בע"מ'

    def test_hebrew_word_with_backslash_quote(self):
        # Characters are reversed individually; \" pair order reverses too.
        # Input chars: מ \ " ע ב  →  reversed: ב ע " \ מ
        assert _fix_rtl_line('מ\\"עב') == 'בע"\\מ'

    # --- mixed Hebrew + LTR content -----------------------------------------

    def test_date_preserved_in_mixed_line(self):
        # Date token has no Hebrew → kept as-is; Hebrew word is reversed
        result = _fix_rtl_line("02/02/2026 דובכל")
        assert "לכבוד" in result
        assert "02/02/2026" in result
        # Date must not be internally mangled (e.g. "6202/20/20")
        assert "6202" not in result

    def test_currency_preserved_in_mixed_line(self):
        result = _fix_rtl_line("₪2,921.68 ךס לכה")
        assert "₪2,921.68" in result
        assert "68.129" not in result   # amount must not be character-reversed

    def test_number_preserved_in_mixed_line(self):
        result = _fix_rtl_line("123456789 ח.פ")
        assert "123456789" in result

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("50008 סמ תינובשח", "חשבונית מס 50008"),
            ('₪1,770.00 םולשתל כ"הס', 'סה"כ לתשלום ₪1,770.00'),
            ('3,307.00:כ"הס', 'סה"כ:3,307.00'),
            ('3,902.26:מ"עמ ללוכ כ"הס', 'סה"כ כולל מע"מ:3,902.26'),
            ("01/03/2026:הדובע ךיראת", "תאריך עבודה:01/03/2026"),
            ("308474246:רוטפ קסוע", "עוסק פטור:308474246"),
            ('18.00%:מ"עמ', 'מע"מ:18.00%'),
            ("support@example.com:ליימ", "מייל:support@example.com"),
            ("https://example.com:רתא", "אתר:https://example.com"),
            ("050-1234567:ןופלט", "טלפון:050-1234567"),
            ("₪1,770.00:םוכס", "סכום:₪1,770.00"),
            ("ABC-123:ההזמ", "מזהה:ABC-123"),
            ("+972-50-1234567:ןופלט", "טלפון:+972-50-1234567"),
        ],
    )
    def test_ltr_run_attached_to_visual_hebrew_is_preserved(self, raw, expected):
        assert _fix_rtl_line(raw) == expected

    def test_word_order_reversed_for_mixed_line(self):
        # Input : Hebrew-word  Date
        # Output: Date  Hebrew-word  (word order reversed, Hebrew chars fixed)
        result = _fix_rtl_line("02/02/2026 דובכל")
        parts = result.split()
        assert parts[0] == "לכבוד"
        assert parts[1] == "02/02/2026"

    # --- edge / whitespace cases --------------------------------------------

    def test_leading_trailing_whitespace_stripped(self):
        # split() strips outer whitespace; acceptable for invoice text
        result = _fix_rtl_line("  דובכל  ")
        assert result == "לכבוד"

    def test_single_hebrew_character(self):
        # Single char reversed is itself
        assert _fix_rtl_line("א") == "א"


# ---------------------------------------------------------------------------
# normalize_rtl_text  (multi-line)
# ---------------------------------------------------------------------------

class TestNormalizeRtlText:

    def test_single_line_hebrew(self):
        assert normalize_rtl_text("דובכל") == "לכבוד"

    def test_multi_line_mixed(self):
        raw = "דובכל\nhello\n02/02/2026 דובכל"
        result = normalize_rtl_text(raw)
        lines = result.splitlines()
        assert lines[0] == "לכבוד"
        assert lines[1] == "hello"
        assert "לכבוד" in lines[2]
        assert "02/02/2026" in lines[2]

    def test_empty_text(self):
        assert normalize_rtl_text("") == ""

    def test_ltr_only_text_unchanged(self):
        text = "Invoice #12345\nDate: 01/01/2026\nTotal: $100.00"
        assert normalize_rtl_text(text) == text

    def test_page_separator_lines_unchanged(self):
        text = "\n--- PAGE 1 ---\nדובכל"
        result = normalize_rtl_text(text)
        assert "--- PAGE 1 ---" in result
        assert "לכבוד" in result

    def test_preserves_line_count(self):
        text = "line one\nדובכל\nline three"
        result = normalize_rtl_text(text)
        assert len(result.splitlines()) == len(text.splitlines())
