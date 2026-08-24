from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from app.application.task_manager import TaskAccess, TaskManager, TaskState, TaskType
from app.ui.tasks.operational_tasks import OperationalTaskController


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


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

    def start(self) -> None:
        self.starts += 1


class WorkerFactory:
    def __init__(self) -> None:
        self.workers: list[FakeWorker] = []

    def __call__(self, store) -> FakeWorker:
        worker = FakeWorker(store)
        self.workers.append(worker)
        return worker


def controller():
    manager = TaskManager()
    scan = WorkerFactory()
    process = WorkerFactory()
    result = OperationalTaskController(
        object(),
        manager,
        scan_worker_factory=scan,
        process_worker_factory=process,
    )
    return result, manager, scan, process


def test_scan_submission_uses_existing_worker_adapter_and_write_access(qapp) -> None:
    control, manager, scan, _ = controller()

    task_id = control.submit_scan()

    record = manager.task(task_id)
    assert record.task_type is TaskType.DRIVE_SCAN
    assert record.access is TaskAccess.WRITE
    assert record.state is TaskState.RUNNING
    assert scan.workers[0].starts == 1


def test_process_progress_and_document_update_are_normalized(qapp) -> None:
    control, manager, _, process = controller()
    updated: list[str] = []
    control.documentUpdated.connect(updated.append)
    task_id = control.submit_process()
    worker = process.workers[0]

    worker.progress.emit("מתחיל")
    worker.step.emit(2, 7, "invoice.pdf")
    worker.doc_updated.emit("drive-2")

    record = manager.task(task_id)
    assert record.message == "מתחיל"
    assert (record.progress_current, record.progress_total) == (2, 7)
    assert record.current_item == "invoice.pdf"
    assert updated == ["drive-2"]


def test_scan_and_process_are_fifo_serialized(qapp) -> None:
    control, manager, scan, process = controller()
    scan_id = control.submit_scan()
    process_id = control.submit_process()

    assert manager.task(scan_id).state is TaskState.RUNNING
    assert manager.task(process_id).state is TaskState.QUEUED
    assert process.workers[0].starts == 0

    scan.workers[0].finished.emit({"new": 1, "updated": 0})

    assert manager.task(process_id).state is TaskState.RUNNING
    assert process.workers[0].starts == 1


@pytest.mark.parametrize("kind", (TaskType.DRIVE_SCAN, TaskType.DOCUMENT_PROCESSING))
def test_duplicate_submission_is_rejected_while_same_type_is_pending(qapp, kind) -> None:
    control, manager, scan, process = controller()
    first = control.submit_scan() if kind is TaskType.DRIVE_SCAN else control.submit_process()
    second = control.submit_scan() if kind is TaskType.DRIVE_SCAN else control.submit_process()

    assert first is not None
    assert second is None
    assert len(manager.tasks()) == 1
    assert len(scan.workers if kind is TaskType.DRIVE_SCAN else process.workers) == 1


def test_success_requests_reconciliation_but_failure_does_not(qapp) -> None:
    control, _, scan, process = controller()
    reconciliations: list[bool] = []
    control.reconciliationRequested.connect(lambda: reconciliations.append(True))

    control.submit_scan()
    scan.workers[0].finished.emit({"new": 2})
    control.submit_process()
    process.workers[0].error.emit("processing failed")

    assert reconciliations == [True]


def test_controller_close_unsubscribes_without_cancelling_work(qapp) -> None:
    control, manager, scan, _ = controller()
    control.submit_scan()
    control.close()
    scan.workers[0].finished.emit({"new": 1})
    assert manager.completed_tasks()[0].state is TaskState.SUCCEEDED

