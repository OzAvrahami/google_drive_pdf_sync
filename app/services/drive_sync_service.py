"""
Drive sync service.

Scans Google Drive recursively and registers new/changed PDFs in the
document store.  Existing approved/exported documents are never reset.
"""
import logging
from typing import Callable, Optional

from app.clients.drive_client import get_drive_service, get_folder_pdf_hierarchy
from app.config import GOOGLE_DRIVE_PARENT_FOLDER_ID
from app.models.document import Document
from app.services.document_store import DocumentStore

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
            {total_found, new, updated, skipped}
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

        new_count = updated_count = skipped_count = 0
        to_upsert: list[Document] = []

        for rec in pdf_records:
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

            elif existing.status in ("approved", "exported"):
                # Never re-queue documents the accountant has already approved.
                skipped_count += 1

            elif rec.get("modifiedTime", "") > existing.updated_at:
                # File was modified in Drive — re-queue for processing.
                existing.status = "new"
                existing.file_name = rec["name"]
                existing.folder_path = rec.get("folder_path", "")
                to_upsert.append(existing)
                updated_count += 1
                logger.debug("Updated: %s/%s", rec.get("folder_path"), rec["name"])

            else:
                skipped_count += 1

        if to_upsert:
            self._store.upsert_many(to_upsert)

        summary = {
            "total_found": len(pdf_records),
            "new": new_count,
            "updated": updated_count,
            "skipped": skipped_count,
        }
        logger.info("Drive scan complete: %s", summary)
        return summary


# ── Helpers ────────────────────────────────────────────────────────────────────

def _progress(cb: Optional[Progress], msg: str) -> None:
    if cb:
        cb(msg)
