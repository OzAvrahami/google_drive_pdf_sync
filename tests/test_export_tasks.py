from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
import pytest

from app.application.task_manager import TaskAccess, TaskManager, TaskState, TaskType
from app.ui.tasks.export_tasks import ExportTaskController


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class FakeWorker(QObject):
    progress = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, service, ids) -> None:
        super().__init__()
        self.service = service
        self.ids = tuple(ids)
        self.starts = 0

    def start(self):
        self.starts += 1


class Factory:
    def __init__(self) -> None:
        self.workers = []

    def __call__(self, service, ids):
        worker = FakeWorker(service, ids)
        self.workers.append(worker)
        return worker


class HoldingRunner:
    def start(self, reporter):
        self.reporter = reporter

    def request_cancel(self):
        return False


def setup_controller(manager=None):
    manager = manager or TaskManager()
    factory = Factory()
    service = object()
    controller = ExportTaskController(
        service, manager, worker_factory=factory
    )
    return controller, manager, factory


def test_selected_export_is_a_serialized_write_task(qapp) -> None:
    controller, manager, factory = setup_controller()
    task_id = controller.submit_export(("one", "two"))

    record = manager.task(task_id)
    assert record.task_type is TaskType.EXCEL_EXPORT
    assert record.access is TaskAccess.WRITE
    assert record.state is TaskState.RUNNING
    assert factory.workers[0].ids == ("one", "two")


def test_export_queues_behind_an_existing_write(qapp) -> None:
    manager = TaskManager()
    blocker = HoldingRunner()
    blocking_id = manager.submit(
        task_type=TaskType.DRIVE_SCAN,
        title="scan",
        runner=blocker,
        access=TaskAccess.WRITE,
    )
    controller, _, factory = setup_controller(manager)

    export_id = controller.submit_export(("one",))

    assert manager.task(export_id).state is TaskState.QUEUED
    assert factory.workers[0].starts == 0
    blocker.reporter.succeed("done")
    assert manager.task(export_id).state is TaskState.RUNNING
    assert factory.workers[0].starts == 1


def test_duplicate_export_submission_is_rejected(qapp) -> None:
    controller, manager, factory = setup_controller()
    first = controller.submit_export(("one",))
    second = controller.submit_export(("two",))
    assert first is not None
    assert second is None
    assert len(factory.workers) == 1
    assert len(manager.tasks()) == 1


def test_progress_result_and_reconciliation_are_normalized(qapp) -> None:
    controller, manager, factory = setup_controller()
    completed = []
    reconciled = []
    controller.exportCompleted.connect(completed.append)
    controller.reconciliationRequested.connect(lambda: reconciled.append(True))
    task_id = controller.submit_export(("one",))
    worker = factory.workers[0]
    worker.progress.emit("כותב")
    worker.finished.emit(
        {
            "outcome": "succeeded",
            "exported": 1,
            "transitioned_ids": ("one",),
            "path": "temp.xlsx",
        }
    )

    task = manager.task(task_id)
    assert task.state is TaskState.SUCCEEDED
    assert task.message == "כותב"
    assert task.result.metadata["transitioned_ids"] == ("one",)
    assert completed[0]["exported"] == 1
    assert reconciled == [True]


def test_failure_stays_failed_and_does_not_request_success_refresh(qapp) -> None:
    controller, manager, factory = setup_controller()
    failures = []
    reconciled = []
    controller.exportFailed.connect(failures.append)
    controller.reconciliationRequested.connect(lambda: reconciled.append(True))
    task_id = controller.submit_export(("one",))
    factory.workers[0].error.emit("workbook is corrupt")

    assert manager.task(task_id).state is TaskState.FAILED
    assert failures == ["workbook is corrupt"]
    assert reconciled == []


def test_failure_releases_next_write_task(qapp) -> None:
    controller, manager, factory = setup_controller()
    export_id = controller.submit_export(("one",))
    next_runner = HoldingRunner()
    next_id = manager.submit(
        task_type=TaskType.DOCUMENT_PROCESSING,
        title="process",
        runner=next_runner,
        access=TaskAccess.WRITE,
    )
    assert manager.task(next_id).state is TaskState.QUEUED

    factory.workers[0].error.emit("failed")

    assert manager.task(export_id).state is TaskState.FAILED
    assert manager.task(next_id).state is TaskState.RUNNING
