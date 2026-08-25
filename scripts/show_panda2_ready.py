"""Offline visual harness for Panda 2.0 Ready approval/export workflows."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.application.export_service import ExportService
from app.application.task_manager import TaskAccess, TaskManager, TaskType
from app.models.document import Document
from app.services.document_store import DocumentStore
from app.ui.routes import AppRoute
from app.ui.shell import PandaMainWindow
from app.writers.excel_writer import export_documents


class StatusFailingRepository:
    """Harness-only repository that fails the JSON transition after Excel succeeds."""

    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    def all(self):
        return self._store.all()

    def get_by_drive_id(self, document_id):
        return self._store.get_by_drive_id(document_id)

    def get_by_status(self, *statuses):
        return self._store.get_by_status(*statuses)

    def upsert(self, item):
        return self._store.upsert(item)

    def upsert_many(self, items):
        if any(item.status == "exported" for item in items):
            raise OSError("synthetic status persistence failure")
        return self._store.upsert_many(items)


class TimedSyntheticWrite:
    """Hold the WRITE lane briefly so a selected export is visibly queued."""

    def start(self, reporter) -> None:
        reporter.progress(message="משימת כתיבה סינתטית פעילה")
        QTimer.singleShot(6000, lambda: reporter.succeed("המשימה הסינתטית הושלמה"))


def document(document_id: str, status: str, **overrides) -> Document:
    values = dict(
        drive_file_id=document_id,
        file_name=f"synthetic_{document_id}.pdf",
        folder_path="הדגמה / 2026",
        status=status,
        supplier_name="ספק הדגמה",
        invoice_number=f"DEMO-{document_id}",
        invoice_date="25/08/2026",
        total=1250.0,
        confidence=0.88,
    )
    values.update(overrides)
    return Document(**values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=(
            "mixed",
            "blocked",
            "already-present",
            "partial",
            "corrupt",
            "formula",
            "queued",
        ),
        default="mixed",
    )
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    temporary = tempfile.TemporaryDirectory(prefix="panda2-ready-")
    root = Path(temporary.name)
    store = DocumentStore(root / "documents.json")
    documents = [
        document("approve-1", "processed", supplier_name="שירותי משרד"),
        document("approve-2", "processed", supplier_name="Microsoft 365"),
        document("export-1", "approved", supplier_name="סלקום"),
        document(
            "export-2",
            "approved",
            supplier_name="שטראוס גרופ",
            was_manually_corrected=True,
        ),
    ]
    if args.scenario == "blocked":
        documents.append(
            document("blocked", "processed", invoice_date="not-a-date")
        )
    if args.scenario == "formula":
        documents[2].supplier_name = "=SUM(1,2)"
        documents[2].invoice_number = "@synthetic"
    store.upsert_many(documents)
    workbook = root / "invoices.xlsx"
    if args.scenario == "corrupt":
        workbook.write_bytes(b"synthetic corrupt workbook")
    elif args.scenario == "already-present":
        export_documents([documents[2]], str(workbook))

    repository = StatusFailingRepository(store) if args.scenario == "partial" else store
    manager = TaskManager()

    app = QApplication.instance() or QApplication(sys.argv)
    if args.scenario == "queued":
        manager.submit(
            task_type=TaskType.DEVELOPMENT,
            title="משימת כתיבה סינתטית",
            runner=TimedSyntheticWrite(),
            access=TaskAccess.WRITE,
        )
    window = PandaMainWindow(
        repository,
        task_manager=manager,
        operational_enabled=False,
        export_service=ExportService(repository, workbook),
        export_enabled=True,
    )
    window.navigate(AppRoute.READY)
    window.resize(1100, 680) if args.compact else window.resize(1440, 900)
    QTimer.singleShot(
        0,
        lambda: window.ready.restore_selected_document_ids(
            ("approve-1", "export-1")
            if args.scenario != "blocked"
            else ("approve-1", "blocked", "export-1")
        ),
    )
    window.show()
    exit_code = app.exec()
    temporary.cleanup()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
