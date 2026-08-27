"""
Text normalization utilities for Hebrew/RTL content extracted from PDFs.

Background
----------
PDF text extraction tools (including pdfplumber) read character positions in
left-to-right visual order. For Hebrew PDFs, this reverses both the character
order within each word and the word order within each line.

  pdfplumber output : "דובכל"             "מ\"עב םוה הדנפ"
  expected          : "לכבוד"             "פנדה הום בע\"מ"

Strategy
--------
For each line that contains Hebrew:

  1. Split into whitespace-delimited tokens.
  2. Reverse the token sequence (fixes reversed word order).
  3. Within each token:
       - If the token contains Hebrew characters, protect embedded strong
         LTR runs (numbers, dates, Latin identifiers, URLs/emails), reverse
         the visual-order token, then restore those runs unchanged.
       - If the token contains NO Hebrew (digits, dates, currency, email, …)
         → leave it exactly as-is (preserves LTR-safe values like 02/02/2026,
         ₪2,921.68, phone numbers, IDs, email addresses).

Lines that contain no Hebrew pass through unchanged.

Limitations
-----------
- Multiple consecutive spaces within a line are collapsed to a single space.
  (split() + " ".join()).  Tab-based column alignment is lost.
- Works on visual-order PDFs.  If pdfplumber already produces logical-order
  Hebrew for a given PDF, applying this function will incorrectly re-reverse
  it.  There is currently no automatic detection of "already correct" text.
- Paragraph-level line-order reversal (whole paragraphs stored bottom-to-top)
  is not addressed here; handle at the page/paragraph level if needed.
"""

import re

# Covers the main Hebrew block (U+05D0–U+05EA), Hebrew extended (U+05F0–U+05F4)
# and the most common Hebrew presentation forms (U+FB1D–U+FB4E).
_HEBREW_RE = re.compile(r"[\u05d0-\u05ea\u05f0-\u05f4\ufb1d-\ufb4e]")

# Strong LTR runs that may be embedded in the same whitespace-delimited token
# as visual-order Hebrew. Separators are included only when surrounded by LTR
# content, so a boundary colon in ``3,307.00:כ\"הס`` remains outside the
# protected span and lands between the normalized label and amount.
_LTR_RUN_RE = re.compile(
    r"""
    (?:
        (?:https?://|www\.)
        [A-Za-z0-9][A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%+-]*
      | [A-Za-z0-9][A-Za-z0-9._%+-]*
        @[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}
      | [₪$€£]?[+-]?[0-9]+(?:[.,/:\-][0-9]+)*%?
      | [A-Za-z0-9]+(?:[._/@+\-][A-Za-z0-9]+)+
      | [A-Za-z]+
    )
    """,
    re.VERBOSE,
)


def _has_hebrew(text: str) -> bool:
    """Return True if *text* contains at least one Hebrew character."""
    return bool(_HEBREW_RE.search(text))


def _reverse_visual_token(token: str) -> str:
    """Reverse visual-order Hebrew without reversing embedded LTR runs."""
    if not _has_hebrew(token):
        return token

    protected: list[tuple[str, str]] = []
    marker_codepoint = 0xE000

    def protect(match: re.Match[str]) -> str:
        nonlocal marker_codepoint
        value = match.group(0)

        # URL matching is permissive, but punctuation separating a URL from
        # Hebrew belongs to the surrounding bidi token rather than the URL.
        trailing = ""
        while value and value[-1] in ":;,!?":
            trailing = value[-1] + trailing
            value = value[:-1]
        if not value:
            return match.group(0)

        while chr(marker_codepoint) in token:
            marker_codepoint += 1
        marker = chr(marker_codepoint)
        marker_codepoint += 1
        protected.append((marker, value))
        return marker + trailing

    protected_token = _LTR_RUN_RE.sub(protect, token)
    normalized = protected_token[::-1]
    for marker, value in protected:
        normalized = normalized.replace(marker, value)
    return normalized


def _fix_rtl_line(line: str) -> str:
    """
    Fix a single line of potentially reversed Hebrew text.

    Returns the line unchanged if it contains no Hebrew.
    """
    if not _has_hebrew(line):
        return line

    tokens = line.split()  # strips leading/trailing whitespace, collapses runs
    fixed = [_reverse_visual_token(token) for token in reversed(tokens)]
    return " ".join(fixed)


def normalize_rtl_text(text: str) -> str:
    """
    Normalize Hebrew RTL text extracted from a PDF page.

    Applies ``_fix_rtl_line`` to every line independently.  Lines that contain
    no Hebrew characters are returned verbatim.

    Args:
        text: Raw text as returned by pdfplumber (or equivalent extractor).

    Returns:
        Text with Hebrew words and word-order corrected to logical reading order.
    """
    return "\n".join(_fix_rtl_line(line) for line in text.splitlines())
