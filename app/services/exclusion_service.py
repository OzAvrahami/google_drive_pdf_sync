"""
Permanent exclusion registry.

Records Drive files that the accountant has explicitly confirmed as irrelevant.
Once excluded:
  - The local PDF is deleted from disk.
  - The drive_file_id is entered into excluded_files.json.
  - Future Drive scans skip the file entirely.
  - Future processing is blocked.

This is intentionally separate from the automatic "skipped" status:
  - "skipped"  → system-classified, PDF kept, reversible, no registry entry.
  - "excluded" → user-confirmed, PDF deleted, permanent registry entry.

File format  (data/excluded_files.json)
---------------------------------------
{
  "version": 1,
  "excluded": {
    "<drive_file_id>": {
      "drive_file_id":           "...",
      "file_name":               "...",
      "folder_path":             "...",
      "detected_doc_type":       "טופס פתיחת ספק",
      "excluded_at":             "2026-04-15T10:00:00+00:00",
      "local_path_at_exclusion": "..."
    }
  }
}

Public API
----------
add_exclusion(doc)         -> None   — record + delete PDF; idempotent
confirm_irrelevant(doc)    -> None   — user-confirmed action; delegates to add_exclusion
is_excluded(drive_file_id) -> bool   — O(1) membership test
load_exclusion_ids()       -> set    — full set, for bulk scan filtering
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.document import Document

from app.config import EXCLUDED_FILES_JSON

logger = logging.getLogger(__name__)


# ── Public API ─────────────────────────────────────────────────────────────────

def confirm_irrelevant(doc: "Document") -> None:
    """
    Record a user-confirmed "irrelevant" decision for *doc*.

    Delegates to add_exclusion() which:
      - Writes a registry entry to excluded_files.json (idempotent).
      - Deletes the local PDF from disk.

    Does NOT mutate doc.status or doc.confirmed_irrelevant_at —
    the caller must set those fields and call store.upsert().
    """
    add_exclusion(doc)


def add_exclusion(doc: "Document") -> None:
    """
    Permanently exclude *doc*.

    1. Writes a registry entry to excluded_files.json (idempotent — safe to
       call again if the entry already exists, count will not duplicate).
    2. Deletes the local PDF from disk.

    Does NOT change doc.status — the caller is responsible for setting
    ``doc.status = "excluded"`` and persisting the document.
    """
    data = _load_registry()

    if doc.drive_file_id not in data["excluded"]:
        data["excluded"][doc.drive_file_id] = {
            "drive_file_id":           doc.drive_file_id,
            "file_name":               doc.file_name,
            "folder_path":             doc.folder_path,
            "detected_doc_type":       (doc.extracted_data or {}).get("document_type", ""),
            "excluded_at":             datetime.now(timezone.utc).isoformat(),
            "local_path_at_exclusion": doc.local_path,
        }
        _save_registry(data)
        logger.info(
            "Exclusion recorded: %s  id=%s", doc.file_name, doc.drive_file_id
        )
    else:
        logger.debug(
            "Exclusion already recorded for %s — skipping registry write.",
            doc.drive_file_id,
        )

    _delete_local_pdf(doc.local_path)


def is_excluded(drive_file_id: str) -> bool:
    """Return True if *drive_file_id* is in the exclusion registry."""
    data = _load_registry()
    return drive_file_id in data["excluded"]


def load_exclusion_ids() -> set:
    """
    Return the full set of excluded drive_file_ids.

    Intended for bulk filtering (e.g. Drive scan loop) so the JSON file is
    read only once rather than once per record.
    """
    data = _load_registry()
    ids  = set(data["excluded"].keys())
    logger.debug("Exclusion registry loaded: %d excluded file(s).", len(ids))
    return ids


# ── Internal helpers ───────────────────────────────────────────────────────────

def _load_registry() -> dict:
    """Load excluded_files.json; return empty structure on missing / corrupt."""
    if not EXCLUDED_FILES_JSON.exists():
        return {"version": 1, "excluded": {}}
    try:
        import json
        data = json.loads(EXCLUDED_FILES_JSON.read_text(encoding="utf-8"))
        if "excluded" not in data:
            return {"version": 1, "excluded": {}}
        return data
    except Exception as exc:
        logger.warning(
            "Could not read excluded_files.json: %s — returning empty registry.", exc
        )
        return {"version": 1, "excluded": {}}


def _save_registry(data: dict) -> None:
    """Atomic write of the exclusion registry."""
    import json
    EXCLUDED_FILES_JSON.parent.mkdir(parents=True, exist_ok=True)
    tmp = EXCLUDED_FILES_JSON.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(EXCLUDED_FILES_JSON)
    except Exception as exc:
        logger.error("Failed to write excluded_files.json: %s", exc)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _delete_local_pdf(local_path: str) -> None:
    """Delete the local PDF file; logs result; never raises."""
    if not local_path or not local_path.strip():
        logger.debug("No local path to delete — nothing to do.")
        return

    p = Path(local_path)
    if p.exists():
        try:
            p.unlink()
            logger.info("Deleted local PDF: %s", local_path)
        except Exception as exc:
            logger.warning(
                "Could not delete local PDF %s: %s", local_path, exc
            )
    else:
        logger.debug("Local PDF already absent, nothing to delete: %s", local_path)
