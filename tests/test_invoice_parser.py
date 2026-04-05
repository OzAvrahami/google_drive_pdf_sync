"""
Unit tests for app.parsers.invoice_parser.

Test strings are derived from real extracted PDF text observed in this
corpus (see tests/test_pdf_parser.py for live extraction).  They are
representative but minimal — each case targets one specific behaviour.

Run from the project root:
    pytest tests/test_invoice_parser.py -v
"""

import pytest
from app.parsers.invoice_parser import (
    DOC_CHESHBON_ESEK,
    DOC_CHESHBONIT_MAS,
    DOC_KABALA,
    DOC_KABALA_MAS,
    STATUS_PROCESSED,
    STATUS_SKIPPED_RECEIPT,
    STATUS_SKIPPED_INV_RECEIPT,
    STATUS_UNRECOGNIZED,
    classify_document_type,
    should_process_document,
    extract_invoice_number,
    extract_invoice_date,
    extract_total_amount,
    extract_business_name,
    parse_invoice_text,
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

UNRECOGNIZED_PAYMENT_REQUEST = """\

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


# ─── classify_document_type ───────────────────────────────────────────────────

class TestClassifyDocumentType:

    def test_cheshbon_esek_accepted(self):
        doc, status = classify_document_type(CHESHBON_ESEK_ICOUNT)
        assert doc == DOC_CHESHBON_ESEK
        assert status == STATUS_PROCESSED

    def test_cheshbonit_mas_accepted(self):
        doc, status = classify_document_type(CHESHBONIT_MAS_ICOUNT)
        assert doc == DOC_CHESHBONIT_MAS
        assert status == STATUS_PROCESSED

    def test_tax_invoice_english_accepted_as_cheshbonit_mas(self):
        doc, status = classify_document_type(CHESHBONIT_MAS_TAX_INVOICE_EN)
        assert doc == DOC_CHESHBONIT_MAS
        assert status == STATUS_PROCESSED

    def test_kabala_simple_rejected(self):
        doc, status = classify_document_type(KABALA_SIMPLE)
        assert doc == DOC_KABALA
        assert status == STATUS_SKIPPED_RECEIPT

    def test_kabala_mas_tabit_rejected(self):
        doc, status = classify_document_type(KABALA_MAS_TABIT)
        assert doc == DOC_KABALA_MAS
        assert status == STATUS_SKIPPED_INV_RECEIPT

    def test_kabala_mas_wolt_slash_format_rejected(self):
        # "חשבונית מס / קבלה" — with slash separator
        doc, status = classify_document_type(KABALA_MAS_WOLT)
        assert doc == DOC_KABALA_MAS
        assert status == STATUS_SKIPPED_INV_RECEIPT

    def test_unrecognized_type(self):
        doc, status = classify_document_type(UNRECOGNIZED_PAYMENT_REQUEST)
        assert doc is None
        assert status == STATUS_UNRECOGNIZED

    def test_invoice_with_embedded_kabala_ref_not_rejected(self):
        # Priority: has "קבלה מספר RCI..." internally but IS a חשבונית מס
        doc, status = classify_document_type(CHESHBONIT_MAS_WITH_KABALA_REF)
        assert doc == DOC_CHESHBONIT_MAS
        assert status == STATUS_PROCESSED

    def test_kabala_mas_never_accepted_as_cheshbonit_mas(self):
        # "חשבונית מס קבלה" must be rejected, never accepted as "חשבונית מס"
        doc, _ = classify_document_type(KABALA_MAS_TABIT)
        assert doc != DOC_CHESHBONIT_MAS

    def test_empty_text_is_unrecognized(self):
        doc, status = classify_document_type("")
        assert doc is None
        assert status == STATUS_UNRECOGNIZED


class TestShouldProcessDocument:

    def test_returns_true_for_accepted_types(self):
        assert should_process_document(CHESHBON_ESEK_ICOUNT) is True
        assert should_process_document(CHESHBONIT_MAS_ICOUNT) is True

    def test_returns_false_for_rejected_types(self):
        assert should_process_document(KABALA_SIMPLE) is False
        assert should_process_document(KABALA_MAS_TABIT) is False

    def test_returns_false_for_unrecognized(self):
        assert should_process_document(UNRECOGNIZED_PAYMENT_REQUEST) is False


# ─── extract_invoice_number ───────────────────────────────────────────────────

class TestExtractInvoiceNumber:

    def test_icount_footer_pipe_pattern(self):
        assert extract_invoice_number(CHESHBON_ESEK_ICOUNT) == "40331"

    def test_icount_footer_cheshbonit_mas(self):
        assert extract_invoice_number(CHESHBONIT_MAS_ICOUNT) == "50094"

    def test_icount_english_footer(self):
        assert extract_invoice_number(CHESHBONIT_MAS_TAX_INVOICE_EN) == "50171"

    def test_hebrew_heading_with_maspor(self):
        # "חשבון עסקה מספר 100038"
        text = "חשבון עסקה מספר 100038\nמקור\n"
        assert extract_invoice_number(text) == "100038"

    def test_hebrew_heading_with_parenthesised_maqor(self):
        # "חשבון עסקה 300001 )מקור("
        assert extract_invoice_number(CHESHBON_ESEK_MAT_LABEL) == "300001"

    def test_cheshbonit_mas_with_maspor(self):
        assert extract_invoice_number(CHESHBONIT_MAS_LABELED_DATE) == "26010096"

    def test_cheshbonit_mas_merged_variant(self):
        # "חשבונית מס מרכזת SII26608838"
        assert extract_invoice_number(CHESHBONIT_MAS_WITH_KABALA_REF) == "SII26608838"

    def test_english_invoice_number_label(self):
        text = "Invoice number: 538221832\nDigitalOcean LLC\n"
        assert extract_invoice_number(text) == "538221832"

    def test_english_invoice_hash_label(self):
        text = "Invoice # INV05085197\nAsana Inc\n"
        assert extract_invoice_number(text) == "INV05085197"

    def test_no_number_returns_none(self):
        assert extract_invoice_number("some text without an invoice number") is None


# ─── extract_invoice_date ─────────────────────────────────────────────────────

class TestExtractInvoiceDate:

    def test_icount_footer_date(self):
        assert extract_invoice_date(CHESHBON_ESEK_ICOUNT) == "03/02/2026"

    def test_icount_english_footer_date(self):
        assert extract_invoice_date(CHESHBONIT_MAS_TAX_INVOICE_EN) == "21/01/2026"

    def test_labeled_date_tarich(self):
        assert extract_invoice_date(CHESHBONIT_MAS_LABELED_DATE) == "31/01/2026"

    def test_labeled_date_tarich_cheshbonit(self):
        # "תאריך חשבונית: 10/03/26" — 2-digit year expanded
        assert extract_invoice_date(CHESHBONIT_MAS_WITH_KABALA_REF) == "10/03/2026"

    def test_taarich_label_without_qualifier(self):
        # "תאריך: 22/02/2026" in body
        assert extract_invoice_date(PULSEEM_NO_LEKAVOD) == "22/02/2026"

    def test_payment_due_date_not_extracted_as_invoice_date(self):
        # "לתשלום עד 28/02/2026" must not be the result when a better date exists
        date = extract_invoice_date(CHESHBON_ESEK_ICOUNT)
        assert date == "03/02/2026"   # footer date wins

    def test_no_date_returns_none(self):
        assert extract_invoice_date("no date here") is None


# ─── extract_total_amount ─────────────────────────────────────────────────────

class TestExtractTotalAmount:

    def test_sehakol_letashloum(self):
        assert extract_total_amount(CHESHBON_ESEK_ICOUNT) == "7500.00"

    def test_sehakol_letashloum_beshach(self):
        # "סה"כ לתשלום בש''ח 142,770.48"
        assert extract_total_amount(CHESHBONIT_MAS_LABELED_DATE) == "142770.48"

    def test_total_payable_english(self):
        assert extract_total_amount(CHESHBONIT_MAS_TAX_INVOICE_EN) == "25635.50"

    def test_sehakol_kolel_maam(self):
        # "סה"כ כולל מע"מ: ₪16,992.00"
        assert extract_total_amount(PULSEEM_NO_LEKAVOD) == "16992.00"

    def test_sehakol_kolel_multiline(self):
        # Amount on line following "סה"כ כולל"
        assert extract_total_amount(MULTILINE_AMOUNT) == "10620.00"

    def test_priority_sehakol_mehir_format(self):
        # "סה"כ מחיר 8,923.00 ש"ח"
        assert extract_total_amount(CHESHBONIT_MAS_WITH_KABALA_REF) == "8923.00"

    def test_no_amount_returns_none(self):
        assert extract_total_amount("invoice text with no totals") is None


# ─── extract_business_name ────────────────────────────────────────────────────

class TestExtractBusinessName:

    def test_mat_label(self):
        # "מאת: מרגריטה שימנובסקי"
        assert extract_business_name(CHESHBON_ESEK_MAT_LABEL) == "מרגריטה שימנובסקי"

    def test_lekavod_line_customer_then_issuer(self):
        # "לכבוד: פנדה הום בע"מ היפוקמפוס סי אקס בע"מ"
        name = extract_business_name(CHESHBONIT_MAS_ICOUNT)
        assert name == 'היפוקמפוס סי אקס בע"מ'

    def test_lekavod_line_individual_issuer(self):
        # "לכבוד: פנדה הום בע"מ ניצן פרידמן- עיצוב גרפי ומדיה חברתית"
        name = extract_business_name(CHESHBON_ESEK_ICOUNT)
        assert name == "ניצן פרידמן- עיצוב גרפי ומדיה חברתית"

    def test_after_doc_type_line(self):
        # "חשבון עסקה 40608\nניב ביטס ייצוג אמנים בע"מ"
        name = extract_business_name(CHESHBON_ESEK_AFTER_HEADER)
        assert name == 'ניב ביטס ייצוג אמנים בע"מ'

    def test_after_doc_type_english(self):
        # "Tax Invoice 50171\nSELLENCE TECHNOLOGY LTD"
        name = extract_business_name(CHESHBONIT_MAS_TAX_INVOICE_EN)
        assert name == "SELLENCE TECHNOLOGY LTD"

    def test_after_doc_type_no_lekavod(self):
        # "חשבון עסקה 47373\nפולסים בע"מ"
        name = extract_business_name(PULSEEM_NO_LEKAVOD)
        assert name == 'פולסים בע"מ'

    def test_first_substantive_line(self):
        # "היי ביז בע"מ" is first line; "לכבוד:" breaks the search
        name = extract_business_name(CHESHBONIT_MAS_FIRST_LINE)
        assert name == 'היי ביז בע"מ'

    def test_first_line_trailing_noise_stripped(self):
        # "רועי זמיר מסמך ממוחשב" — trailing noise stripped
        name = extract_business_name(MULTILINE_AMOUNT)
        assert name == "רועי זמיר"

    def test_priority_first_substantive_line(self):
        # Issuer "פריוריטי סופטוור בע"מ" is first line
        name = extract_business_name(CHESHBONIT_MAS_WITH_KABALA_REF)
        assert name == 'פריוריטי סופטוור בע"מ'


# ─── parse_invoice_text (integration) ────────────────────────────────────────

class TestParseInvoiceText:

    def test_processed_record_has_all_fields(self):
        record = parse_invoice_text(
            CHESHBON_ESEK_ICOUNT,
            file_name="40331.pdf",
            folder_path="ינואר 2026/חשבון עסקה",
        )
        assert record.status        == STATUS_PROCESSED
        assert record.document_type == DOC_CHESHBON_ESEK
        assert record.file_name     == "40331.pdf"
        assert record.folder_path   == "ינואר 2026/חשבון עסקה"
        assert record.invoice_number == "40331"
        assert record.invoice_date   == "03/02/2026"
        assert record.amount         == "7500.00"
        assert record.business_name is not None

    def test_skipped_receipt_has_no_extracted_fields(self):
        record = parse_invoice_text(KABALA_SIMPLE)
        assert record.status        == STATUS_SKIPPED_RECEIPT
        assert record.document_type == DOC_KABALA
        assert record.invoice_number is None
        assert record.invoice_date   is None
        assert record.amount         is None
        assert record.business_name  is None

    def test_skipped_invoice_receipt(self):
        record = parse_invoice_text(KABALA_MAS_TABIT)
        assert record.status        == STATUS_SKIPPED_INV_RECEIPT
        assert record.document_type == DOC_KABALA_MAS

    def test_unrecognized_document(self):
        record = parse_invoice_text(UNRECOGNIZED_PAYMENT_REQUEST)
        assert record.status == STATUS_UNRECOGNIZED
        assert record.invoice_number is None

    def test_to_dict_never_contains_none(self):
        record = parse_invoice_text(KABALA_SIMPLE)
        d = record.to_dict()
        for key, val in d.items():
            assert val is not None, f"to_dict() returned None for key '{key}'"

    def test_file_name_and_folder_path_always_present(self):
        record = parse_invoice_text("", file_name="x.pdf", folder_path="some/path")
        assert record.file_name   == "x.pdf"
        assert record.folder_path == "some/path"
