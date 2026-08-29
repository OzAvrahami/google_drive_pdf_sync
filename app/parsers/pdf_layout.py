"""Native-PDF positional header analysis and supplier resolution.

Text parsing remains Panda's primary parser.  This module supplies a narrowly
gated positional override for the validated two-column customer/issuer merge
ambiguity and otherwise leaves parser output untouched.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

import pdfplumber

from app.parsers.supplier_validator import validate_supplier
from app.utils.text_helpers import normalize_rtl_text


logger = logging.getLogger(__name__)

ROW_TOP_TOLERANCE = 1.8
MIN_WIDE_SPAN = 180.0
HEADER_ABOVE = 120.0
HEADER_BELOW = 145.0

_RE_ADDRESSEE = re.compile(r"לכבוד|לידי")
_RE_DOCUMENT_TITLE = re.compile(
    r"חשב(?:ון|ונית)\s+(?:עסקה|עיסקה|חיוב|מס)|דרישת\s+תשלום",
)
_RE_ISSUER_REGISTRATION = re.compile(r"עוסק\s+(?:מורשה|פטור)")
_RE_CUSTOMER_REGISTRATION = re.compile(
    r"(?:ח\s*[.׳'\"]?\s*פ|ת\s*[.׳'\"]?\s*ז|מספר\s+לקוח)",
)
_RE_DATE = re.compile(r"\d{1,2}[/.]\d{1,2}[/.]\d{2,4}")
_RE_STRUCTURAL = re.compile(
    r"^(?:"
    r"מקור|לתשלום|תאריך|הופק|עמוד|מסמך|חתום|עוסק|ח\s*[.׳'\"]?\s*פ|"
    r"ת\s*[.׳'\"]?\s*ז|טלפון|נייד|כתובת|דוא[\"׳']?ל|כמות|פירוט|"
    r"תיאור|מחיר|סה[\"״]?כ|מע[\"״]?מ|חתימה"
    r")\b",
)
_RE_SERVICE_CONTENT = re.compile(
    r"^(?:סוג\s+מוצר\s*:|מוצר(?:/שירות)?\s*:|שירות\s*:|"
    r"עמלות\s+[א-ת]+\s+\d{4}\b)",
)
_RE_ADDRESS = re.compile(
    r"(?:\b(?:רחוב|רח׳|שדרות|כתובת|ת\.ד|קומה|מגדל)\b|\d+\s*,?\s*[א-ת])",
)
_RE_AMOUNT_OR_ID = re.compile(r"(?:₪|\b\d[\d,./:-]{3,}\b)")
_RE_UPPER_LATIN = re.compile(r"^[A-Z][A-Z0-9 .&_'/-]*$")
_RE_MIRRORED_RTL_PARENTHETICAL = re.compile(
    r"\)(?P<inner>[\u0590-\u05ff](?:[\u0590-\u05ff\s'\"׳״.-]{0,58}[\u0590-\u05ff])?)\("
)


@dataclass(frozen=True, slots=True)
class HeaderLine:
    top: float
    bottom: float
    text: str


@dataclass(frozen=True, slots=True)
class PositionalSupplierResolution:
    before_supplier: str
    after_supplier: str
    before_validation_score: int
    after_validation_score: int
    observation: Mapping[str, Any]


def _comparison_supplier(value: Any) -> str:
    return (
        " ".join(str(value or "").split())
        .replace("''", '"')
        .replace("``", '"')
        .replace("׳", "'")
        .replace("’", "'")
        .replace("״", '"')
        .replace("“", '"')
        .replace("”", '"')
    )


def has_required_layout_signals(normalized_text: str) -> bool:
    """Return whether text contains every semantic signal required by geometry."""

    return all(
        pattern.search(normalized_text)
        for pattern in (
            _RE_ADDRESSEE,
            _RE_ISSUER_REGISTRATION,
            _RE_CUSTOMER_REGISTRATION,
            _RE_DOCUMENT_TITLE,
        )
    )


def _word_center(word: Mapping[str, Any]) -> float:
    return (float(word.get("x0") or 0.0) + float(word.get("x1") or 0.0)) / 2


def group_rows(
    words: Sequence[Mapping[str, Any]], *, tolerance: float = ROW_TOP_TOLERANCE
) -> list[list[Mapping[str, Any]]]:
    rows: list[list[Mapping[str, Any]]] = []
    for word in sorted(
        words,
        key=lambda item: (
            float(item.get("top") or 0.0),
            float(item.get("x0") or 0.0),
        ),
    ):
        top = float(word.get("top") or 0.0)
        row = next(
            (
                candidate
                for candidate in rows
                if abs(float(candidate[0].get("top") or 0.0) - top) <= tolerance
            ),
            None,
        )
        if row is None:
            rows.append([word])
        else:
            row.append(word)
    return rows


def normalize_mirrored_rtl_parentheses(text: str) -> str:
    """Repair only mirrored parentheses around a reconstructed Hebrew phrase."""

    return _RE_MIRRORED_RTL_PARENTHETICAL.sub(
        lambda match: f"({match.group('inner')})",
        text,
    )


def row_text(words: Sequence[Mapping[str, Any]]) -> str:
    raw = " ".join(
        str(word.get("text") or "")
        for word in sorted(words, key=lambda item: float(item.get("x0") or 0.0))
        if str(word.get("text") or "").strip()
    )
    normalized = " ".join(normalize_rtl_text(raw).split())
    return normalize_mirrored_rtl_parentheses(normalized)


def _side_lines(
    rows: Sequence[Sequence[Mapping[str, Any]]],
    *,
    midpoint: float,
    side: str,
    minimum_top: float,
    maximum_top: float,
) -> list[HeaderLine]:
    result: list[HeaderLine] = []
    for row in rows:
        top = min(float(word.get("top") or 0.0) for word in row)
        if not minimum_top <= top <= maximum_top:
            continue
        selected = [
            word
            for word in row
            if (_word_center(word) >= midpoint) == (side == "right")
        ]
        if not selected:
            continue
        text = row_text(selected)
        if text:
            result.append(
                HeaderLine(
                    top=top,
                    bottom=max(float(word.get("bottom") or top) for word in selected),
                    text=text,
                )
            )
    return result


def _clean_addressee_text(text: str) -> str:
    return re.sub(r"^(?:לכבוד|לידי)\s*:?[ ]*", "", text).strip()


def _is_name_candidate(text: str) -> bool:
    candidate = _clean_addressee_text(text)
    if not candidate or not 1 <= len(candidate.split()) <= 7 or len(candidate) > 80:
        return False
    if re.search(r"\d", candidate):
        return False
    if _RE_DATE.search(candidate) or _RE_AMOUNT_OR_ID.search(candidate):
        return False
    if _RE_DOCUMENT_TITLE.search(candidate) or _RE_STRUCTURAL.search(candidate):
        return False
    if _RE_SERVICE_CONTENT.search(candidate) or _RE_ADDRESS.search(candidate):
        return False
    if "@" in candidate or not re.search(r"[A-Za-z\u05d0-\u05ea]", candidate):
        return False
    return True


def _nearest_distance(top: float, lines: Sequence[HeaderLine]) -> float | None:
    return min((abs(top - line.top) for line in lines), default=None)


def _candidate_score(
    line: HeaderLine,
    *,
    anchor_top: float,
    registration_lines: Sequence[HeaderLine],
) -> int:
    score = 1
    anchor_distance = abs(line.top - anchor_top)
    if anchor_distance <= 3:
        score += 4
    elif anchor_distance <= 30:
        score += 3
    elif anchor_distance <= 120:
        score += 1
    registration_distance = _nearest_distance(line.top, registration_lines)
    if registration_distance is not None:
        if registration_distance <= 45:
            score += 4
        elif registration_distance <= 85:
            score += 2
    if _RE_UPPER_LATIN.fullmatch(line.text):
        score += 1
    if re.search(r"בע[\"״'׳]{0,2}מ|\b(?:Ltd|LLC|Inc)\b", line.text, re.IGNORECASE):
        score += 2
    return score


def _best_name_line(
    lines: Sequence[HeaderLine],
    *,
    anchor_top: float,
    registration_lines: Sequence[HeaderLine],
) -> tuple[HeaderLine | None, int]:
    candidates = [line for line in lines if _is_name_candidate(line.text)]
    if not candidates:
        return None, 0
    scored = [
        (
            _candidate_score(
                line,
                anchor_top=anchor_top,
                registration_lines=registration_lines,
            ),
            -abs(line.top - anchor_top),
            -line.top,
            line,
        )
        for line in candidates
    ]
    scored.sort(key=lambda item: item[:3], reverse=True)
    return scored[0][3], scored[0][0]


def _customer_name_line(
    lines: Sequence[HeaderLine], *, anchor_top: float
) -> HeaderLine | None:
    candidates: list[HeaderLine] = []
    for line in lines:
        if not anchor_top - 3 <= line.top <= anchor_top + 65:
            continue
        text = _clean_addressee_text(line.text)
        if not _is_name_candidate(text):
            continue
        candidates.append(HeaderLine(line.top, line.bottom, text))
    return min(candidates, key=lambda line: (abs(line.top - anchor_top), line.top), default=None)


def _line_dict(line: HeaderLine) -> dict[str, Any]:
    return {"text": line.text, "top": round(line.top, 3), "bottom": round(line.bottom, 3)}


def _full_lines(
    rows: Sequence[Sequence[Mapping[str, Any]]],
    *,
    minimum_top: float,
    maximum_top: float,
) -> list[HeaderLine]:
    result: list[HeaderLine] = []
    for row in rows:
        top = min(float(word.get("top") or 0.0) for word in row)
        if not minimum_top <= top <= maximum_top:
            continue
        text = row_text(row)
        if text:
            result.append(
                HeaderLine(
                    top=top,
                    bottom=max(float(word.get("bottom") or top) for word in row),
                    text=text,
                )
            )
    return result


def analyze_page_header(
    page: Mapping[str, Any],
    *,
    current_supplier: str | None = None,
) -> list[dict[str, Any]]:
    """Return strict positional observations for wide addressee header rows."""

    width = float(page.get("width") or 0.0)
    midpoint = width / 2
    rows = group_rows(list(page.get("words") or []))
    observations: list[dict[str, Any]] = []
    for row in rows:
        normalized_words = [
            normalize_rtl_text(str(word.get("text") or "")) for word in row
        ]
        anchor_words = [
            word
            for word, normalized in zip(row, normalized_words)
            if _RE_ADDRESSEE.search(normalized)
        ]
        if not anchor_words:
            continue
        span = max(float(word.get("x1") or 0.0) for word in row) - min(
            float(word.get("x0") or 0.0) for word in row
        )
        if span < MIN_WIDE_SPAN:
            continue

        anchor_word = max(anchor_words, key=_word_center)
        anchor_top = float(anchor_word.get("top") or 0.0)
        anchor_side = "right" if _word_center(anchor_word) >= midpoint else "left"
        opposite_side = "left" if anchor_side == "right" else "right"
        minimum_top = max(0.0, anchor_top - HEADER_ABOVE)
        maximum_top = anchor_top + HEADER_BELOW
        anchor_lines = _side_lines(
            rows,
            midpoint=midpoint,
            side=anchor_side,
            minimum_top=minimum_top,
            maximum_top=maximum_top,
        )
        opposite_lines = _side_lines(
            rows,
            midpoint=midpoint,
            side=opposite_side,
            minimum_top=minimum_top,
            maximum_top=maximum_top,
        )
        full_lines = _full_lines(
            rows,
            minimum_top=minimum_top,
            maximum_top=maximum_top,
        )
        issuer_registration = [
            line for line in opposite_lines if _RE_ISSUER_REGISTRATION.search(line.text)
        ]
        customer_registration = [
            line for line in anchor_lines if _RE_CUSTOMER_REGISTRATION.search(line.text)
        ]
        issuer, issuer_score = _best_name_line(
            opposite_lines,
            anchor_top=anchor_top,
            registration_lines=issuer_registration,
        )
        customer = _customer_name_line(anchor_lines, anchor_top=anchor_top)
        titles = [
            line
            for line in full_lines
            if _RE_DOCUMENT_TITLE.search(line.text)
        ]
        branding = [
            line
            for line in opposite_lines
            if issuer is not None
            and line != issuer
            and _is_name_candidate(line.text)
            and abs(line.top - issuer.top) <= 35
        ]
        title_separable = bool(
            titles
            and issuer
            and customer
            and min(
                min(abs(title.top - issuer.top), abs(title.top - customer.top))
                for title in titles
            )
            >= 20
        )

        evidence: list[str] = []
        if issuer:
            evidence.append(f"opposite candidate {issuer.text!r}")
        if issuer_registration:
            evidence.append("opposite block has issuer registration evidence")
        if customer:
            evidence.append(f"addressee-side customer {customer.text!r}")
        if customer_registration:
            evidence.append("addressee block has customer registration evidence")
        if title_separable:
            evidence.append("document title is spatially separate from entity blocks")

        high_confidence = bool(
            issuer
            and issuer_score >= 8
            and issuer_registration
            and customer
            and customer_registration
            and title_separable
        )
        current_normalized = _comparison_supplier(current_supplier)
        customer_normalized = _comparison_supplier(customer.text if customer else "")
        issuer_normalized = _comparison_supplier(issuer.text if issuer else "")
        current_looks_customer = bool(
            current_normalized
            and customer_normalized
            and current_normalized.startswith(customer_normalized)
        )
        would_change = bool(
            high_confidence
            and current_looks_customer
            and issuer_normalized
            and issuer_normalized != current_normalized
        )
        observations.append(
            {
                "page": int(page.get("page") or 1),
                "page_width": width,
                "anchor": {
                    "text": normalize_rtl_text(str(anchor_word.get("text") or "")),
                    "side": anchor_side,
                    "top": round(anchor_top, 3),
                    "x0": round(float(anchor_word.get("x0") or 0.0), 3),
                    "x1": round(float(anchor_word.get("x1") or 0.0), 3),
                    "row_span": round(span, 3),
                },
                "issuer_candidate": _line_dict(issuer) if issuer else None,
                "issuer_candidate_score": issuer_score,
                "issuer_registration_evidence": [
                    _line_dict(line) for line in issuer_registration
                ],
                "issuer_branding_evidence": [_line_dict(line) for line in branding],
                "customer_candidate": _line_dict(customer) if customer else None,
                "customer_registration_evidence": [
                    _line_dict(line) for line in customer_registration
                ],
                "document_title_region": [_line_dict(line) for line in titles],
                "title_spatially_separate": title_separable,
                "opposite_block_lines": [_line_dict(line) for line in opposite_lines],
                "addressee_block_lines": [_line_dict(line) for line in anchor_lines],
                "positional_confidence": "high" if high_confidence else (
                    "medium" if issuer and issuer_registration else "low"
                ),
                "proposal": {
                    "supplier": issuer.text if would_change and issuer else None,
                    "would_change": would_change,
                    "evidence": evidence,
                },
            }
        )
    return observations


def extract_word_pages(pdf_path: str | Path) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    with pdfplumber.open(Path(pdf_path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            pages.append(
                {
                    "page": page_number,
                    "width": float(page.width),
                    "height": float(page.height),
                    "words": page.extract_words(),
                }
            )
    return pages


def analyze_pdf_layout(
    pdf_path: str | Path | None = None,
    *,
    current_supplier: str | None = None,
    pages: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if pages is None:
        if pdf_path is None:
            raise ValueError("pdf_path or pages is required for positional analysis")
        pages = extract_word_pages(pdf_path)
    observations: list[dict[str, Any]] = []
    for page in pages:
        observations.extend(
            analyze_page_header(page, current_supplier=current_supplier)
        )
    return observations


def best_supplier_proposal(
    observations: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    proposals = [
        observation
        for observation in observations
        if (observation.get("proposal") or {}).get("would_change")
    ]
    if not proposals:
        return None
    return max(
        proposals,
        key=lambda item: (
            int(item.get("issuer_candidate_score") or 0),
            float((item.get("anchor") or {}).get("row_span") or 0.0),
        ),
    )


def _validation_payload(candidate: str, validation: Any) -> dict[str, Any]:
    return {
        "original": candidate,
        "score": validation.score,
        "is_valid": validation.is_valid,
        "rejection_reason": validation.rejection_reason,
        "triggered_rule": validation.triggered_rule,
        "fallback_used": validation.fallback_used,
        "fallback_candidate": validation.fallback_candidate,
        "address_score": validation.address_score,
    }


def apply_positional_supplier_override(
    parsed: MutableMapping[str, Any] | None,
    normalized_text: str,
    *,
    pdf_path: str | Path | None = None,
    pages: Sequence[Mapping[str, Any]] | None = None,
) -> PositionalSupplierResolution | None:
    """Apply the strict positional supplier override, or leave *parsed* unchanged."""

    if not parsed or not parsed.get("business_name"):
        return None
    if not has_required_layout_signals(normalized_text):
        return None
    before_supplier = str(parsed["business_name"])
    try:
        observations = analyze_pdf_layout(
            pdf_path,
            current_supplier=before_supplier,
            pages=pages,
        )
    except Exception as exc:
        logger.warning(
            "Optional positional supplier analysis failed for %s: %s",
            pdf_path or "in-memory pages",
            exc,
        )
        return None
    observation = best_supplier_proposal(observations)
    if observation is None:
        return None
    proposal = str((observation.get("proposal") or {}).get("supplier") or "")
    if not proposal:
        return None

    validation = validate_supplier(proposal, normalized_text)
    if (
        not validation.is_valid
        or validation.fallback_used
        or not validation.name
        or _comparison_supplier(validation.name) != _comparison_supplier(proposal)
    ):
        return None

    before_score = int((parsed.get("supplier_validation") or {}).get("score") or 0)
    parsed["business_name"] = validation.name
    parsed["supplier_validation"] = _validation_payload(proposal, validation)
    return PositionalSupplierResolution(
        before_supplier=before_supplier,
        after_supplier=validation.name,
        before_validation_score=before_score,
        after_validation_score=validation.score,
        observation=observation,
    )
