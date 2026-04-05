"""
State manager: tracks which Drive files have been processed.

State is persisted as JSON at STATE_FILE_PATH (data/state/sync_state.json).

Schema
------
{
  "version": 1,
  "files": {
    "<drive_file_id>": {
      "file_name":     "invoice.pdf",
      "folder_path":   "ינואר 2026/חשבוניות מס",
      "modified_time": "2026-01-31T10:00:00.000Z",   # from Drive API
      "processed_at":  "2026-04-05T12:30:00",
      "status":        "processed"                    # or "failed"
    }
  }
}

A file is considered "new" if its file_id is absent from state, OR if its
Drive modified_time differs from the recorded value (the file was changed).
"""

import json
import os
from datetime import datetime
from typing import Optional


class StateManager:
    VERSION = 1

    def __init__(self, state_path: str) -> None:
        self._path = state_path
        self._data: dict = {"version": self.VERSION, "files": {}}
        self._load()

    # ── Public API ─────────────────────────────────────────────────────────────

    def filter_new(self, drive_records: list[dict]) -> list[dict]:
        """
        Return the subset of drive_records that have not yet been processed
        (or whose Drive modified_time has changed since last processing).
        """
        new = []
        for rec in drive_records:
            fid = rec.get("id", "")
            if not fid:
                continue
            entry = self._data["files"].get(fid)
            if entry is None:
                new.append(rec)
            elif entry.get("modified_time") != rec.get("modifiedTime"):
                new.append(rec)
        return new

    def mark_processed(self, drive_record: dict, status: str = "processed",
                       error: Optional[str] = None) -> None:
        """Record that a file was processed (successfully or with an error)."""
        fid = drive_record["id"]
        self._data["files"][fid] = {
            "file_name":     drive_record.get("name", ""),
            "folder_path":   drive_record.get("folder_path", ""),
            "modified_time": drive_record.get("modifiedTime", ""),
            "processed_at":  datetime.now().isoformat(timespec="seconds"),
            "status":        status,
            **({"error": error} if error else {}),
        }

    def is_processed(self, file_id: str) -> bool:
        return file_id in self._data["files"]

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded.get("files"), dict):
                self._data = loaded
        except (json.JSONDecodeError, OSError):
            pass  # corrupt state file → start fresh
