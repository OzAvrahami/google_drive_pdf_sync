"""
Processing service.

For each document with status "new":
  1. Download the PDF from Google Drive.
  2. Extract text with pdfplumber + Hebrew normalisation.
  3. Save raw text to data/text/<drive_file_id>.txt.
  4. Parse invoice fields.
  5. Calculate confidence and set final status.
  6. Persist the updated document.
"""
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from googleapiclient.http import MediaIoBaseDownload

from app.config import DOWNLOADS_DIR, TEXT_DIR
from app.models.document import Document
from app.parsers.invoice_parser import (
    classify_document_type,
    parse_invoice_text,
    EXCLUDED_DOCUMENT_TYPES,
)
from app.parsers.pdf_parser import extract_text_from_pdf
from app.services.correction_map_service import load_correction_map
from app.services.document_store import DocumentStore
from app.services.duplicate_detection_service import detect_and_mark_duplicate
from app.utils.pdf_downloader import _download_file, resolve_local_path

logger = logging.getLogger(__name__)

Progress           = Callable[[str], None]
StepCallback       = Callable[[int, int, str], None]
DocUpdatedCallback = Callable[[str], None]

# Non-supplier fields, each worth 25 % of the total score.
_BASE_FIELDS = ("invoice_date", "invoice_number", "amount")


class ProcessingService:

    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    def process_new(
        self,
        progress: Optional[Progress] = None,
        drive_service=None,
        step_callback: Optional[StepCallback] = None,
        doc_updated_callback: Optional[DocUpdatedCallback] = None,
    ) -> dict:
        """
        Process all documents with status "new".

        drive_service — pre-authenticated Drive service object.  If None a
        new authentication is performed automatically.

        Returns a summary dict:
            {total, success, needs_review, failed}
        """
        docs = self._store.get_by_status("new")
        if not docs:
            _progress(progress, "No new documents to process.")
            return {"total": 0, "success": 0, "needs_review": 0, "failed": 0}

        if drive_service is None:
            _progress(progress, "Authenticating with Google Drive…")
            from app.clients.drive_client import get_drive_service
            drive_service, _ = get_drive_service()

        success = needs_review = failed = 0

        for i, doc in enumerate(docs, 1):
            _progress(progress, f"Processing {i}/{len(docs)}: {doc.file_name}")
            if step_callback:
                step_callback(i, len(docs), doc.file_name)
            try:
                self._process_one(doc, drive_service)
                if doc.status == "processed":
                    success += 1
                else:
                    needs_review += 1
            except Exception as exc:
                logger.exception("Failed processing %s: %s", doc.file_name, exc)
                doc.status = "failed"
                doc.error_message = str(exc)
                self._store.upsert(doc)
                failed += 1
            if doc_updated_callback:
                doc_updated_callback(doc.drive_file_id)

        summary = {
            "total": len(docs),
            "success": success,
            "needs_review": needs_review,
            "failed": failed,
        }
        logger.info("Processing complete: %s", summary)
        return summary

    def retry(self, doc: Document, drive_service=None) -> None:
        """Re-process a single document (any status except 'excluded'/'confirmed_irrelevant')."""
        if doc.status in ("excluded", "confirmed_irrelevant"):
            raise ValueError(
                f"Cannot retry permanently excluded document: {doc.file_name!r}. "
                "Remove the exclusion registry entry to re-enable this file."
            )
        if drive_service is None:
            from app.clients.drive_client import get_drive_service
            drive_service, _ = get_drive_service()
        doc.status = "new"
        doc.error_message = None
        self._process_one(doc, drive_service)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _process_one(self, doc: Document, service) -> None:
        logger.info("Processing started: %s", doc.file_name)

        # 1. Download PDF
        local_path = self._download(doc, service)
        doc.local_path = str(local_path)

        # 2. Extract text
        raw_text = extract_text_from_pdf(str(local_path))

        # 3. Save raw text
        text_path = TEXT_DIR / f"{doc.drive_file_id}.txt"
        TEXT_DIR.mkdir(parents=True, exist_ok=True)
        text_path.write_text(raw_text, encoding="utf-8")
        doc.raw_text_path = str(text_path)

        # 4. Classify document type — skip immediately if excluded.
        doc_type = classify_document_type(raw_text)
        if doc_type in EXCLUDED_DOCUMENT_TYPES:
            logger.info(
                "Skipping %s — excluded document type: %r",
                doc.file_name, doc_type,
            )
            doc.status        = "skipped"
            doc.error_message = f"מסמך לא רלוונטי: {doc_type}"
            doc.extracted_data = {"document_type": doc_type}
            self._store.upsert(doc)
            return

        # 5. Load correction map — applied as a post-processing layer in the parser.
        #    corrected_data is human-verified truth and is never overwritten here.
        correction_map = load_correction_map()
        logger.debug(
            "Correction map loaded for %s: %d field(s) with mappings.",
            doc.file_name,
            len(correction_map.get("fields", {})),
        )

        # 6. Parse invoice fields (with learned corrections applied automatically)
        logger.debug("Parsing invoice text for: %s", doc.file_name)
        parsed = parse_invoice_text(raw_text, correction_map=correction_map)
        doc.extracted_data = parsed or {}

        logger.info(
            "Parse result for %s: supplier=%r date=%r number=%r amount=%r",
            doc.file_name,
            (parsed or {}).get("business_name"),
            (parsed or {}).get("invoice_date"),
            (parsed or {}).get("invoice_number"),
            (parsed or {}).get("amount"),
        )

        if parsed:
            doc.supplier_name  = parsed.get("business_name")
            doc.invoice_date   = parsed.get("invoice_date")
            doc.invoice_number = parsed.get("invoice_number")
            raw_amount         = parsed.get("amount")
            doc.total = float(raw_amount) if raw_amount is not None else None

        # 7. Confidence & status
        doc.confidence = _confidence(parsed)

        # If the supplier was rejected (e.g. it was an address) and no valid
        # fallback was found, always flag the document for review regardless
        # of the numeric confidence score.
        supplier_val = (parsed or {}).get("supplier_validation", {})
        supplier_rejected_without_fallback = (
            not supplier_val.get("is_valid", True)
            and not supplier_val.get("fallback_used", False)
        )

        if supplier_rejected_without_fallback:
            doc.status = "needs_review"
        elif doc.confidence >= 0.75:
            doc.status = "processed"
        else:
            doc.status = "needs_review"

        # 8. Duplicate detection — runs after status assignment so the comparison
        #    pool excludes documents still queued as 'new' in the same batch.
        detect_and_mark_duplicate(doc, self._store)

        self._store.upsert(doc)

    def _download(self, doc: Document, service) -> Path:
        drive_record = {
            "id":          doc.drive_file_id,
            "name":        doc.file_name,
            "folder_path": doc.folder_path,
        }
        local_path = Path(resolve_local_path(str(DOWNLOADS_DIR), drive_record))

        if local_path.exists():
            logger.debug("Already downloaded: %s", local_path)
            return local_path

        local_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("Downloading %s → %s", doc.file_name, local_path)
        _download_file(service, doc.drive_file_id, str(local_path))
        return local_path


# ── Helpers ────────────────────────────────────────────────────────────────────

def _confidence(parsed: Optional[dict]) -> float:
    """
    Weighted confidence score (0.0–1.0).

    Weights:
      - invoice_date    : 25 %
      - invoice_number  : 25 %
      - amount          : 25 %
      - supplier score  : 25 %  (uses ValidationResult.score from supplier_validator)

    A supplier that was rejected as an address contributes near-zero to the
    supplier component, which lowers overall confidence and triggers
    needs_review status even when every other field was found.
    """
    if not parsed:
        return 0.0

    # Base components (0–0.75)
    base = sum(0.25 for f in _BASE_FIELDS if parsed.get(f))

    # Supplier component (0–0.25): uses the 0–100 validator score
    supplier_val   = parsed.get("supplier_validation", {})
    supplier_score = supplier_val.get("score", 0)          # 0–100 int
    # Treat a rejected-but-fallen-back supplier at face value (the fallback
    # has its own score already).  Treat rejected-with-no-fallback as 0.
    if not supplier_val.get("is_valid", True) and not supplier_val.get("fallback_used", False):
        supplier_score = 0
    supplier_component = (supplier_score / 100) * 0.25

    return round(base + supplier_component, 2)


def _progress(cb: Optional[Progress], msg: str) -> None:
    if cb:
        cb(msg)
