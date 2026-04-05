import re
from pathlib import Path
import pdfplumber

from ..utils.text_helpers import normalize_rtl_text

# Strip non-printable characters that some PDF font encodings emit as glyph
# placeholders: control chars (except tab/newline/CR) and the BMP Private Use Area
# (U+E000–U+F8FF), e.g. "חשבו\uf8ffית" instead of "חשבונית", or "\x00" mid-string.
_RE_PUA = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ue000-\uf8ff]')


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts all text from a PDF file and returns it as a single string.
    Private-use-area glyph artifacts are stripped, then Hebrew RTL text is
    normalized to logical reading order before returning.
    """
    pdf_file = Path(pdf_path)

    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_file}")

    all_text = []

    with pdfplumber.open(pdf_file) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            page_text = _RE_PUA.sub('', page_text)
            page_text = normalize_rtl_text(page_text)
            all_text.append(f"\n--- PAGE {page_number} ---\n{page_text}")

    return "\n".join(all_text)