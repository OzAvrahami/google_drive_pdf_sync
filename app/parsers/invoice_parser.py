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
_RE_ESEK   = re.compile(r'חשבון\s+עסקה')
_RE_MAS    = re.compile(r'חשבונית\s+מס(?!\s*קבלה)')   # negative-lookahead guard
_RE_TAX_EN = re.compile(r'\bTax\s+Invoice\b', re.IGNORECASE)


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
    if _RE_MAS.search(text) or _RE_TAX_EN.search(text):
        return "חשבונית מס"

    return None


def should_process_document(text: str) -> bool:
    doc_type = classify_document_type(text)
    return doc_type in {"חשבון עסקה", "חשבונית מס"}


# ── Field extractors ───────────────────────────────────────────────────────────

_RE_NUM_FOOTER  = re.compile(
    r'\|\s*(?:חשבון\s+עסקה|חשבונית\s+מס|Tax\s+Invoice)\s+([A-Za-z0-9]+)\s*\|',
    re.IGNORECASE,
)
_RE_NUM_ENGLISH = re.compile(r'Invoice\s+(?:number|#)\s*:?\s*([A-Za-z0-9]+)', re.IGNORECASE)
_RE_NUM_HEADING = re.compile(
    r'(?:חשבון\s+עסקה|חשבונית\s+מס(?:\s+(?!מספר)\S+)?|Tax\s+Invoice)'
    r'\s+(?:מספר\s+)?\(?([A-Za-z0-9]{3,})\)?',
    re.IGNORECASE,
)

_RE_DATE_FOOTER    = re.compile(r'הופק\s+ב[:\s]+(\d{1,2}/\d{2}/\d{4})')
_RE_DATE_FOOTER_EN = re.compile(r'Created\s+(\d{1,2}/\d{2}/\d{4})', re.IGNORECASE)
_RE_DATE_LABELED   = re.compile(
    r'תאריך\s*(?:חשבונית|מקור|הפקה|הדפסה)?\s*:?\s*(\d{1,2}[/.]\d{1,2}[/.]\d{2,4})'
)
_RE_DATE_ANY      = re.compile(r'\b(\d{1,2}[/.]\d{1,2}[/.]\d{4})\b')
_RE_PAYMENT_DUE   = re.compile(r'לתשלום\s+עד|due\s+by|payment\s+due|due\s+on', re.IGNORECASE)

_AMOUNT_PATTERNS = [
    re.compile(rf'סה[{_Q}]כ\s*לתשלום\s*(?:בש[{_Q}\'"]+ח)?\s*₪?\s*([\d,]+(?:\.\d+)?)\s*₪?'),
    re.compile(r'(?:Total\s+payable|Total\s+due)\s+(?:ILS|USD|EUR|GBP)?\s*\$?\s*([\d,]+(?:\.\d+)?)', re.IGNORECASE),
    re.compile(rf'סה[{_Q}]כ\s+כולל(?:\s+מע[{_Q}]מ)?\s*:?\s*₪?\s*([\d,]+(?:\.\d+)?)\s*₪?'),
    re.compile(rf'סה[{_Q}]כ\s+מחיר\s+([\d,]+(?:\.\d+)?)\s*ש[{_Q}\'"]+ח'),
    re.compile(r'^Total\s*:\s*([\d,]+(?:\.\d+)?)', re.MULTILINE | re.IGNORECASE),
]
_RE_SEHAKOL_FALLBACK = re.compile(rf'סה[{_Q}]כ\s*₪?\s*([\d,]+(?:\.\d+)?)\s*₪?')

_RE_MAT     = re.compile(r'מאת\s*:\s*(.+?)(?:\s+עבור\s*:|$)', re.MULTILINE)
_RE_LEKAVOD = re.compile(r'(?:לכבוד|לידי)\s*:?\s*(.+)')
_RE_BE_AM   = re.compile(rf'בע[{_Q}]מ')
_RE_CUSTOMER_SECTION = re.compile(r'לכבוד|לידי|שם\s+הלקוח|For\s+billing|Bill\s+To', re.IGNORECASE)
_RE_SKIP_LINE = re.compile(
    r'^(?:עוסק|ח\.פ|ת\.ז|לכבוד|לידי|טלפון|מקור|עמוד|הופק|תאריך|לתשלום|'
    r'כתובת|נייד|אימייל|פירוט|תאור|פרוט|כמות|הקצאה|'
    r'page\b|invoice\s+#|tax\s+id|billing|from\s+invoice|bill\s+to|'
    r'total|subtotal|created|date\b|due\b|powered\s+by|http|www\.|[a-z0-9._%+\-]+@)',
    re.IGNORECASE,
)
_RE_TRAILING_NOISE = re.compile(
    r'\s*(?:מסמך\s+ממוחשב.*|\(\s*מקור\s*\).*|-\s*מקור.*|\d{1,2}[/.]\d{1,2}[/.]\d{2,4}.*)$'
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
    lines = text.splitlines()
    for i, line in enumerate(lines):
        is_doc_line = _RE_ESEK.search(line) or _RE_MAS.search(line) or _RE_TAX_EN.search(line)
        if is_doc_line and re.search(r'[A-Za-z0-9]{3,}', line):
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j].strip()
                if candidate and not _is_skip_line(candidate):
                    return _clean_name(candidate)

    # 4. First substantive line before the customer section
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('---'):
            continue
        if _RE_CUSTOMER_SECTION.search(stripped):
            break
        if not _is_skip_line(stripped):
            return _clean_name(stripped)

    return None


# ── Main entry point ───────────────────────────────────────────────────────────

def parse_invoice_text(text: str) -> Optional[dict]:
    """
    Parse normalised PDF text extracted by extract_text_from_pdf().

    Returns a dict for processable documents (חשבון עסקה / חשבונית מס),
    or None for receipts, combined invoice-receipts, and unrecognised types.

    Return shape:
        {
            "document_type": "tax_invoice" | "transaction_invoice",
            "business_name": str | None,
            "invoice_date":  str | None,   # DD/MM/YYYY
            "invoice_number": str | None,
            "amount": float | None,        # סה"כ לתשלום
        }
    """
    doc_type = classify_document_type(text)

    if doc_type not in {"חשבון עסקה", "חשבונית מס"}:
        return None

    return {
        "document_type":  "transaction_invoice" if doc_type == "חשבון עסקה" else "tax_invoice",
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


def _parse_amount(raw: str) -> Optional[float]:
    cleaned = re.sub(r'[₪$,\s]', '', raw)
    cleaned = re.sub(rf'(?:ILS|USD|EUR|GBP|ש[{_Q}\'"]+ח|בש[{_Q}]+ח)', '', cleaned).strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _clean_name(raw: str) -> Optional[str]:
    cleaned = _RE_TRAILING_NOISE.sub('', raw).strip()
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
