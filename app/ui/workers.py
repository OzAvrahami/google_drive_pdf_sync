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

    progress = Signal(str)
    step     = Signal(int, int, str)   # current, total, filename
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, store: DocumentStore) -> None:
        super().__init__()
        self._store = store

    def run(self) -> None:
        try:
            svc = ProcessingService(self._store)
            summary = svc.process_new(
                progress=self.progress.emit,
                step_callback=self.step.emit,
            )
            self.finished.emit(summary)
        except Exception as exc:
            logger.exception("ProcessWorker error: %s", exc)
            self.error.emit(str(exc))


class RetryWorker(QThread):
    """Re-processes a single document regardless of its current status."""

    progress = Signal(str)
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
                self.error.emit(f"Document not found: {self._drive_file_id}")
                return
            self.progress.emit(f"Retrying: {doc.file_name}…")
            svc = ProcessingService(self._store)
            svc.retry(doc)
            self.finished.emit({"retried": doc.file_name, "status": doc.status})
        except Exception as exc:
            logger.exception("RetryWorker error: %s", exc)
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
            from app.writers.excel_writer import export_documents

            self.progress.emit("Collecting approved documents…")
            docs = self._store.get_by_status("approved")

            if not docs:
                self.finished.emit({"exported": 0, "message": "No approved documents to export."})
                return

            self.progress.emit(f"Exporting {len(docs)} document(s) to Excel…")
            count = export_documents(docs, self._output_path)

            # Mark exported documents
            for doc in docs:
                if doc.drive_file_id in {d.drive_file_id for d in docs}:
                    doc.status           = "exported"
                    doc.exported_to_excel = True
            self._store.upsert_many(docs)

            self.finished.emit({
                "exported": count,
                "path": self._output_path,
            })
        except Exception as exc:
            logger.exception("ExportWorker error: %s", exc)
            self.error.emit(str(exc))
