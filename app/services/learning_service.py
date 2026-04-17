"""
Correction-driven learning service.

When the accountant saves a correction in the review dialog:

  1. record_and_learn() is called with field + original + corrected values.
  2. The raw correction is appended atomically to corrections_log.json.
  3. _infer_rule() inspects the original value for a known bad pattern.
  4. If a generalizable rule is found (and isn't already known), it is written
     to learned_rules.json and the validator cache is invalidated so the rule
     takes effect on the next document without restarting the app.

Rule inference is conservative to prevent rule explosion:
  - Address-like supplier: already caught by base rules → NOT duplicated.
  - Date-like value as wrong field: rule created on first occurrence.
  - Phone number / tax-ID as supplier: rule created on first occurrence.
  - Repeated-literal errors: rule created only after 3 identical corrections.
  - One-off OCR noise: logged only, no rule created.

Public API
----------
record_and_learn(field_name, original_value, corrected_value,
                 drive_file_id, file_name) -> str | None
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import CORRECTIONS_LOG_JSON, LEARNED_RULES_JSON

logger = logging.getLogger(__name__)

# A correction must occur this many times before a generic "literal" rule fires.
_LITERAL_RULE_THRESHOLD = 3

# ── Patterns for detecting known-bad field values ─────────────────────────────

# Matches DD/MM/YYYY, DD.MM.YYYY, etc.
_RE_DATE_LIKE = re.compile(r'^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}$')
# Israeli mobile/landline: 05X-XXXXXXX or 0X-XXXXXXX
_RE_PHONE_IL  = re.compile(r'^0[2-9][\d\-\s]{7,10}$')
# Company/personal ID line (e.g. "ח.פ 123456789" or "עוסק מורשה: 123")
_RE_TAX_ID    = re.compile(r'(?:ח["\'.]\s*פ|ת["\'.]\s*ז|עוסק\s*מורשה)\s*[:\s/]?\s*\d{5,}',
                            re.IGNORECASE)

# ── Supplier correction safety classification ─────────────────────────────────

# Entity markers: if the extracted supplier value contains these, the parser
# found a REAL business/person name in the wrong document role (customer vs.
# supplier).  Storing this as a global correction key is dangerous because
# the same entity could legitimately be the supplier on a different invoice.
_RE_ENTITY_MARKER = re.compile(
    r'בע["\u05f4]?מ'           # בע"מ / בע״מ  (Ltd)
    r'|ח["\'.]\s*פ'            # ח.פ  (company registration)
    r'|ת["\'.]\s*ז'            # ת.ז  (personal ID)
    r'|עוסק\s*מורשה'           # authorized dealer
    r'|שותפות'                 # partnership
    r'|inc\.|ltd\.|llc\.',
    re.IGNORECASE,
)

# Document-structure noise: these phrases appear verbatim across many PDFs
# that share the same template layout.  A single-document correction that
# maps one of these phrases to a supplier name would fire on every document
# from that template, injecting the wrong supplier everywhere.
_RE_DOC_STRUCTURE_NOISE = re.compile(
    r'(?:^|\b)(?:'
    r'דף\s*[:\-]?\s*\d'         # דף: 1 / דף 1   (page header)
    r'|חתום\s+דיגיטלי'          # חתום דיגיטלית  (digital signature line)
    r'|מסמך\s+ממוחשב'           # מסמך ממוחשב    (computerized document footer)
    r'|(?:^|\s)מקור(?:\s|$)'    # מקור            (original — standalone)
    r'|הקצאה\b'                 # הקצאה           (allocation)
    r'|בגין\b'                  # בגין            (regarding / for the purpose of)
    r'|עמוד\s+\d'               # עמוד 1          (page N)
    r'|page\s+\d'               # page 1
    r')',
    re.IGNORECASE,
)


def _supplier_correction_safety(extracted_value: str) -> Optional[str]:
    """
    Classify whether a supplier_name correction is safe to promote to the
    global correction_map.

    Returns a human-readable reason string when the correction is RISKY and
    should be kept as audit log only.
    Returns None when it IS safe to store as a reusable global rule.

    Safe:   dates, phone numbers, tax IDs, short OCR gibberish specific to
            one document — unlikely to collide across unrelated invoices.

    Risky:  real entity names (contains בע"מ / ח.פ / etc.) — the parser got
            the ROLE wrong, not the text.  Document-structure phrases (דף: 1,
            חתום דיגיטלית) — appear in many PDFs from the same template.
    """
    if not extracted_value or not extracted_value.strip():
        return "empty extracted value"

    if _RE_ENTITY_MARKER.search(extracted_value):
        return (
            "contains an entity marker (בע\"מ / ח.פ / etc.) — the parser "
            "confused document role (customer vs. supplier), not the text; "
            "storing this key globally would contaminate documents where this "
            "entity is the correct supplier"
        )

    if _RE_DOC_STRUCTURE_NOISE.search(extracted_value):
        return (
            "matches a document-structure noise pattern (page header, "
            "digital-signature line, etc.) — this phrase appears in many "
            "PDFs sharing the same template and must not become a global rule"
        )

    return None  # Safe to promote to global correction_map

# Fields whose extracted values should be checked for known-bad patterns.
# Maps UI/Document field name → parser extracted_data key.
_FIELD_ALIAS: dict[str, str] = {
    "supplier_name":  "business_name",
    "invoice_date":   "invoice_date",
    "invoice_number": "invoice_number",
    "total":          "amount",
}


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Correction:
    field_name:      str           # e.g. "supplier_name", "invoice_number"
    original_value:  str           # what the parser extracted
    corrected_value: str           # what the accountant typed
    drive_file_id:   str
    file_name:       str
    timestamp:       str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Public API ────────────────────────────────────────────────────────────────

def record_and_learn(
    field_name:      str,
    original_value:  str,
    corrected_value: str,
    drive_file_id:   str,
    file_name:       str,
) -> Optional[str]:
    """
    Record a correction and attempt to infer a reusable rule from it.

    Returns a human-readable description of the rule that was created,
    or None if no rule was created (correction was logged but not generalised).
    """
    original_value  = (original_value  or "").strip()
    corrected_value = (corrected_value or "").strip()

    if original_value == corrected_value:
        return None   # Nothing actually changed — ignore.

    correction = Correction(
        field_name=field_name,
        original_value=original_value,
        corrected_value=corrected_value,
        drive_file_id=drive_file_id,
        file_name=file_name,
    )

    _append_correction(correction)
    _record_positive_correction(correction)
    return _maybe_create_rule(correction)


# ── Rule inference ────────────────────────────────────────────────────────────

def _infer_rule(correction: Correction) -> Optional[dict]:
    """
    Inspect *correction.original_value* for a known bad pattern.

    Returns a partial rule dict (without id / created_at) if a generalizable
    rule can be inferred, or None for one-off noise.
    """
    original = correction.original_value
    field    = correction.field_name

    if field == "supplier_name":
        # Address: already caught by the base supplier_rules.json — do not duplicate.
        from app.parsers.supplier_validator import is_probable_address
        if is_probable_address(original):
            logger.debug("Address-as-supplier already covered by base rules — skipping rule.")
            return None

        if _RE_DATE_LIKE.match(original):
            return _make_rule(field, "date_like",
                              "Date-like value used as supplier name")

        if _RE_PHONE_IL.match(original):
            return _make_rule(field, "phone_number",
                              "Phone number used as supplier name")

        if _RE_TAX_ID.search(original):
            return _make_rule(field, "tax_id",
                              "Tax/company ID used as supplier name")

    elif field == "invoice_number":
        if _RE_DATE_LIKE.match(original):
            return _make_rule(field, "date_like",
                              "Date extracted as invoice number")

    # No known pattern matched — might be a one-off OCR artefact.
    return None


def _maybe_create_rule(correction: Correction) -> Optional[str]:
    """
    Attempt to infer and persist a new rule.  Returns reason string or None.
    """
    rule_template = _infer_rule(correction)

    if rule_template is None:
        # Check for repeated-literal errors that didn't match a named pattern.
        log   = _load_corrections_log()
        count = _count_occurrences(
            correction.field_name, correction.original_value, log
        )
        if count >= _LITERAL_RULE_THRESHOLD:
            rule_template = {
                "field":        correction.field_name,
                "action":       "reject",
                "pattern_type": "literal",
                "value":        correction.original_value,
                "reason":       f"Value corrected {count} time(s)",
            }
        else:
            logger.debug(
                "No generalizable rule for %r in field %r (count=%d/%d).",
                correction.original_value, correction.field_name,
                count, _LITERAL_RULE_THRESHOLD,
            )
            return None

    learned = _load_learned_rules()

    if _rule_exists(rule_template, learned["rules"]):
        logger.debug("Rule already exists: %s", rule_template.get("reason"))
        return None

    new_rule = {
        **rule_template,
        "id":         f"lr_{uuid.uuid4().hex[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    learned["rules"].append(new_rule)
    _save_learned_rules(learned)

    # Invalidate the supplier_validator cache so the new rule takes effect
    # immediately without restarting the application.
    from app.parsers.supplier_validator import invalidate_rules_cache
    invalidate_rules_cache()

    reason = new_rule.get("reason", "New rule learned")
    logger.info("Rule created [%s]: %s", new_rule["id"], reason)
    return reason


# ── Positive correction map ───────────────────────────────────────────────────

def _record_positive_correction(correction: Correction) -> None:
    """
    Store the correction in correction_map.json so the parser can apply it on
    the next run.

    For supplier_name specifically: a safety classification is applied before
    writing to the correction_map.  Corrections whose extracted value is a
    real entity name or a document-structure artifact are kept in the audit
    log only — they are NOT promoted to the global correction_map — to prevent
    cross-document contamination.

    All other fields (invoice_date, invoice_number, total) are stored
    unconditionally: their values are precise enough that collisions across
    unrelated documents are negligible.
    """
    if correction.field_name == "supplier_name":
        risk_reason = _supplier_correction_safety(correction.original_value)
        if risk_reason:
            logger.info(
                "Supplier correction kept as audit-log only "
                "(not promoted to correction_map): "
                "file=%r  extracted=%r → correct=%r  |  reason: %s",
                correction.file_name,
                correction.original_value,
                correction.corrected_value,
                risk_reason,
            )
            return  # Already appended to corrections_log by _append_correction()

    try:
        from app.services.correction_map_service import record_correction
        record_correction(
            field_name      = correction.field_name,
            extracted_value = correction.original_value,
            correct_value   = correction.corrected_value,
        )
    except Exception as exc:
        logger.warning("Could not record positive correction: %s", exc)


# ── Persistence helpers ───────────────────────────────────────────────────────

def _append_correction(correction: Correction) -> None:
    """Atomically append *correction* to corrections_log.json."""
    path = CORRECTIONS_LOG_JSON
    path.parent.mkdir(parents=True, exist_ok=True)

    log = _load_corrections_log()
    log.append(asdict(correction))

    _atomic_write(path, {"version": 1, "corrections": log})
    logger.debug("Correction recorded: field=%s file=%s",
                 correction.field_name, correction.file_name)


def _load_corrections_log() -> list[dict]:
    return _load_json(CORRECTIONS_LOG_JSON).get("corrections", [])


def _load_learned_rules() -> dict:
    data = _load_json(LEARNED_RULES_JSON)
    if "rules" not in data:
        data = {"version": 1, "rules": []}
    return data


def _save_learned_rules(data: dict) -> None:
    LEARNED_RULES_JSON.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(LEARNED_RULES_JSON, data)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning("Could not read %s: %s — returning empty.", path.name, exc)
        return {}


def _atomic_write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
        tmp.replace(path)
    except Exception as exc:
        logger.error("Failed to write %s: %s", path.name, exc)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


# ── Rule helpers ──────────────────────────────────────────────────────────────

def _make_rule(field: str, pattern_type: str, reason: str) -> dict:
    return {"field": field, "action": "reject",
            "pattern_type": pattern_type, "reason": reason}


def _rule_exists(candidate: dict, existing: list[dict]) -> bool:
    """True if a semantically equivalent rule is already in *existing*."""
    for r in existing:
        if r.get("field") != candidate.get("field"):
            continue
        if r.get("action") != candidate.get("action"):
            continue
        if r.get("pattern_type") != candidate.get("pattern_type"):
            continue
        # Literal rules must also match the exact value.
        if candidate.get("pattern_type") == "literal":
            if r.get("value") != candidate.get("value"):
                continue
        return True
    return False


def _count_occurrences(field_name: str, value: str, log: list[dict]) -> int:
    return sum(
        1 for c in log
        if c.get("field_name") == field_name
        and c.get("original_value") == value
    )
