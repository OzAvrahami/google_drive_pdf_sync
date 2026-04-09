"""
Supplier validation and scoring layer.

Sits on top of the raw invoice_parser extraction.  Given a candidate
supplier name and the full document text, this module:

  1. Rejects candidates that look like street addresses.
  2. Applies learned rules (date-like, phone, tax-ID, repeated-literal).
  3. Scores the candidate on a 0–100 scale.
  4. Tries fallback candidates when the primary is invalid.
  5. Returns a ValidationResult with full debug info.

Rules are loaded from two files:
  - data/supplier_rules.json  — hand-authored base rules (static)
  - data/learned_rules.json   — machine-inferred rules (grows over time)

Call invalidate_rules_cache() after writing new learned rules so they take
effect on the next document without restarting the application.

Public API
----------
is_probable_address(text)               -> bool
is_probable_supplier(text)              -> bool
validate_supplier(candidate, full_text) -> ValidationResult
invalidate_rules_cache()                -> None
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import LEARNED_RULES_JSON, SUPPLIER_RULES_JSON

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────

_ADDRESS_THRESHOLD  = 40   # address_score >= this → is_probable_address
_SUPPLIER_THRESHOLD = 25   # supplier_score >= this → is_probable_supplier
_FALLBACK_THRESHOLD = 20   # minimum score for a fallback candidate to be used
_FALLBACK_SCAN_LINES = 40  # how many lines to scan when hunting for a fallback

# ── Hebrew city list ──────────────────────────────────────────────────────────

_ISRAELI_CITIES: frozenset[str] = frozenset({
    "תל אביב", "ירושלים", "חיפה", "ראשון לציון", "פתח תקווה",
    "אשדוד", "נתניה", "באר שבע", "בני ברק", "הרצליה",
    "חולון", "רמת גן", "אשקלון", "רחובות", "בת ים",
    "כפר סבא", "מודיעין", "רעננה", "הוד השרון", "לוד",
    "רמלה", "נס ציונה", "עפולה", "חדרה", "נהריה",
    "גבעתיים", "אילת", "קריית גת", "צפת", "טבריה",
    "יהוד", "אור יהודה", "גבעת שמואל", "קרית אונו",
    "פרדס חנה", "זכרון יעקב", "עכו", "ראש העין",
    "אלעד", "ביתר עילית", "אריאל", "מעלה אדומים",
    "כפר יונה", "שפרעם", "נצרת", "יפו",
})

# ── Compiled patterns ─────────────────────────────────────────────────────────

_Q = '"\u05f4\u201c\u201d'

_RE_BE_AM      = re.compile(rf'בע[{_Q}]מ')
_RE_BIZ_WORDS  = re.compile(
    r'חברה|שירותים|שירות|קבלן|קבלנות|בית\s+\S+|'
    r'מרכז|מוסד|עמותה|אגודה|קואופרטיב|'
    r'\bInc\b|\bLtd\b|\bCorp\b|\bLLC\b|\bCo\b',
    re.IGNORECASE,
)
_RE_HEB        = re.compile(r'[\u05D0-\u05EA]')
_RE_DIGIT      = re.compile(r'\d')
_RE_SHORT_NUM  = re.compile(r'(?<!\d)\d{1,4}(?!\d)')

# Address patterns
_RE_ADDR_A = re.compile(            # "Hebrew words <number>, Hebrew word"
    r'[\u05D0-\u05EA][\u05D0-\u05EA\s\-\'\"]{1,30}'
    r'\s+\d{1,4}\s*,\s*[\u05D0-\u05EA]{2,}',
)
_RE_ADDR_B = re.compile(r'^\d{1,4}\s+[\u05D0-\u05EA]')   # "23 הרצליה"
_RE_ADDR_C = re.compile(r'\d\s*,|,\s*\d')                  # digit near comma

# Learned-rule pattern matchers
_RE_DATE_LIKE = re.compile(r'^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}$')
_RE_PHONE_IL  = re.compile(r'^0[2-9][\d\-\s]{7,10}$')
_RE_TAX_ID    = re.compile(
    r'(?:ח["\'.]\s*פ|ת["\'.]\s*ז|עוסק\s*מורשה)\s*[:\s/]?\s*\d{5,}',
    re.IGNORECASE,
)

# Fallback scan filters
_RE_PAGE_SEP   = re.compile(r'^-+\s*PAGE', re.IGNORECASE)
_RE_SKIP       = re.compile(
    r'^(?:עוסק|ח\.פ|ת\.ז|לכבוד|לידי|טלפון|מקור|עמוד|הופק|תאריך|לתשלום|'
    r'כתובת|נייד|אימייל|פירוט|תאור|פרוט|כמות|הקצאה|שם\s*:|'
    r'מספר\s+(?:פנימי|הקצאה|עוסק|לקוח|חשבון)\b|'
    r'page\b|invoice\s*#|tax\s+id|billing|bill\s+to|total|subtotal|'
    r'created|date\b|due\b|powered\s+by|http|www\.|[a-z0-9._%+\-]+@)',
    re.IGNORECASE,
)
_RE_ONLY_PUNCT = re.compile(r'^[\d\s/.\-:,+()₪$€£]+$')

# ── Default base rules (written to disk if the file is absent) ────────────────

_DEFAULT_BASE_RULES: dict = {
    "version": 1,
    "global": {
        "prefer_keywords": ["בע\"מ", "חברה", "שירותים", "קבלן"],
    },
    "suppliers": {},
}

# ── Rules cache ───────────────────────────────────────────────────────────────
# Using a plain module-level variable instead of @lru_cache so that
# invalidate_rules_cache() can force a reload after learning writes new rules.

_rules_cache: Optional[dict] = None


def invalidate_rules_cache() -> None:
    """Force the next validate_supplier() call to reload rules from disk."""
    global _rules_cache
    _rules_cache = None


def _load_rules() -> dict:
    global _rules_cache
    if _rules_cache is None:
        _rules_cache = _load_rules_from_disk()
    return _rules_cache


def _load_rules_from_disk() -> dict:
    """
    Load and merge base rules (supplier_rules.json) and learned rules
    (learned_rules.json) into a single dict used during validation.
    """
    base    = _read_json(SUPPLIER_RULES_JSON, _DEFAULT_BASE_RULES)
    learned = _read_json(LEARNED_RULES_JSON, {"version": 1, "rules": []})

    # Write defaults if the base file didn't exist yet.
    if not SUPPLIER_RULES_JSON.exists():
        _write_json(SUPPLIER_RULES_JSON, _DEFAULT_BASE_RULES)

    # Attach learned rules under a separate key so _apply_learned_rules()
    # can access them without mixing them with hand-authored global rules.
    base["learned"] = learned.get("rules", [])
    return base


def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning("Could not read %s: %s — using defaults.", path.name, exc)
        return dict(default)


def _write_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except Exception as exc:
        logger.warning("Could not write %s: %s", path.name, exc)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Full result of a supplier validation check."""

    name:             Optional[str]    # Final supplier name (may be a fallback)
    score:            int              # 0–100 supplier confidence score
    is_valid:         bool             # False → name was rejected
    rejection_reason: Optional[str]   # Human-readable reason for rejection
    triggered_rule:   Optional[str]   # Which rule key fired
    fallback_used:    bool             # True → fallback candidate was substituted
    fallback_candidate: Optional[str] # The fallback name (if used)
    address_score:    int              # Internal: raw address heuristic score
    debug_notes:      list[str]        # Step-by-step trace


# ── Public API ────────────────────────────────────────────────────────────────

def is_probable_address(text: str) -> bool:
    """
    Return True if *text* looks like a street address rather than a supplier.

    Heuristic signals:
      - "<Hebrew words> <number>, <Hebrew word>" pattern  (+50)
      - Starts with a number followed by Hebrew            (+30)
      - Contains a known Israeli city name                 (+25)
      - Digit adjacent to a comma                         (+15)
      - Any short standalone number                       (+10)
      - בע"מ / business words act as strong counter-signals (-40 / -25)

    Classified as address when score >= 40.
    """
    return _address_score(text) >= _ADDRESS_THRESHOLD


def is_probable_supplier(text: str) -> bool:
    """
    Return True if *text* looks like a valid supplier name.

    Any text that passes is_probable_address is rejected outright.
    """
    if not text or not text.strip():
        return False
    if is_probable_address(text):
        return False
    score, _ = _supplier_score(text, position=0, rules=_load_rules())
    return score >= _SUPPLIER_THRESHOLD


def validate_supplier(
    candidate: Optional[str],
    full_text: str,
) -> ValidationResult:
    """
    Validate *candidate* as a supplier name against *full_text*.

    Validation pipeline:
      1. Empty → attempt fallback immediately.
      2. Address check  → reject + fallback.
      3. Learned rules  → reject + fallback.
      4. Score accepted candidate.
      5. Return ValidationResult with full debug trace.
    """
    rules  = _load_rules()
    notes: list[str] = []
    return _validate(candidate, full_text, rules, notes)


# ── Core validation ───────────────────────────────────────────────────────────

def _validate(
    candidate: Optional[str],
    full_text: str,
    rules:     dict,
    notes:     list[str],
) -> ValidationResult:

    # 1. Empty candidate ──────────────────────────────────────────────────────
    if not candidate or not candidate.strip():
        notes.append("No candidate — attempting fallback.")
        return _fallback_result(None, None, full_text, rules, notes,
                                rejection_reason="No supplier extracted",
                                triggered_rule="empty_candidate",
                                address_score=0)

    # 2. Address check ────────────────────────────────────────────────────────
    addr_score = _address_score(candidate)
    notes.append(f"Address score for {candidate!r}: {addr_score}")

    if addr_score >= _ADDRESS_THRESHOLD:
        rejection = "Extracted text looks like a street address"
        triggered = "address_pattern"
        notes.append(f"REJECTED ({triggered}): score={addr_score}")
        return _fallback_result(candidate, triggered, full_text, rules, notes,
                                rejection_reason=rejection,
                                triggered_rule=triggered,
                                address_score=addr_score)

    # 3. Learned rules ────────────────────────────────────────────────────────
    learned_rejection = _apply_learned_rules(candidate, rules.get("learned", []), notes)
    if learned_rejection:
        return _fallback_result(candidate, learned_rejection, full_text, rules, notes,
                                rejection_reason=f"Learned rule: {learned_rejection}",
                                triggered_rule=learned_rejection,
                                address_score=addr_score)

    # 4. Score the accepted candidate ─────────────────────────────────────────
    position = _line_position(candidate, full_text)
    score, score_notes = _supplier_score(candidate, position=position, rules=rules)
    notes.extend(score_notes)
    notes.append(f"Final score: {score}")

    return ValidationResult(
        name=candidate, score=score, is_valid=True,
        rejection_reason=None, triggered_rule=None,
        fallback_used=False, fallback_candidate=None,
        address_score=addr_score, debug_notes=notes,
    )


def _fallback_result(
    rejected:         Optional[str],
    triggered:        Optional[str],
    full_text:        str,
    rules:            dict,
    notes:            list[str],
    *,
    rejection_reason: Optional[str],
    triggered_rule:   Optional[str],
    address_score:    int,
) -> ValidationResult:
    """Attempt a fallback and build a ValidationResult in one place."""
    fallback = _find_best_candidate(full_text, rules, notes, exclude=rejected)

    if fallback:
        f_score, f_notes = _supplier_score(fallback, position=0, rules=rules)
        notes.extend(f_notes)
        notes.append(f"Fallback accepted: {fallback!r} (score={f_score})")
        return ValidationResult(
            name=fallback, score=f_score, is_valid=True,
            rejection_reason=rejection_reason, triggered_rule=triggered_rule,
            fallback_used=True, fallback_candidate=fallback,
            address_score=address_score, debug_notes=notes,
        )

    notes.append("No valid fallback found.")
    return ValidationResult(
        name=None, score=0, is_valid=False,
        rejection_reason=rejection_reason, triggered_rule=triggered_rule,
        fallback_used=False, fallback_candidate=None,
        address_score=address_score, debug_notes=notes,
    )


# ── Address scoring ───────────────────────────────────────────────────────────

def _address_score(text: str) -> int:
    if not text or not text.strip():
        return 0

    t     = text.strip()
    score = 0

    if _RE_ADDR_A.search(t):    score += 50   # "<Hebrew> <num>, <Hebrew>"
    if _RE_ADDR_B.search(t):    score += 30   # starts with number
    if _RE_ADDR_C.search(t):    score += 15   # digit near comma
    if _RE_SHORT_NUM.search(t): score += 10   # any short standalone number

    for city in _ISRAELI_CITIES:
        if city in t:
            score += 25
            break

    if _RE_BE_AM.search(t):    score -= 40   # strong negative: בע"מ
    if _RE_BIZ_WORDS.search(t): score -= 25  # moderate negative: business word

    return max(0, score)


# ── Supplier scoring ──────────────────────────────────────────────────────────

def _supplier_score(
    text:     str,
    position: int,
    rules:    dict,
) -> tuple[int, list[str]]:
    """
    Score a supplier candidate from 0 to 100.  Returns (score, debug_notes).
    """
    notes: list[str] = []
    score = 0

    if not text or not text.strip():
        return 0, ["Empty — score 0"]

    t = text.strip()

    # Immediate disqualifier: looks like an address
    if _address_score(t) >= _ADDRESS_THRESHOLD:
        notes.append("Looks like an address — score capped at 5")
        return 5, notes

    # Business indicators
    if _RE_BE_AM.search(t):
        score += 40
        notes.append('+40 contains בע"מ')
    elif _RE_BIZ_WORDS.search(t):
        score += 25
        notes.append("+25 contains business keyword")

    # Text quality
    words     = t.split()
    n_words   = len(words)
    has_digit = bool(_RE_DIGIT.search(t))
    has_heb   = bool(_RE_HEB.search(t))

    if has_heb and not has_digit and 2 <= n_words <= 5:
        score += 25
        notes.append(f"+25 clean Hebrew name ({n_words} words)")
    elif has_heb and not has_digit and n_words == 1:
        score += 10
        notes.append("+10 single Hebrew word")
    elif has_digit and n_words <= 4:
        score -= 15
        notes.append("-15 contains digit(s)")

    if len(t) < 3:
        score -= 10
        notes.append("-10 too short")
    elif len(t) > 60:
        score -= 10
        notes.append("-10 too long")

    # Position bonus
    if 0 < position <= 5:
        score += 20
        notes.append(f"+20 near top (line {position})")
    elif 6 <= position <= 12:
        score += 15
        notes.append(f"+15 early in document (line {position})")
    elif 13 <= position <= 25:
        score += 10
        notes.append(f"+10 within first 25 lines (line {position})")

    # Prefer-keywords from base rules
    for kw in rules.get("global", {}).get("prefer_keywords", []):
        if kw in t:
            score += 10
            notes.append(f"+10 prefer_keyword {kw!r}")
            break

    # Known supplier aliases
    for key, data in rules.get("suppliers", {}).items():
        for alias in data.get("known_names", []):
            if alias.lower() in t.lower():
                boost = data.get("boost", 15)
                score += boost
                notes.append(f"+{boost} known supplier {key!r}")
                break

    return max(0, min(100, score)), notes


# ── Learned rule application ──────────────────────────────────────────────────

def _apply_learned_rules(
    candidate:     str,
    learned_rules: list[dict],
    notes:         list[str],
) -> Optional[str]:
    """
    Check *candidate* against learned rules.

    Returns a short rejection description if any rule fires, else None.
    Each rule has a pattern_type that maps to a compiled regex or an
    exact-value check.
    """
    t = candidate.strip()

    for rule in learned_rules:
        if rule.get("action") != "reject":
            continue
        if rule.get("field") not in ("supplier_name", None):
            continue

        ptype   = rule.get("pattern_type")
        rule_id = rule.get("id", "?")

        if ptype == "date_like" and _RE_DATE_LIKE.match(t):
            msg = f"date_like [{rule_id}]"
            notes.append(f"REJECTED by learned rule: {msg}")
            return msg

        if ptype == "phone_number" and _RE_PHONE_IL.match(t):
            msg = f"phone_number [{rule_id}]"
            notes.append(f"REJECTED by learned rule: {msg}")
            return msg

        if ptype == "tax_id" and _RE_TAX_ID.search(t):
            msg = f"tax_id [{rule_id}]"
            notes.append(f"REJECTED by learned rule: {msg}")
            return msg

        if ptype == "literal" and t == (rule.get("value") or "").strip():
            msg = f"literal [{rule_id}]: {t!r}"
            notes.append(f"REJECTED by learned rule: {msg}")
            return msg

    return None


# ── Fallback candidate scan ───────────────────────────────────────────────────

def _find_best_candidate(
    full_text: str,
    rules:     dict,
    notes:     list[str],
    exclude:   Optional[str] = None,
) -> Optional[str]:
    """
    Scan the first _FALLBACK_SCAN_LINES of *full_text* for the best-scoring
    supplier candidate that is not *exclude*.
    """
    lines:  list[str]          = full_text.splitlines()[:_FALLBACK_SCAN_LINES]
    scored: list[tuple[int, str]] = []

    for lineno, raw in enumerate(lines, 1):
        c = raw.strip()
        if not c or len(c) < 2:         continue
        if _RE_PAGE_SEP.match(c):       continue
        if _RE_SKIP.match(c):           continue
        if _RE_ONLY_PUNCT.match(c):     continue
        if exclude and c == exclude:    continue
        if _address_score(c) >= _ADDRESS_THRESHOLD: continue

        sc, _ = _supplier_score(c, position=lineno, rules=rules)
        if sc >= _FALLBACK_THRESHOLD:
            scored.append((sc, c))

    if not scored:
        notes.append("Fallback scan: no candidates above threshold.")
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    notes.append(
        f"Fallback scan: {best!r} (score={best_score}, {len(scored)} candidate(s))."
    )
    return best


# ── Helpers ───────────────────────────────────────────────────────────────────

def _line_position(candidate: str, full_text: str) -> int:
    """Return 1-based line number of *candidate* in *full_text*, or 0."""
    for i, line in enumerate(full_text.splitlines(), 1):
        if candidate in line:
            return i
    return 0
