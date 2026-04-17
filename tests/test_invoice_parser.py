"""
Unit tests for app.parsers.invoice_parser.

Text fixtures are derived from real extracted PDF text observed in this corpus.
Each case targets one specific behaviour.

Run from the project root:
    pytest tests/test_invoice_parser.py -v
"""

import pytest
from app.parsers.invoice_parser import (
    classify_document_type,
    should_process_document,
    parse_invoice_text,
    EXCLUDED_DOCUMENT_TYPES,
    SUPPORTED_DOCUMENT_TYPES,
    _extract_invoice_number,
    _extract_invoice_date,
    _extract_amount,
    _extract_business_name,
)


# ─── Fixtures: representative text blocks ─────────────────────────────────────

CHESHBON_ESEK_ICOUNT = """\

--- PAGE 1 ---
לכבוד: פנדה הום בע"מ ניצן פרידמן- עיצוב גרפי ומדיה חברתית
עוסק פטור: 036884781
ח.פ/ת.ז 515781219 יהודה הימית ,21 תל אביב - יפו
חשבון עסקה 40331
03/02/2026
מקור לתשלום עד 28/02/2026
סה"כ ₪7,500.00
מע"מ 0% ₪0.00
סה"כ לתשלום ₪7,500.00
הופק ב 03/02/2026 13:54 | חשבון עסקה 40331 | עמוד 1 מתוך 1
"""

CHESHBON_ESEK_AFTER_HEADER = """\

--- PAGE 1 ---
לכבוד: 02/02/2026
פנדה הום בע"מ
ח.פ/ת.ז 515781219
חשבון עסקה 40608
ניב ביטס ייצוג אמנים בע"מ
מקור
סה"כ ₪5,462.00
מע"מ 18% ₪983.16
סה"כ לתשלום ₪6,445.16
הופק ב 02/02/2026 23:05 | חשבון עסקה 40608 | עמוד 1 מתוך 1
"""

CHESHBON_ESEK_MAT_LABEL = """\

--- PAGE 1 ---
חשבון עסקה 300001 )מקור(
הופק ב: 01/02/2026
מאת: מרגריטה שימנובסקי עבור: פנדה הום
ע.פ: 325941672 ע.מ/ת.ז: 515781219
סה"כ פטור ממע"מ 2,795.00 ₪
מע"מ 0.00 ₪
סה"כ לתשלום 2,795.00 ₪
"""

CHESHBONIT_MAS_ICOUNT = """\

--- PAGE 1 ---
לכבוד: פנדה הום בע"מ היפוקמפוס סי אקס בע"מ
עוסק מורשה )ח.פ(: 516259702
ח.פ/ת.ז 515781219
01/02/2026 לתשלום עד 28/02/2026
חשבונית מס 50094
מקור
סה"כ ₪2,250.00
מע"מ 18% ₪405.00
סה"כ לתשלום ₪2,655.00
הופק ב 01/02/2026 14:12 | חשבונית מס 50094 | עמוד 1 מתוך 1
"""

CHESHBONIT_MAS_LABELED_DATE = """\

--- PAGE 1 ---
לידי: פנדה הום בע"מ תאריך: 31/01/2026
אריה שנקר 1 הרצליה
מס' ח.פ. 515781219
חשבונית מס מספר 26010096 מקור
הקצאה מספר: 20260218090543410049056886
סה"כ חייב במע"מ: 120,991.93
מע"מ 18% 21,778.55
סה"כ לתשלום בש''ח 142,770.48
"""

CHESHBONIT_MAS_FIRST_LINE = """\

--- PAGE 1 ---
היי ביז בע"מ
רפפורט ,3 כפר סבא
ח.פ. 51-4231075
לכבוד: פנדה הום בע"מ תאריך: 19/01/2026
חשבונית מס 6739050 מקור
סה"כ 85,000.00 ₪
מע"מ 18.00% 15,300.00 ₪
סה"כ לתשלום 100,300.00 ₪
"""

CHESHBONIT_MAS_TAX_INVOICE_EN = """\

--- PAGE 1 ---
To: 02 Jan 2026
פנדה
ID 515781219
Tax Invoice 50171
SELLENCE TECHNOLOGY LTD
Tax ID: 516806866
Subtotal ILS 21,725.00
VAT 18% ILS 3,910.50
Total payable ILS 25,635.50
Created 21/01/2026 19:50 | Tax Invoice 50171 | page 1 of 1
"""

CHESHBONIT_MAS_WITH_KABALA_REF = """\

--- PAGE 1 ---
פריוריטי סופטוור בע"מ
רח' עמל 2 פארק אפק
לכבוד: תאריך חשבונית: 10/03/26
פנדה הום בע"מ
חשבונית מס מרכזת SII26608838 - מקור )מסמך ממוחשב(
סה"כ כללי 7,561.59
מע"מ (18.00%) 1,361.14
סה"כ מחיר 8,923.00 ש"ח
קבלה מספר RCI26908086
כרטיסי אשראי
"""

PULSEEM_NO_LEKAVOD = """\

--- PAGE 1 ---
חשבון עסקה 47373
פולסים בע"מ
מקור
שם הלקוח: פנדה
ת.ז./ע.מ.: 515781219
תאריך: 22/02/2026
לתשלום עד: 24/03/2026
סה"כ לפני מע"מ ₪14,400.00
מע"מ 18.0% ₪2,592.00
סה"כ כולל מע"מ: ₪16,992.00
"""

KABALA_SIMPLE = """\

--- PAGE 1 ---
קיסוס הפקות
צילום אירועים
עוסק מורשה: 200335123
לכבוד: פנדה הום בע"מ קבלה מס' 705299 03/03/2026
515781219 מקור
סה"כ: ₪1,025.00
"""

KABALA_MAS_TABIT = """\

--- PAGE 1 ---
BRENNER MAX
מקס ברנר ריטייל
ח.פ./ע.מ. 516222247
עבור פנדה הום בע"מ
חשבונית מס קבלה מס 8100003679
12:52 23/03/2026
סה"כ לתשלום 6445.00
"""

KABALA_MAS_WOLT = """\

--- PAGE 1 ---
חשבונית מס / קבלה )מקור( מספר 254875607
וואלט אנטרפריזס ישראל בע"מ
סה"כ בש"ח )כולל מע״מ( 271.90
"""

DARISHA_TASHLUM = """\

--- PAGE 1 ---
יעל רותם
עוסק מורשה: 032971020
דרישת תשלום 1010
חתום דיגיטלית מקור 29/01/2026
לכבוד:
פנדה הום בע"מ
סה"כ כולל מע"מ ₪802
"""

MULTILINE_AMOUNT = """\

--- PAGE 1 ---
רועי זמיר מסמך ממוחשב
חשבון עסקה 7263 )מקור(
תאריך: 31/01/2026
לכבוד: פנדה הום בע"מ
סה"כ לפני מע"מ ₪9,000.00
מע"מ 18% ₪1,620.00
סה"כ כולל
₪10,620.00
מע"מ:
"""

# Supplier onboarding / account-opening form — must be excluded
SUPPLIER_OPENING_FORM = """\

--- PAGE 1 ---
טופס פתיחת ספק
שם הספק: חברה ראשית בע"מ
ח.פ: 123456789
כתובת: רחוב הרצל 1, תל אביב
טלפון: 03-1234567
אימייל: supplier@example.com
מספר חשבון בנק: 12-345-678901
"""

SUPPLIER_FORM_VARIANT = """\

--- PAGE 1 ---
טופס פרטי ספק
למילוי על-ידי הספק
שם מלא: דניאל לוי
עוסק מורשה: 987654321
"""


# ─── classify_document_type ───────────────────────────────────────────────────

class TestClassifyDocumentType:

    def test_cheshbon_esek_accepted(self):
        assert classify_document_type(CHESHBON_ESEK_ICOUNT) == "חשבון עסקה"

    def test_cheshbonit_mas_accepted(self):
        assert classify_document_type(CHESHBONIT_MAS_ICOUNT) == "חשבונית מס"

    def test_tax_invoice_english_accepted(self):
        assert classify_document_type(CHESHBONIT_MAS_TAX_INVOICE_EN) == "חשבונית מס"

    def test_kabala_simple_rejected(self):
        assert classify_document_type(KABALA_SIMPLE) == "קבלה"

    def test_kabala_mas_tabit_rejected(self):
        assert classify_document_type(KABALA_MAS_TABIT) == "חשבונית מס קבלה"

    def test_kabala_mas_wolt_slash_format_rejected(self):
        assert classify_document_type(KABALA_MAS_WOLT) == "חשבונית מס קבלה"

    def test_darisha_tashlum_accepted(self):
        # "דרישת תשלום" is a supported type
        assert classify_document_type(DARISHA_TASHLUM) == "דרישת תשלום"

    def test_invoice_with_embedded_kabala_ref_not_rejected(self):
        # Priority: contains "קבלה מספר RCI..." internally — must still be חשבונית מס
        assert classify_document_type(CHESHBONIT_MAS_WITH_KABALA_REF) == "חשבונית מס"

    def test_kabala_mas_never_accepted_as_cheshbonit_mas(self):
        assert classify_document_type(KABALA_MAS_TABIT) != "חשבונית מס"

    def test_empty_text_is_none(self):
        assert classify_document_type("") is None


# ─── should_process_document ─────────────────────────────────────────────────

class TestShouldProcessDocument:

    def test_returns_true_for_accepted_types(self):
        assert should_process_document(CHESHBON_ESEK_ICOUNT) is True
        assert should_process_document(CHESHBONIT_MAS_ICOUNT) is True
        assert should_process_document(DARISHA_TASHLUM) is True

    def test_returns_false_for_rejected_types(self):
        assert should_process_document(KABALA_SIMPLE) is False
        assert should_process_document(KABALA_MAS_TABIT) is False

    def test_returns_false_for_unrecognized(self):
        assert should_process_document("random unrecognized text") is False


# ─── Classification constants ────────────────────────────────────────────────

class TestClassificationConstants:
    """Verify EXCLUDED_DOCUMENT_TYPES and SUPPORTED_DOCUMENT_TYPES are correct."""

    def test_excluded_contains_invoice_receipt(self):
        assert "חשבונית מס קבלה" in EXCLUDED_DOCUMENT_TYPES

    def test_excluded_contains_receipt(self):
        assert "קבלה" in EXCLUDED_DOCUMENT_TYPES

    def test_excluded_contains_supplier_form(self):
        assert "טופס פתיחת ספק" in EXCLUDED_DOCUMENT_TYPES

    def test_supported_contains_all_invoice_types(self):
        assert "חשבון עסקה"  in SUPPORTED_DOCUMENT_TYPES
        assert "חשבונית מס"  in SUPPORTED_DOCUMENT_TYPES
        assert "דרישת תשלום" in SUPPORTED_DOCUMENT_TYPES

    def test_excluded_and_supported_are_disjoint(self):
        assert EXCLUDED_DOCUMENT_TYPES.isdisjoint(SUPPORTED_DOCUMENT_TYPES)


# ─── Supplier opening form exclusion ─────────────────────────────────────────

class TestSupplierOpeningFormExclusion:
    """טופס פתיחת ספק must be classified as excluded and never parsed."""

    def test_classify_returns_supplier_form_type(self):
        assert classify_document_type(SUPPLIER_OPENING_FORM) == "טופס פתיחת ספק"

    def test_variant_phrase_also_detected(self):
        assert classify_document_type(SUPPLIER_FORM_VARIANT) == "טופס פתיחת ספק"

    def test_should_process_returns_false(self):
        assert should_process_document(SUPPLIER_OPENING_FORM) is False

    def test_parse_invoice_text_returns_none(self):
        assert parse_invoice_text(SUPPLIER_OPENING_FORM) is None

    def test_supplier_form_is_in_excluded_types(self):
        doc_type = classify_document_type(SUPPLIER_OPENING_FORM)
        assert doc_type in EXCLUDED_DOCUMENT_TYPES

    def test_supplier_form_not_classified_as_invoice(self):
        doc_type = classify_document_type(SUPPLIER_OPENING_FORM)
        assert doc_type not in SUPPORTED_DOCUMENT_TYPES


# ─── Existing excluded types (regression) ────────────────────────────────────

class TestExistingExcludedTypesRegression:
    """Ensure previously excluded types remain excluded after the refactor."""

    def test_invoice_receipt_excluded(self):
        assert classify_document_type(KABALA_MAS_TABIT) in EXCLUDED_DOCUMENT_TYPES
        assert classify_document_type(KABALA_MAS_WOLT) in EXCLUDED_DOCUMENT_TYPES

    def test_receipt_excluded(self):
        assert classify_document_type(KABALA_SIMPLE) in EXCLUDED_DOCUMENT_TYPES

    def test_invoice_receipt_never_classified_as_supported(self):
        assert classify_document_type(KABALA_MAS_TABIT) not in SUPPORTED_DOCUMENT_TYPES

    def test_normal_invoice_still_accepted(self):
        assert classify_document_type(CHESHBONIT_MAS_ICOUNT) in SUPPORTED_DOCUMENT_TYPES
        assert classify_document_type(CHESHBON_ESEK_ICOUNT)   in SUPPORTED_DOCUMENT_TYPES
        assert classify_document_type(DARISHA_TASHLUM)         in SUPPORTED_DOCUMENT_TYPES


# ─── _extract_invoice_number ──────────────────────────────────────────────────

class TestExtractInvoiceNumber:

    def test_icount_footer_pipe_pattern(self):
        assert _extract_invoice_number(CHESHBON_ESEK_ICOUNT) == "40331"

    def test_icount_footer_cheshbonit_mas(self):
        assert _extract_invoice_number(CHESHBONIT_MAS_ICOUNT) == "50094"

    def test_icount_english_footer(self):
        assert _extract_invoice_number(CHESHBONIT_MAS_TAX_INVOICE_EN) == "50171"

    def test_hebrew_heading_with_maspor(self):
        text = "חשבון עסקה מספר 100038\nמקור\n"
        assert _extract_invoice_number(text) == "100038"

    def test_hebrew_heading_with_parenthesised_maqor(self):
        assert _extract_invoice_number(CHESHBON_ESEK_MAT_LABEL) == "300001"

    def test_cheshbonit_mas_with_maspor(self):
        assert _extract_invoice_number(CHESHBONIT_MAS_LABELED_DATE) == "26010096"

    def test_cheshbonit_mas_merged_variant(self):
        assert _extract_invoice_number(CHESHBONIT_MAS_WITH_KABALA_REF) == "SII26608838"

    def test_english_invoice_number_label(self):
        text = "Invoice number: 538221832\nDigitalOcean LLC\n"
        assert _extract_invoice_number(text) == "538221832"

    def test_english_invoice_hash_label(self):
        text = "Invoice # INV05085197\nAsana Inc\n"
        assert _extract_invoice_number(text) == "INV05085197"

    def test_no_number_returns_none(self):
        assert _extract_invoice_number("some text without an invoice number") is None


# ─── _extract_invoice_date ────────────────────────────────────────────────────

class TestExtractInvoiceDate:

    def test_icount_footer_date(self):
        assert _extract_invoice_date(CHESHBON_ESEK_ICOUNT) == "03/02/2026"

    def test_icount_english_footer_date(self):
        assert _extract_invoice_date(CHESHBONIT_MAS_TAX_INVOICE_EN) == "21/01/2026"

    def test_labeled_date_tarich(self):
        assert _extract_invoice_date(CHESHBONIT_MAS_LABELED_DATE) == "31/01/2026"

    def test_labeled_date_tarich_cheshbonit(self):
        # "תאריך חשבונית: 10/03/26" — 2-digit year expanded
        assert _extract_invoice_date(CHESHBONIT_MAS_WITH_KABALA_REF) == "10/03/2026"

    def test_taarich_label_without_qualifier(self):
        assert _extract_invoice_date(PULSEEM_NO_LEKAVOD) == "22/02/2026"

    def test_payment_due_date_not_used_when_better_date_exists(self):
        # Footer date "03/02/2026" must win over "לתשלום עד 28/02/2026"
        assert _extract_invoice_date(CHESHBON_ESEK_ICOUNT) == "03/02/2026"

    def test_no_date_returns_none(self):
        assert _extract_invoice_date("no date here") is None


# ─── _extract_amount ──────────────────────────────────────────────────────────

class TestExtractAmount:

    def test_sehakol_letashloum(self):
        assert _extract_amount(CHESHBON_ESEK_ICOUNT) == 7500.0

    def test_sehakol_letashloum_beshach(self):
        assert _extract_amount(CHESHBONIT_MAS_LABELED_DATE) == 142770.48

    def test_total_payable_english(self):
        assert _extract_amount(CHESHBONIT_MAS_TAX_INVOICE_EN) == 25635.5

    def test_sehakol_kolel_maam(self):
        assert _extract_amount(PULSEEM_NO_LEKAVOD) == 16992.0

    def test_sehakol_kolel_multiline(self):
        assert _extract_amount(MULTILINE_AMOUNT) == 10620.0

    def test_priority_sehakol_mehir_format(self):
        assert _extract_amount(CHESHBONIT_MAS_WITH_KABALA_REF) == 8923.0

    def test_no_amount_returns_none(self):
        assert _extract_amount("invoice text with no totals") is None


# ─── _extract_business_name ───────────────────────────────────────────────────

class TestExtractBusinessName:

    def test_mat_label(self):
        assert _extract_business_name(CHESHBON_ESEK_MAT_LABEL) == "מרגריטה שימנובסקי"

    def test_lekavod_line_customer_then_issuer(self):
        name = _extract_business_name(CHESHBONIT_MAS_ICOUNT)
        assert name == 'היפוקמפוס סי אקס בע"מ'

    def test_lekavod_line_individual_issuer(self):
        name = _extract_business_name(CHESHBON_ESEK_ICOUNT)
        assert name == "ניצן פרידמן- עיצוב גרפי ומדיה חברתית"

    def test_after_doc_type_line(self):
        name = _extract_business_name(CHESHBON_ESEK_AFTER_HEADER)
        assert name == 'ניב ביטס ייצוג אמנים בע"מ'

    def test_after_doc_type_english(self):
        name = _extract_business_name(CHESHBONIT_MAS_TAX_INVOICE_EN)
        assert name == "SELLENCE TECHNOLOGY LTD"

    def test_after_doc_type_no_lekavod(self):
        name = _extract_business_name(PULSEEM_NO_LEKAVOD)
        assert name == 'פולסים בע"מ'

    def test_first_substantive_line(self):
        name = _extract_business_name(CHESHBONIT_MAS_FIRST_LINE)
        assert name == 'היי ביז בע"מ'

    def test_first_line_trailing_noise_stripped(self):
        name = _extract_business_name(MULTILINE_AMOUNT)
        assert name == "רועי זמיר"

    def test_priority_first_substantive_line(self):
        name = _extract_business_name(CHESHBONIT_MAS_WITH_KABALA_REF)
        assert name == 'פריוריטי סופטוור בע"מ'


# ─── parse_invoice_text (integration) ────────────────────────────────────────

class TestParseInvoiceText:

    def test_processed_record_has_all_fields(self):
        result = parse_invoice_text(CHESHBON_ESEK_ICOUNT)
        assert result is not None
        assert result["document_type"]  == "transaction_invoice"
        assert result["invoice_number"] == "40331"
        assert result["invoice_date"]   == "03/02/2026"
        assert result["amount"]         == 7500.0
        assert result["business_name"]  is not None

    def test_tax_invoice_type(self):
        result = parse_invoice_text(CHESHBONIT_MAS_ICOUNT)
        assert result is not None
        assert result["document_type"] == "tax_invoice"

    def test_payment_request_type(self):
        result = parse_invoice_text(DARISHA_TASHLUM)
        assert result is not None
        assert result["document_type"] == "payment_request"

    def test_receipt_returns_none(self):
        assert parse_invoice_text(KABALA_SIMPLE) is None

    def test_invoice_receipt_returns_none(self):
        assert parse_invoice_text(KABALA_MAS_TABIT) is None

    def test_unrecognized_returns_none(self):
        assert parse_invoice_text("random text with no invoice markers") is None

    def test_amount_is_float(self):
        result = parse_invoice_text(CHESHBON_ESEK_ICOUNT)
        assert isinstance(result["amount"], float)

    def test_all_dict_keys_present(self):
        result = parse_invoice_text(CHESHBONIT_MAS_ICOUNT)
        assert result is not None
        for key in ("document_type", "business_name", "invoice_date",
                    "invoice_number", "amount"):
            assert key in result
