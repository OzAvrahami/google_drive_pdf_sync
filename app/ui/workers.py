"""
QThread workers for long-running background tasks.

Each worker exposes three signals:
  progress(str)  — status message for the status bar
  finished(dict) — summary dict when the task completes successfully
  error(str)     — error message if the task raises an exception
"""
import logging

from PySide6.QtCore import QThread, Signal

from app.services.document_store import DocumentStore
from app.services.drive_sync_service import DriveSyncService
from app.services.processing_service import ProcessingService

logger = logging.getLogger(__name__)


class ScanWorker(QThread):
    """Scans Google Drive and registers new PDFs in the store."""

    progress = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, store: DocumentStore, folder_id: str = "") -> None:
        super().__init__()
        self._store     = store
        self._folder_id = folder_id or None

    def run(self) -> None:
        try:
            svc = DriveSyncService(self._store)
            summary = svc.scan(
                folder_id=self._folder_id,
                progress=self.progress.emit,
            )
            self.finished.emit(summary)
        except Exception as exc:
            logger.exception("ScanWorker error: %s", exc)
            self.error.emit(str(exc))


class ProcessWorker(QThread):
    """Downloads and parses all documents with status 'new'."""

    progress    = Signal(str)
    step        = Signal(int, int, str)   # current, total, filename
    doc_updated = Signal(str)             # drive_file_id — emitted after each doc
    finished    = Signal(dict)
    error       = Signal(str)

    def __init__(self, store: DocumentStore) -> None:
        super().__init__()
        self._store = store

    def run(self) -> None:
        try:
            svc = ProcessingService(self._store)
            summary = svc.process_new(
                progress=self.progress.emit,
                step_callback=self.step.emit,
                doc_updated_callback=self.doc_updated.emit,
            )
            self.finished.emit(summary)
        except Exception as exc:
            logger.exception("ProcessWorker error: %s", exc)
            self.error.emit(str(exc))


class RetryWorker(QThread):
    """Re-processes a single document regardless of its current status."""

    progress = Signal(str)
    step     = Signal(int, int, str)   # current, total, filename
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, store: DocumentStore, drive_file_id: str) -> None:
        super().__init__()
        self._store         = store
        self._drive_file_id = drive_file_id

    def run(self) -> None:
        try:
            doc = self._store.get_by_drive_id(self._drive_file_id)
            if doc is None:
                self.error.emit(f"מסמך לא נמצא: {self._drive_file_id}")
                return
            self.progress.emit(f"מעבד מחדש: {doc.file_name}…")
            self.step.emit(0, 1, doc.file_name)
            svc = ProcessingService(self._store)
            svc.retry(doc)
            self.step.emit(1, 1, doc.file_name)
            self.finished.emit({"retried": doc.file_name, "status": doc.status})
        except Exception as exc:
            logger.exception("RetryWorker error: %s", exc)
            self.error.emit(str(exc))


class BulkProcessWorker(QThread):
    """Re-processes a specific list of documents identified by drive_file_id."""

    progress = Signal(str)
    step     = Signal(int, int, str)   # current, total, filename
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, store: DocumentStore, drive_file_ids: list) -> None:
        super().__init__()
        self._store          = store
        self._drive_file_ids = list(drive_file_ids)

    def run(self) -> None:
        try:
            from app.clients.drive_client import get_drive_service
            self.progress.emit("מתחבר ל-Google Drive…")
            drive_service, _ = get_drive_service()

            svc   = ProcessingService(self._store)
            total = len(self._drive_file_ids)
            success = needs_review = failed = skipped = 0

            for i, drive_id in enumerate(self._drive_file_ids, 1):
                doc = self._store.get_by_drive_id(drive_id)
                if doc is None:
                    skipped += 1
                    continue
                self.progress.emit(f"מעבד {i}/{total}: {doc.file_name}")
                self.step.emit(i, total, doc.file_name)
                try:
                    svc.retry(doc, drive_service=drive_service)
                    if doc.status == "processed":
                        success += 1
                    elif doc.status == "skipped":
                        skipped += 1
                    else:
                        needs_review += 1
                except Exception as exc:
                    logger.exception(
                        "BulkProcessWorker error on %s: %s", doc.file_name, exc
                    )
                    doc.status = "failed"
                    doc.error_message = str(exc)
                    self._store.upsert(doc)
                    failed += 1

            self.finished.emit({
                "total":        total,
                "success":      success,
                "needs_review": needs_review,
                "failed":       failed,
                "skipped":      skipped,
            })
        except Exception as exc:
            logger.exception("BulkProcessWorker fatal error: %s", exc)
            self.error.emit(str(exc))


class ExportWorker(QThread):
    """Exports all approved documents to Excel."""

    progress = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, store: DocumentStore, output_path: str) -> None:
        super().__init__()
        self._store       = store
        self._output_path = output_path

    def run(self) -> None:
        try:
            from app.application.export_service import ExportService

            self.progress.emit("אוסף מסמכים מאושרים…")
            docs = self._store.get_by_status("approved")

            if not docs:
                self.finished.emit({"exported": 0, "message": "אין מסמכים מאושרים לייצוא."})
                return

            self.progress.emit(f"מייצא {len(docs)} מסמכים לאקסל…")
            result = ExportService(self._store, self._output_path).export_selected(
                [doc.drive_file_id for doc in docs]
            )

            self.finished.emit({
                "exported": result.exported_count,
                "written": len(result.written_ids),
                "already_present": len(result.already_present_ids),
                "ineligible": len(result.ineligible_ids),
                "missing": len(result.missing_ids),
                "partial": result.outcome.value == "partial",
                "status_persistence_error": result.status_persistence_error,
                "path": result.workbook_path,
            })
        except Exception as exc:
            logger.exception("ExportWorker error: %s", exc)
            self.error.emit(str(exc))
