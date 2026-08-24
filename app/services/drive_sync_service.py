"""
Drive sync service.

Scans Google Drive recursively and registers new/changed PDFs in the
document store.  Existing approved/exported documents are never reset.
"""
import logging
from typing import Callable, Optional

from app.clients.drive_client import get_drive_service, get_folder_pdf_hierarchy
from app.config import DOWNLOADS_DIR, GOOGLE_DRIVE_PARENT_FOLDER_ID
from app.models.document import Document
from app.services.document_store import DocumentStore
from app.services.exclusion_service import load_exclusion_ids
from app.utils.pdf_downloader import remove_cached_download, resolve_local_path

logger = logging.getLogger(__name__)

Progress = Callable[[str], None]


class DriveSyncService:

    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    def scan(
        self,
        folder_id: Optional[str] = None,
        progress: Optional[Progress] = None,
    ) -> dict:
        """
        Scan Google Drive for PDFs and register new/changed files.

        Returns a summary dict:
            {total_found, new, updated, skipped, excluded}

        Files present in the permanent exclusion registry are silently ignored
        so they are never re-downloaded or re-queued for processing.
        """
        fid = folder_id or GOOGLE_DRIVE_PARENT_FOLDER_ID
        if not fid:
            raise ValueError(
                "Google Drive folder ID is not configured.\n"
                "Set GOOGLE_DRIVE_PARENT_FOLDER_ID in your .env file."
            )

        _progress(progress, "Connecting to Google Drive…")
        service, _ = get_drive_service()

        _progress(progress, "Scanning folders recursively…")
        pdf_records = get_folder_pdf_hierarchy(service, fid)
        _progress(progress, f"Found {len(pdf_records)} PDF file(s). Registering…")

        # Load the exclusion set once so the per-record check is O(1).
        exclusion_ids = load_exclusion_ids()

        new_count = updated_count = skipped_count = excluded_count = 0
        to_upsert: list[Document] = []

        for rec in pdf_records:
            _progress(progress, f"Checking: {rec.get('folder_path', '') or 'root'} / {rec['name']}")
            # Never re-register a user-confirmed excluded file.
            if rec["id"] in exclusion_ids:
                excluded_count += 1
                logger.debug(
                    "Excluded (permanent): %s/%s",
                    rec.get("folder_path"), rec["name"],
                )
                continue

            existing = self._store.get_by_drive_id(rec["id"])

            if existing is None:
                doc = Document(
                    drive_file_id=rec["id"],
                    file_name=rec["name"],
                    folder_path=rec.get("folder_path", ""),
                )
                to_upsert.append(doc)
                new_count += 1
                logger.debug("New:     %s/%s", rec.get("folder_path"), rec["name"])

            elif existing.status in ("approved", "exported", "excluded", "confirmed_irrelevant"):
                # Never re-queue documents the accountant has already finalised.
                skipped_count += 1

            elif rec.get("modifiedTime", "") > existing.updated_at:
                # Invalidate every known cache destination before re-queuing.
                # A failed invalidation aborts the scan rather than allowing
                # stale local bytes to win during the next processing pass.
                _invalidate_changed_cache(existing, rec)
                existing.status = "new"
                existing.file_name = rec["name"]
                existing.folder_path = rec.get("folder_path", "")
                existing.local_path = ""
                existing.raw_text_path = ""
                to_upsert.append(existing)
                updated_count += 1
                logger.debug("Updated: %s/%s", rec.get("folder_path"), rec["name"])

            else:
                skipped_count += 1

        if to_upsert:
            self._store.upsert_many(to_upsert)

        summary = {
            "total_found": len(pdf_records),
            "new":         new_count,
            "updated":     updated_count,
            "skipped":     skipped_count,
            "excluded":    excluded_count,
        }
        logger.info("Drive scan complete: %s", summary)
        return summary


# ── Helpers ────────────────────────────────────────────────────────────────────

def _progress(cb: Optional[Progress], msg: str) -> None:
    if cb:
        cb(msg)


def _invalidate_changed_cache(existing: Document, remote_record: dict) -> None:
    root = str(DOWNLOADS_DIR)
    candidates = {
        resolve_local_path(
            root,
            {
                "name": existing.file_name,
                "folder_path": existing.folder_path,
            },
        ),
        resolve_local_path(root, remote_record),
    }
    if existing.local_path:
        candidates.add(existing.local_path)
    for candidate in candidates:
        remove_cached_download(root, candidate)
