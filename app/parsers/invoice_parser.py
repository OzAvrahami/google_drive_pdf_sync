"""
Invoice parser: classify document type and extract structured fields.

Public API
----------
classify_document_type(text) -> str | None
should_process_document(text) -> bool
parse_invoice_text(text)     -> dict | None
"""

import re
from typing import Optional

# Hebrew PDFs use U+05F4 GERSHAYIM, ASCII 0x22, or curly U+201D in place of "
_Q = '"\u05f4\u201c\u201d'

# ── Classification ─────────────────────────────────────────────────────────────

# Rejection patterns — must be checked before acceptance
_RE_KABALA_MAS = re.compile(r'חשבונית\s+מס\s*[/\\]\s*קבלה|חשבונית\s+מס\s+קבלה')
_RE_KABALA     = re.compile(rf"קבלה\s+(?:מס[{_Q}'`]?\s*)?(?=\d)")

# Acceptance patterns
_RE_ESEK    = re.compile(r'חשבון\s+עסקה')
_RE_MAS     = re.compile(r'חשבונית\s+מס(?!\s*קבלה)')   # negative-lookahead guard
# Fix 1: typo variant "חשבוית מס" (missing ן) produced by certain PDF generators
_RE_MAS_TYPO = re.compile(r'חשבוית\s+מס(?!\s*קבלה)')
# Fix 2: broaden English detection — "Tax Invoice", "Invoice number/# /ID:", lone "Invoice" heading
_RE_TAX_EN  = re.compile(
    r'\bTax\s+Invoice\b'
    r'|\bInvoice\s+(?:number|#|ID)\s*:?'   # colon optional — some vendors omit it
    r'|^Invoice\s*$'
    r'|\bBill\s+#\d+\b',
    re.IGNORECASE | re.MULTILINE,
)
_RE_DARISHA = re.compile(r'דרישת\s+תשלום')


def classify_document_type(text: str) -> Optional[str]:
    """
    Return the canonical document type string, or None if unrecognised.

    Rejection checks always run before acceptance so "חשבונית מס קבלה"
    is never matched as "חשבונית מס".
    """
    # Reject combined invoice+receipt (both "חשבונית מס קבלה" and "חשבונית מס / קבלה")
    if _RE_KABALA_MAS.search(text):
        return "חשבונית מס קבלה"

    # Reject standalone receipt.
    # _RE_KABALA requires a digit immediately after the optional "מס'" token
    # (via a (?=\d) lookahead) so alphanumeric receipt references like
    # "קבלה מספר RCI26908086" inside consolidated invoices do NOT match here.
    if _RE_KABALA.search(text):
        return "קבלה"

    if _RE_ESEK.search(text):
        return "חשבון עסקה"
    if _RE_MAS.search(text) or _RE_MAS_TYPO.search(text) or _RE_TAX_EN.search(text):
        return "חשבונית מס"
    if _RE_DARISHA.search(text):
        return "דרישת תשלום"

    return None


def should_process_document(text: str) -> bool:
    doc_type = classify_document_type(text)
    return doc_type in {"חשבון עסקה", "חשבונית מס", "דרישת תשלום"}


# ── Field extractors ───────────────────────────────────────────────────────────

_RE_NUM_FOOTER  = re.compile(
    r'\|\s*(?:חשבון\s+עסקה|חשבונית\s+מס|חשבוית\s+מס|Tax\s+Invoice)\s+([A-Za-z0-9]+)\s*\|',
    re.IGNORECASE,
)
_RE_NUM_ENGLISH = re.compile(r'Invoice\s+(?:number|#|ID)\s*:?\s*([A-Za-z0-9]+)', re.IGNORECASE)
_RE_NUM_HEADING = re.compile(
    r'(?:חשבון\s+עסקה|חשבונ[יו]ת\s+מס(?:\s+(?!מספר)\S+)?|Tax\s+Invoice)'
    r'\s+(?:מספר\s+)?\(?([A-Za-z0-9]{3,})\)?',
    re.IGNORECASE,
)

_RE_DATE_FOOTER    = re.compile(r'הופק\s+ב[:\s]+(\d{1,2}/\d{2}/\d{4})')
_RE_DATE_FOOTER_EN = re.compile(r'Created\s+(\d{1,2}/\d{2}/\d{4})', re.IGNORECASE)
_RE_DATE_LABELED   = re.compile(
    r'תאריך\s*(?:חשבונית|מקור|הפקה|הדפסה|:)?\s*:?\s*(\d{1,2}[/.]\d{1,2}[/.]\d{2,4})'
)
_RE_DATE_EN_LABELED = re.compile(
    r'(?:Invoice\s+date|Date\s+of\s+issue|Date)\s*:?\s*'
    r'(\d{1,2}[/.]\d{1,2}[/.]\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4})',
    re.IGNORECASE,
)
_RE_DATE_ANY      = re.compile(r'\b(\d{1,2}[/.]\d{1,2}[/.]\d{4})\b')
_RE_PAYMENT_DUE   = re.compile(r'לתשלום\s+עד|due\s+by|payment\s+due|due\s+on', re.IGNORECASE)

_AMOUNT_PATTERNS = [
    re.compile(rf'סה[{_Q}]כ\s*לתשלום\s*(?:בש[{_Q}\'"]+ח)?\s*₪?\s*([\d,]+(?:\.\d+)?)\s*₪?'),
    re.compile(r'(?:Total\s+payable|Total\s+due|Amount\s+due|Invoice\s+Total)\s*:?\s*(?:ILS|USD|EUR|GBP)?\s*[₪$€£]?\s*([\d,]+(?:\.\d+)?)', re.IGNORECASE),
    re.compile(rf'סה[{_Q}]כ\s+כולל(?:\s+מע[{_Q}]מ)?\s*:?\s*₪?\s*([\d,]+(?:\.\d+)?)\s*₪?'),
    re.compile(rf'סה[{_Q}]כ\s+מחיר\s+([\d,]+(?:\.\d+)?)\s*ש[{_Q}\'"]+ח'),
    re.compile(r'^Total\s*:\s*([\d,]+(?:\.\d+)?)', re.MULTILINE | re.IGNORECASE),
]
# Fix 5: allow optional colon after סה"כ (e.g. "סה"כ: 19,164.00 ₪")
_RE_SEHAKOL_FALLBACK = re.compile(rf'סה[{_Q}]כ\s*:?\s*₪?\s*([\d,]+(?:\.\d+)?)\s*₪?')

_RE_MAT     = re.compile(r'מאת\s*:\s*(.+?)(?:\s+עבור\s*:|$)', re.MULTILINE)
_RE_LEKAVOD = re.compile(r'(?:לכבוד|לידי)\s*:?\s*(.+)')
_RE_BE_AM   = re.compile(rf'בע[{_Q}]מ')
_RE_CUSTOMER_SECTION = re.compile(r'לכבוד|לידי|שם\s+הלקוח|For\s+billing|Bill\s+To', re.IGNORECASE)
# Fix 3: added ^# (table header rows), מספר\s+X: (reference-number lines), שם\s*: (customer label)
_RE_SKIP_LINE = re.compile(
    r'^(?:עוסק|ח\.פ|ת\.ז|לכבוד|לידי|טלפון|מקור|עמוד|הופק|תאריך|לתשלום|'
    r'כתובת|נייד|אימייל|פירוט|תאור|פרוט|כמות|הקצאה|שם\s*:|'
    r'מספר\s+(?:פנימי|הקצאה|עוסק|לקוח|חשבון)\b|'
    r'#|'
    r'page\b|invoice\s+#|tax\s+id|billing|from\s+invoice|bill\s+to|'
    r'total|subtotal|created|date\b|due\b|powered\s+by|http|www\.|[a-z0-9._%+\-]+@)',
    re.IGNORECASE,
)
_RE_TRAILING_NOISE = re.compile(
    r'\s*(?:מסמך\s+ממוחשב.*|\(\s*מקור\s*\).*|-\s*מקור.*|\d{1,2}[/.]\d{1,2}[/.]\d{2,4}.*)$'
)
# Fix 6: watermark prefixes that appear before the actual supplier name
_RE_NAME_PREFIX_NOISE = re.compile(
    r'^(?:העתק\s+נאמן\s+למקור|Certif?ied\s+Copy)\s*',
    re.IGNORECASE,
)


def _extract_invoice_number(text: str) -> Optional[str]:
    m = _RE_NUM_FOOTER.search(text)
    if m:
        return m.group(1)
    m = _RE_NUM_ENGLISH.search(text)
    if m:
        return m.group(1)
    m = _RE_NUM_HEADING.search(text)
    if m:
        val = m.group(1)
        if len(val) >= 3 and val not in {"מקור", "מסמך", "מספר"}:
            return val
    return None


def _extract_invoice_date(text: str) -> Optional[str]:
    m = _RE_DATE_FOOTER.search(text)
    if m:
        return m.group(1)
    m = _RE_DATE_FOOTER_EN.search(text)
    if m:
        return m.group(1)
    m = _RE_DATE_LABELED.search(text)
    if m:
        return _normalise_date(m.group(1))
    m = _RE_DATE_EN_LABELED.search(text)
    if m:
        return _normalise_date_en(m.group(1))
    for m in _RE_DATE_ANY.finditer(text):
        ctx = text[max(0, m.start() - 30) : m.start()]
        if not _RE_PAYMENT_DUE.search(ctx):
            return _normalise_date(m.group(1))
    return None


def _extract_amount(text: str) -> Optional[float]:
    for pattern in _AMOUNT_PATTERNS:
        m = pattern.search(text)
        if m:
            val = _parse_amount(m.group(1))
            if val is not None:
                return val
    # Fallback: last סה"כ VALUE in document
    last = None
    for m in _RE_SEHAKOL_FALLBACK.finditer(text):
        val = _parse_amount(m.group(1))
        if val is not None:
            last = val
    return last


def _extract_business_name(text: str) -> Optional[str]:
    # 1. Explicit "מאת:" label
    m = _RE_MAT.search(text)
    if m:
        name = _clean_name(m.group(1))
        if name:
            return name

    # 2. "לכבוד: [customer בע"מ] [issuer]" — take text after first בע"מ
    m = _RE_LEKAVOD.search(text)
    if m:
        content = m.group(1)
        be_am = _RE_BE_AM.search(content)
        if be_am:
            remainder = content[be_am.end():].strip()
            name = _clean_name(remainder)
            if name and not _is_skip_line(remainder):
                return name

    # 3. Line immediately after the doc-type + number line
    # Only applies when the customer section (לכבוד/לידי) has NOT appeared
    # before the doc-type line — otherwise the supplier is above לכבוד: and
    # strategy 4 handles it better.
    lines = text.splitlines()
    for i, line in enumerate(lines):
        is_doc_line = (
            _RE_ESEK.search(line) or _RE_MAS.search(line) or _RE_MAS_TYPO.search(line)
            or _RE_TAX_EN.search(line) or _RE_DARISHA.search(line)
        )
        if is_doc_line and re.search(r'[A-Za-z0-9]{3,}', line):
            # If substantive non-skip lines exist before the customer section,
            # strategy 4 can find the supplier there — skip strategy 3.
            # But if לכבוד: is the very first meaningful line (nothing useful above
            # it), fall through to strategy 3 which looks below the doc-type line.
            first_customer = next(
                (k for k in range(i) if _RE_CUSTOMER_SECTION.search(lines[k])), None
            )
            if first_customer is not None:
                _doc_pats = (_RE_ESEK, _RE_MAS, _RE_MAS_TYPO, _RE_TAX_EN, _RE_DARISHA)
                supplier_above = any(
                    lines[k].strip()
                    and not lines[k].strip().startswith('---')
                    and not _is_skip_line(lines[k].strip())
                    and not any(p.search(lines[k]) for p in _doc_pats)
                    for k in range(first_customer)
                )
                if supplier_above:
                    continue  # strategy 4 will find it above לכבוד:
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j].strip()
                if _RE_CUSTOMER_SECTION.search(candidate):  # stop at customer section
                    break
                if candidate and not _is_skip_line(candidate):
                    return _clean_name(candidate)

    # 4. First substantive line before the customer section
    # Skip document-type indicator lines (e.g. "חשבונית מס מקור", "Invoice")
    # so the issuer name on the preceding/following line is returned instead.
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('---'):
            continue
        if _RE_CUSTOMER_SECTION.search(stripped):
            break
        is_doc_indicator = (
            _RE_ESEK.search(stripped) or _RE_MAS.search(stripped)
            or _RE_MAS_TYPO.search(stripped) or _RE_DARISHA.search(stripped)
            or _RE_TAX_EN.search(stripped)
        )
        if is_doc_indicator:
            continue
        if not _is_skip_line(stripped):
            return _clean_name(stripped)

    return None


# ── Main entry point ───────────────────────────────────────────────────────────

def parse_invoice_text(text: str) -> Optional[dict]:
    """
    Parse normalised PDF text extracted by extract_text_from_pdf().

    Returns a dict for processable documents (חשבון עסקה / חשבונית מס / דרישת תשלום),
    or None for receipts, combined invoice-receipts, and unrecognised types.

    Return shape:
        {
            "document_type": "tax_invoice" | "transaction_invoice" | "payment_request",
            "business_name": str | None,
            "invoice_date":  str | None,   # DD/MM/YYYY
            "invoice_number": str | None,
            "amount": float | None,        # סה"כ לתשלום
        }
    """
    doc_type = classify_document_type(text)

    if doc_type not in {"חשבון עסקה", "חשבונית מס", "דרישת תשלום"}:
        return None

    _TYPE_MAP = {
        "חשבון עסקה":  "transaction_invoice",
        "חשבונית מס":  "tax_invoice",
        "דרישת תשלום": "payment_request",
    }
    return {
        "document_type":  _TYPE_MAP[doc_type],
        "business_name":  _extract_business_name(text),
        "invoice_date":   _extract_invoice_date(text),
        "invoice_number": _extract_invoice_number(text),
        "amount":         _extract_amount(text),
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _normalise_date(raw: str) -> str:
    s = raw.replace('.', '/')
    parts = s.split('/')
    if len(parts) == 3 and len(parts[2]) == 2:
        parts[2] = "20" + parts[2]
    return '/'.join(parts)


_MONTH_MAP = {
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
    'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
}

def _normalise_date_en(raw: str) -> Optional[str]:
    """Convert English date strings like 'Jan 31, 2026' or '31 Jan 2026' to DD/MM/YYYY."""
    raw = raw.strip().rstrip('.')
    # Already numeric — delegate
    if re.match(r'^\d', raw):
        return _normalise_date(raw)
    # "Month DD, YYYY" or "Month DD YYYY"
    m = re.match(r'([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})', raw)
    if m:
        mon = _MONTH_MAP.get(m.group(1)[:3].lower())
        if mon:
            return f"{int(m.group(2)):02d}/{mon}/{m.group(3)}"
    # "DD Month YYYY"
    m = re.match(r'(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})', raw)
    if m:
        mon = _MONTH_MAP.get(m.group(2)[:3].lower())
        if mon:
            return f"{int(m.group(1)):02d}/{mon}/{m.group(3)}"
    return None


def _parse_amount(raw: str) -> Optional[float]:
    cleaned = re.sub(r'[₪$€£,\s]', '', raw)
    cleaned = re.sub(rf'(?:ILS|USD|EUR|GBP|ש[{_Q}\'"]+ח|בש[{_Q}]+ח)', '', cleaned).strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _clean_name(raw: str) -> Optional[str]:
    # Fix 6: strip watermark prefixes before trailing-noise removal
    cleaned = _RE_NAME_PREFIX_NOISE.sub('', raw)
    cleaned = _RE_TRAILING_NOISE.sub('', cleaned).strip()
    return cleaned if len(cleaned) >= 2 else None


def _is_skip_line(line: str) -> bool:
    s = line.strip()
    if not s or len(s) < 2 or len(s) > 80:
        return True
    if s in {"מקור", "מסמך ממוחשב", "מסמך", "חתימה:"}:
        return True
    if _RE_SKIP_LINE.match(s):
        return True
    if re.match(r'^[\d\s/.\-:,+()]+$', s):
        return True
    return False
