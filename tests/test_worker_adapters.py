from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from app.application.task_manager import TaskAccess, TaskManager, TaskState, TaskType
from app.ui.tasks.worker_adapters import adapt_existing_worker


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class FakeWorker(QObject):
    progress = Signal(str)
    step = Signal(int, int, str)
    doc_updated = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.starts = 0

    def start(self) -> None:
        self.starts += 1


def submit(manager: TaskManager, worker: FakeWorker, task_type=TaskType.DOCUMENT_PROCESSING):
    adapter = adapt_existing_worker(worker, task_type)
    task_id = manager.submit(
        task_type=task_type,
        title="Adapted worker",
        access=TaskAccess.WRITE,
        runner=adapter,
        cancellable=False,
    )
    return task_id, adapter


def test_adapter_starts_and_owns_worker(qapp) -> None:
    manager = TaskManager()
    worker = FakeWorker()
    task_id, adapter = submit(manager, worker)

    assert worker.starts == 1
    assert adapter.worker is worker
    assert manager.task(task_id).state is TaskState.RUNNING


def test_progress_and_step_signals_are_normalized(qapp) -> None:
    manager = TaskManager()
    worker = FakeWorker()
    task_id, _ = submit(manager, worker)
    worker.progress.emit("reading source")
    worker.step.emit(3, 8, "invoice.pdf")

    record = manager.task(task_id)
    assert record.message == "reading source"
    assert (record.progress_current, record.progress_total) == (3, 8)
    assert record.current_item == "invoice.pdf"


def test_result_is_structured_and_worker_reference_released(qapp) -> None:
    manager = TaskManager()
    worker = FakeWorker()
    task_id, adapter = submit(manager, worker)
    worker.finished.emit({"success": 5, "failed": 1})

    record = manager.task(task_id)
    assert record.state is TaskState.SUCCEEDED
    assert record.result.metadata == {"success": 5, "failed": 1}
    assert "5" in record.result.summary and "1" in record.result.summary
    assert adapter.worker is None


@pytest.mark.parametrize(
    ("task_type", "result", "expected"),
    (
        (TaskType.DRIVE_SCAN, {"new": 4, "updated": 2}, "4 חדשים, 2 עודכנו"),
        (TaskType.DOCUMENT_PROCESSING, {"success": 5, "failed": 1}, "5 הצליחו, 1 נכשלו"),
        (TaskType.BULK_PROCESSING, {"success": 3, "failed": 0}, "3 הצליחו, 0 נכשלו"),
        (TaskType.RETRY, {"retried": "one.pdf"}, "העיבוד מחדש הושלם"),
        (TaskType.EXCEL_EXPORT, {"exported": 12}, "12 רשומות"),
    ),
)
def test_all_existing_worker_result_shapes_receive_task_specific_summaries(
    qapp, task_type, result, expected
) -> None:
    manager = TaskManager()
    worker = FakeWorker()
    task_id, _ = submit(manager, worker, task_type)
    worker.finished.emit(result)
    assert expected in manager.task(task_id).result.summary


def test_error_is_bounded_for_ui_and_preserved_for_diagnostics(qapp) -> None:
    manager = TaskManager()
    worker = FakeWorker()
    task_id, _ = submit(manager, worker)
    message = "Short failure\n" + "diagnostic " * 400
    worker.error.emit(message)

    error = manager.task(task_id).error
    assert error.summary == "Short failure"
    assert len(error.detail) <= 2000
    assert error.diagnostic == message


def test_document_update_callback_is_forwarded_when_available(qapp) -> None:
    manager = TaskManager()
    worker = FakeWorker()
    updated = []
    adapter = adapt_existing_worker(
        worker,
        TaskType.DOCUMENT_PROCESSING,
        document_updated=updated.append,
    )
    manager.submit(
        task_type=TaskType.DOCUMENT_PROCESSING,
        title="Process",
        runner=adapter,
    )
    worker.doc_updated.emit("drive-123")
    assert updated == ["drive-123"]


def test_duplicate_completion_or_error_signal_is_ignored(qapp) -> None:
    manager = TaskManager()
    worker = FakeWorker()
    task_id, adapter = submit(manager, worker)
    worker.finished.emit({"success": 1})
    worker.error.emit("late error")
    worker.finished.emit({"success": 2})

    assert adapter.completed is True
    assert manager.task(task_id).state is TaskState.SUCCEEDED
    assert manager.task(task_id).result.metadata["success"] == 1


def test_completion_releases_next_serialized_write_worker(qapp) -> None:
    manager = TaskManager()
    first = FakeWorker()
    second = FakeWorker()
    first_id, _ = submit(manager, first)
    second_id, _ = submit(manager, second)

    assert first.starts == 1 and second.starts == 0
    first.finished.emit({"success": 1})
    assert manager.task(first_id).state is TaskState.SUCCEEDED
    assert manager.task(second_id).state is TaskState.RUNNING
    assert second.starts == 1


def test_existing_worker_adapter_never_claims_cancellation(qapp) -> None:
    manager = TaskManager()
    worker = FakeWorker()
    _, adapter = submit(manager, worker)
    assert adapter.request_cancel() is False
