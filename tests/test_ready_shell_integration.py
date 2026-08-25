from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal
from PySide6.QtWidgets import QApplication

from app.application.export_service import ExportService
from app.application.task_manager import TaskManager
from app.models.document import Document
from app.ui.models import ReadySegment
from app.ui.routes import AppRoute
from app.ui.shell import PandaMainWindow
from app.ui.views.ready import ReadyView


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    application = QApplication.instance() or QApplication([])
    existing_widgets = set(application.topLevelWidgets())
    yield application
    for widget in set(application.topLevelWidgets()) - existing_widgets:
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()


def doc(document_id: str, status: str) -> Document:
    return Document(
        drive_file_id=document_id,
        file_name=f"{document_id}.pdf",
        folder_path="synthetic",
        status=status,
        supplier_name="Supplier",
        invoice_number=f"INV-{document_id}",
        invoice_date="25/08/2026",
        total=100.0,
    )


class Repository:
    def __init__(self, *documents) -> None:
        self.documents = {item.drive_file_id: item for item in documents}

    def all(self):
        return list(self.documents.values())

    def get_by_drive_id(self, document_id):
        return self.documents.get(document_id)

    def get_by_status(self, *statuses):
        return [item for item in self.documents.values() if item.status in statuses]

    def upsert(self, item):
        self.documents[item.drive_file_id] = item

    def upsert_many(self, items):
        for item in items:
            self.documents[item.drive_file_id] = item


class FakeExportController(QObject):
    exportCompleted = Signal(dict)
    exportFailed = Signal(str)
    reconciliationRequested = Signal()
    availabilityChanged = Signal()

    def __init__(self):
        super().__init__()
        self.has_pending_export = False
        self.submissions = []
        self.closed = False

    def submit_export(self, ids):
        self.submissions.append(tuple(ids))
        self.has_pending_export = True
        self.availabilityChanged.emit()
        return "export-task"

    def close(self):
        self.closed = True


def shell(tmp_path, *documents):
    repository = Repository(*documents)
    manager = TaskManager()
    controller = FakeExportController()
    window = PandaMainWindow(
        repository,
        task_manager=manager,
        operational_enabled=False,
        export_service=ExportService(repository, tmp_path / "invoices.xlsx"),
        export_controller=controller,
    )
    return window, repository, controller


def test_real_ready_view_replaces_placeholder_for_repository_source(qapp, tmp_path) -> None:
    window, _, _ = shell(tmp_path, doc("processed", "processed"), doc("approved", "approved"))
    assert isinstance(window.view_for(AppRoute.READY), ReadyView)
    window.navigate(AppRoute.READY)
    assert window.ready.count_label.text() == "2"
    window.close()


def test_batch_approval_refreshes_ready_segments_and_shared_counts(qapp, tmp_path) -> None:
    window, repository, _ = shell(tmp_path, doc("processed", "processed"), doc("approved", "approved"))
    window.ready.restore_selected_document_ids(("processed",))
    window.ready.approve_selected()

    assert repository.documents["processed"].status == "approved"
    assert window._counts.ready == 2
    assert window._counts.ready_breakdown.ready_to_approve == 0
    assert window._counts.ready_breakdown.ready_to_export == 2
    window.ready.set_ready_segment(ReadySegment.READY_TO_EXPORT)
    assert set(window.ready.ordered_visible_document_ids) == {"processed", "approved"}
    window.close()


def test_selected_export_submission_disables_duplicate_action(qapp, tmp_path) -> None:
    window, _, controller = shell(tmp_path, doc("approved", "approved"))
    window.ready._confirm_export = lambda _ids: True
    window.ready.restore_selected_document_ids(("approved",))
    window.ready.request_selected_export()

    assert controller.submissions == [("approved",)]
    assert window.ready.export_button.isEnabled() is False
    window.close()


def test_export_completion_refreshes_ready_history_overview_and_rail(qapp, tmp_path) -> None:
    window, repository, controller = shell(tmp_path, doc("approved", "approved"))
    repository.documents["approved"].status = "exported"
    repository.documents["approved"].exported_to_excel = True
    controller.has_pending_export = False
    controller.exportCompleted.emit(
        {
            "outcome": "succeeded",
            "exported": 1,
            "transitioned_ids": ("approved",),
            "missing_ids": (),
            "ineligible_ids": (),
            "path": str(tmp_path / "invoices.xlsx"),
        }
    )

    assert window._counts.ready == 0
    assert window._counts.history == 1
    assert window.ready.proxy_model.rowCount() == 0
    assert window.navigation.button_for(AppRoute.READY).count == 0
    assert window.navigation.button_for(AppRoute.HISTORY).count == 1
    window.close()


def test_export_failure_keeps_last_known_ready_rows(qapp, tmp_path) -> None:
    window, _, controller = shell(tmp_path, doc("approved", "approved"))
    controller.exportFailed.emit("corrupt workbook")
    assert window.ready.proxy_model.rowCount() == 1
    assert "corrupt workbook" in window.ready.feedback_widget.accessibleName()
    window.close()
