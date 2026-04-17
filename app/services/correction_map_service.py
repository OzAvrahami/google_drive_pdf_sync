"""
Positive correction map.

Persists exact "extracted value → correct value" mappings per field so that
known parsing mistakes are corrected automatically on the next parse run —
no threshold, no pattern matching, no AI required.

Public API
----------
record_correction(field_name, extracted_value, correct_value) -> None
lookup_correction(field_name, extracted_value, correction_map)  -> str | None
load_correction_map()                                            -> dict

File format  (data/correction_map.json)
---------------------------------------
{
  "version": 1,
  "fields": {
    "supplier_name": {
      "פנדה הום בעמ": { "correct_value": "שירה לוסטיגר", "count": 2 }
    },
    "invoice_number": { ... },
    "invoice_date":   { ... },
    "total":          { ... }
  }
}

Keys are normalised (stripped + collapsed whitespace) before storage and lookup
so minor spacing artefacts don't create duplicate entries.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.config import CORRECTION_MAP_JSON

logger = logging.getLogger(__name__)

# ── Normalisation ──────────────────────────────────────────────────────────────

def _normalize(value: str) -> str:
    """Strip and collapse internal whitespace.  Preserves Hebrew / Unicode."""
    return " ".join(value.split())


# ── Public API ─────────────────────────────────────────────────────────────────

def load_correction_map() -> dict:
    """
    Load correction_map.json from disk.

    Returns an empty ``{"version": 1, "fields": {}}`` structure when the file
    is absent or unreadable — never raises.
    """
    if not CORRECTION_MAP_JSON.exists():
        logger.debug("Correction map not found — starting empty.")
        return {"version": 1, "fields": {}}

    try:
        with open(CORRECTION_MAP_JSON, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        if "fields" not in data:
            return {"version": 1, "fields": {}}

        total = sum(len(v) for v in data["fields"].values())
        logger.debug(
            "Correction map loaded: %d field(s), %d mapping(s).",
            len(data["fields"]), total,
        )
        return data

    except Exception as exc:
        logger.warning(
            "Could not read correction_map.json: %s — starting empty.", exc
        )
        return {"version": 1, "fields": {}}


def record_correction(
    field_name:      str,
    extracted_value: str,
    correct_value:   str,
) -> None:
    """
    Persist a positive correction mapping.

    On first occurrence: creates ``extracted_norm → correct_norm`` with count=1.
    On repeat: increments count.  No threshold — takes effect immediately.

    Skips silently when either value is blank or both values are identical
    after normalisation.
    """
    extracted_norm = _normalize(extracted_value)
    correct_norm   = _normalize(correct_value)

    if not extracted_norm or not correct_norm:
        logger.debug(
            "Skipping correction with empty value (field=%r).", field_name
        )
        return

    if extracted_norm == correct_norm:
        logger.debug(
            "Correction identical to extracted value — nothing to learn "
            "(field=%r, value=%r).", field_name, extracted_norm,
        )
        return

    data      = load_correction_map()
    field_map = data.setdefault("fields", {}).setdefault(field_name, {})

    if extracted_norm in field_map:
        field_map[extracted_norm]["count"] += 1
        count  = field_map[extracted_norm]["count"]
        action = "incremented"
    else:
        field_map[extracted_norm] = {"correct_value": correct_norm, "count": 1}
        count  = 1
        action = "recorded"

    _save_correction_map(data)
    logger.info(
        "Correction %s: field=%r  extracted=%r → correct=%r  count=%d",
        action,
        field_name,
        extracted_norm,
        field_map[extracted_norm]["correct_value"],
        count,
    )


def lookup_correction(
    field_name:      str,
    extracted_value: str,
    correction_map:  dict,
) -> Optional[str]:
    """
    Return the learned correct value for *extracted_value* in *field_name*,
    or ``None`` if no mapping exists.

    *correction_map* is the pre-loaded dict from :func:`load_correction_map`.
    Pass it in to avoid a disk read per field during batch parsing.
    """
    if not correction_map or not extracted_value:
        return None

    norm    = _normalize(str(extracted_value))
    mapping = correction_map.get("fields", {}).get(field_name, {}).get(norm)

    if mapping:
        return mapping["correct_value"]

    logger.debug(
        "No correction match: field=%r extracted=%r", field_name, norm
    )
    return None


# ── Persistence helper ─────────────────────────────────────────────────────────

def _save_correction_map(data: dict) -> None:
    CORRECTION_MAP_JSON.parent.mkdir(parents=True, exist_ok=True)
    tmp = CORRECTION_MAP_JSON.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
        tmp.replace(CORRECTION_MAP_JSON)
    except Exception as exc:
        logger.error("Failed to write correction_map.json: %s", exc)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
