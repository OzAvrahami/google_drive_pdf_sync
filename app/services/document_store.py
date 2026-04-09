"""
Local JSON document store with atomic writes.

Single source of truth for all document state.  The store is indexed by
drive_file_id in memory and serialised to a single JSON file on disk.

Atomic write pattern: write to .tmp, then rename — so a crash mid-write
never corrupts the live file.
"""
import json
import logging
import threading
from pathlib import Path
from typing import Optional

from app.config import DOCUMENTS_JSON
from app.models.document import Document

logger = logging.getLogger(__name__)


class DocumentStore:
    """Thread-safe, JSON-backed document store."""

    def __init__(self, path: Path = DOCUMENTS_JSON) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._docs: dict[str, Document] = {}   # keyed by drive_file_id
        self._load()

    # ── Read ───────────────────────────────────────────────────────────────────

    def all(self) -> list[Document]:
        with self._lock:
            return list(self._docs.values())

    def get_by_drive_id(self, drive_file_id: str) -> Optional[Document]:
        with self._lock:
            return self._docs.get(drive_file_id)

    def get_by_id(self, doc_id: str) -> Optional[Document]:
        with self._lock:
            for doc in self._docs.values():
                if doc.id == doc_id:
                    return doc
            return None

    def get_by_status(self, *statuses: str) -> list[Document]:
        with self._lock:
            return [d for d in self._docs.values() if d.status in statuses]

    def count_by_status(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for doc in self._docs.values():
                counts[doc.status] = counts.get(doc.status, 0) + 1
            return counts

    def total(self) -> int:
        with self._lock:
            return len(self._docs)

    # ── Write ──────────────────────────────────────────────────────────────────

    def upsert(self, doc: Document) -> None:
        """Insert or update a document and persist immediately."""
        with self._lock:
            doc.touch()
            self._docs[doc.drive_file_id] = doc
            self._save_locked()

    def upsert_many(self, docs: list[Document]) -> None:
        """Batch insert/update — single write to disk."""
        with self._lock:
            for doc in docs:
                doc.touch()
                self._docs[doc.drive_file_id] = doc
            self._save_locked()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            logger.info("No document store found at %s — starting fresh.", self._path)
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            for entry in raw.get("documents", []):
                try:
                    doc = Document.from_dict(entry)
                    self._docs[doc.drive_file_id] = doc
                except Exception as exc:
                    logger.warning("Skipping corrupt entry id=%s: %s", entry.get("id"), exc)
            logger.info("Loaded %d documents from store.", len(self._docs))
        except Exception as exc:
            logger.error("Failed to load document store: %s", exc)

    def _save_locked(self) -> None:
        """Atomic write. Caller must hold self._lock."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        payload = {
            "version": 2,
            "documents": [d.to_dict() for d in self._docs.values()],
        }
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
            tmp.replace(self._path)
        except Exception as exc:
            logger.error("Failed to save document store: %s", exc)
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise
