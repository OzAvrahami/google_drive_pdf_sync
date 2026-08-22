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

CURRENT_STORE_VERSION = 2


class DocumentStoreLoadError(RuntimeError):
    """Raised when an existing document store cannot be loaded safely."""

    def __init__(self, path: Path, category: str, detail: str) -> None:
        self.path = path
        self.category = category
        super().__init__(
            f"Document store at '{path}' could not be loaded safely "
            f"({category}): {detail}"
        )


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
        try:
            self._path.stat()
        except FileNotFoundError:
            logger.info("No document store found at %s — starting fresh.", self._path)
            return
        except OSError as exc:
            error = DocumentStoreLoadError(
                self._path,
                "unreadable",
                f"the file could not be accessed ({type(exc).__name__})",
            )
            logger.error("%s", error)
            raise error from exc

        try:
            with self._path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except json.JSONDecodeError as exc:
            error = DocumentStoreLoadError(
                self._path,
                "malformed_json",
                f"malformed JSON at line {exc.lineno}, column {exc.colno}",
            )
            logger.error("%s", error)
            raise error from exc
        except (OSError, UnicodeError) as exc:
            error = DocumentStoreLoadError(
                self._path,
                "unreadable",
                f"the file could not be read ({type(exc).__name__})",
            )
            logger.error("%s", error)
            raise error from exc

        if not isinstance(raw, dict):
            raise DocumentStoreLoadError(
                self._path,
                "invalid_shape",
                "the top-level JSON value must be an object",
            )

        version = raw.get("version")
        if type(version) is not int:
            raise DocumentStoreLoadError(
                self._path,
                "invalid_version",
                f"schema version must be the integer {CURRENT_STORE_VERSION}",
            )
        if version != CURRENT_STORE_VERSION:
            raise DocumentStoreLoadError(
                self._path,
                "unsupported_version",
                f"schema version {version} is unsupported; "
                f"supported version is {CURRENT_STORE_VERSION}",
            )

        entries = raw.get("documents")
        if not isinstance(entries, list):
            raise DocumentStoreLoadError(
                self._path,
                "invalid_shape",
                "the 'documents' field must be an array",
            )

        loaded: dict[str, Document] = {}
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise DocumentStoreLoadError(
                    self._path,
                    "invalid_document",
                    f"document entry at index {index} must be an object",
                )
            try:
                doc = Document.from_dict(entry)
            except (KeyError, TypeError, ValueError) as exc:
                raise DocumentStoreLoadError(
                    self._path,
                    "invalid_document",
                    f"document entry at index {index} is invalid",
                ) from exc

            if not isinstance(doc.drive_file_id, str) or not doc.drive_file_id.strip():
                raise DocumentStoreLoadError(
                    self._path,
                    "invalid_document",
                    f"document entry at index {index} has no valid Drive file ID",
                )
            if doc.drive_file_id in loaded:
                raise DocumentStoreLoadError(
                    self._path,
                    "invalid_document",
                    f"document entry at index {index} duplicates a Drive file ID",
                )
            loaded[doc.drive_file_id] = doc

        self._docs = loaded
        logger.info("Loaded %d documents from store.", len(self._docs))

    def _save_locked(self) -> None:
        """Atomic write. Caller must hold self._lock."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        payload = {
            "version": CURRENT_STORE_VERSION,
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
