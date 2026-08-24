from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from app.application.task_manager import TaskManager, TaskState, TaskType
from app.models.document import Document
from app.ui.routes import AppRoute
from app.ui.shell import PandaMainWindow
from app.ui.tasks.operational_tasks import OperationalTaskController


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def doc(document_id: str, status: str) -> Document:
    return Document(
        drive_file_id=document_id,
        id=f"record-{document_id}",
        file_name=f"{document_id}.pdf",
        folder_path="Drive / 2026",
        status=status,
    )


class OperationalSource:
    def __init__(self, documents=()) -> None:
        self.documents = {item.drive_file_id: item for item in documents}
        self.all_calls = 0
        self.write_calls = 0

    def all(self):
        self.all_calls += 1
        return list(self.documents.values())

    def get_by_drive_id(self, document_id):
        return self.documents.get(document_id)

    def get_by_status(self, *statuses):
        return [item for item in self.documents.values() if item.status in statuses]

    def upsert(self, document):
        self.write_calls += 1
        self.documents[document.drive_file_id] = document


class FakeWorker(QObject):
    progress = Signal(str)
    step = Signal(int, int, str)
    doc_updated = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, store) -> None:
        super().__init__()
        self.store = store
        self.starts = 0

    def start(self):
        self.starts += 1


class Factory:
    def __init__(self) -> None:
        self.workers = []

    def __call__(self, store):
        worker = FakeWorker(store)
        self.workers.append(worker)
        return worker


def shell_with_operations(documents=()):
    source = OperationalSource(documents)
    manager = TaskManager()
    scan = Factory()
    process = Factory()
    controller = OperationalTaskController(
        source,
        manager,
        scan_worker_factory=scan,
        process_worker_factory=process,
    )
    shell = PandaMainWindow(source, operational_controller=controller)
    return shell, source, manager, scan, process


def test_operational_shell_does_no_automatic_work_on_startup(qapp) -> None:
    shell, source, manager, scan, process = shell_with_operations([doc("new", "new")])

    assert source.all_calls == 1
    assert source.write_calls == 0
    assert manager.tasks() == ()
    assert scan.workers == [] and process.workers == []
    assert shell.scan_button.isEnabled()
    assert shell.process_button.isEnabled()


def test_scan_header_action_submits_once_and_success_refreshes_all_views(qapp) -> None:
    shell, source, manager, scan, _ = shell_with_operations()

    shell.scan_button.click()
    shell.scan_button.click()
    assert shell.navigation.task_dock.state.title == "סריקת Drive"
    source.documents["new"] = doc("new", "new")
    scan.workers[0].finished.emit({"new": 1, "updated": 0})

    assert len(manager.tasks()) == 1
    assert manager.tasks()[0].task_type is TaskType.DRIVE_SCAN
    assert manager.tasks()[0].state is TaskState.SUCCEEDED
    assert source.all_calls == 2
    assert shell.inbox.proxy_model.rowCount() == 1
    assert shell.navigation.button_for(AppRoute.INBOX).count == 1
    assert shell.overview.snapshot.counts.inbox == 1


def test_scan_failure_keeps_last_known_queue_and_does_not_fake_refresh(qapp) -> None:
    shell, source, manager, scan, _ = shell_with_operations([doc("existing", "new")])
    initial_calls = source.all_calls

    shell.scan_button.click()
    scan.workers[0].error.emit("Drive unavailable")

    assert manager.completed_tasks()[0].state is TaskState.FAILED
    assert source.all_calls == initial_calls
    assert shell.inbox.proxy_model.rowCount() == 1


def test_process_document_update_moves_row_by_stable_id(qapp) -> None:
    moving = doc("moving", "new")
    shell, source, manager, _, process = shell_with_operations([moving])

    shell.process_button.click()
    moving.status = "needs_review"
    process.workers[0].doc_updated.emit("moving")

    assert shell.inbox.proxy_model.rowCount() == 0
    assert shell.attention.proxy_model.rowCount() == 1
    assert shell.navigation.button_for(AppRoute.INBOX).count == 0
    assert shell.navigation.button_for(AppRoute.ATTENTION).count == 1
    assert manager.active_tasks()[0].task_type is TaskType.DOCUMENT_PROCESSING


def test_process_completion_performs_final_reconciliation(qapp) -> None:
    shell, source, _, _, process = shell_with_operations([doc("one", "new")])
    initial_calls = source.all_calls
    shell.process_button.click()
    source.documents["ready"] = doc("ready", "processed")

    process.workers[0].finished.emit({"success": 1, "failed": 0})

    assert source.all_calls == initial_calls + 1
    assert shell.navigation.button_for(AppRoute.READY).count == 1
    assert shell.overview.cards["ready_to_approve"].count == 1


def test_process_failure_retains_selection_and_last_known_rows(qapp) -> None:
    shell, source, manager, _, process = shell_with_operations(
        [doc("one", "new"), doc("two", "new")]
    )
    shell.navigate(AppRoute.INBOX)
    shell.inbox.restore_selected_document_ids(("two",))
    assert shell.inbox.selected_document_ids == ("two",)
    initial_calls = source.all_calls

    shell.process_button.click()
    process.workers[0].error.emit("processing unavailable")

    assert manager.completed_tasks()[0].state is TaskState.FAILED
    assert source.all_calls == initial_calls
    assert shell.inbox.proxy_model.rowCount() == 2
    assert shell.inbox.selected_document_ids == ("two",)


def test_scan_and_process_buttons_queue_distinct_serialized_writes(qapp) -> None:
    shell, _, manager, scan, process = shell_with_operations()
    shell.scan_button.click()
    shell.process_button.click()

    records = manager.tasks()
    assert [record.state for record in records] == [TaskState.RUNNING, TaskState.QUEUED]
    assert scan.workers[0].starts == 1
    assert process.workers[0].starts == 0

    scan.workers[0].finished.emit({"new": 0})
    assert process.workers[0].starts == 1


def test_queue_actions_use_same_operational_controller(qapp) -> None:
    shell, _, manager, scan, process = shell_with_operations()
    shell.inbox.empty_state.action_button.click()
    shell.inbox.process_button.click()

    assert [task.task_type for task in manager.tasks()] == [
        TaskType.DRIVE_SCAN,
        TaskType.DOCUMENT_PROCESSING,
    ]
    assert scan.workers[0].starts == 1
    assert process.workers[0].starts == 0


def test_navigation_remains_available_while_real_task_adapter_runs(qapp) -> None:
    shell, _, _, _, process = shell_with_operations()
    shell.process_button.click()

    shell.navigation.button_for(AppRoute.ATTENTION).click()

    assert shell.current_route is AppRoute.ATTENTION
    assert process.workers[0].starts == 1
