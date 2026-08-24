from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.application.task_manager import TaskAccess, TaskManager, TaskState, TaskType
from app.ui.models.task_list_model import TaskListModel, TaskRoles


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class ManualRunner:
    def start(self, reporter) -> None:
        self.reporter = reporter

    def request_cancel(self) -> bool:
        return False


def add_task(manager: TaskManager, runner=None) -> tuple[str, ManualRunner]:
    runner = runner or ManualRunner()
    task_id = manager.submit(
        task_type=TaskType.DEVELOPMENT,
        title="Model task",
        description="Description",
        access=TaskAccess.WRITE,
        runner=runner,
        cancellable=False,
    )
    return task_id, runner


def test_empty_model_and_incremental_insertion(qapp) -> None:
    manager = TaskManager()
    model = TaskListModel(manager)
    inserted = QSignalSpy(model.rowsInserted)
    task_id, _ = add_task(manager)

    assert model.rowCount() == 1
    assert inserted.count() == 1
    assert model.task_id_for_index(model.index(0, 0)) == task_id


def test_roles_expose_typed_task_data(qapp) -> None:
    manager = TaskManager()
    model = TaskListModel(manager)
    task_id, _ = add_task(manager)
    index = model.index_for_task_id(task_id)

    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "Model task"
    assert model.data(index, TaskRoles.TASK_ID) == task_id
    assert model.data(index, TaskRoles.TASK_TYPE) == TaskType.DEVELOPMENT.value
    assert model.data(index, TaskRoles.STATE) == TaskState.RUNNING.value
    assert model.data(index, TaskRoles.CANCELLABLE) is False
    assert model.data(index, TaskRoles.ACCESS) == TaskAccess.WRITE.value


def test_progress_uses_data_changed_without_model_reset(qapp) -> None:
    manager = TaskManager()
    model = TaskListModel(manager)
    task_id, runner = add_task(manager)
    changed = QSignalSpy(model.dataChanged)
    reset = QSignalSpy(model.modelReset)
    runner.reporter.progress(current=2, total=5, message="working", current_item="two.pdf")
    index = model.index_for_task_id(task_id)

    assert changed.count() == 1 and reset.count() == 0
    assert model.data(index, TaskRoles.PROGRESS_CURRENT) == 2
    assert model.data(index, TaskRoles.PROGRESS_TOTAL) == 5
    assert model.data(index, TaskRoles.PROGRESS_FRACTION) == pytest.approx(0.4)
    assert model.data(index, TaskRoles.CURRENT_ITEM) == "two.pdf"


def test_completion_roles_update_in_place(qapp) -> None:
    manager = TaskManager()
    model = TaskListModel(manager)
    task_id, runner = add_task(manager)
    runner.reporter.succeed("complete")
    index = model.index_for_task_id(task_id)

    assert model.rowCount() == 1
    assert model.data(index, TaskRoles.STATE) == TaskState.SUCCEEDED.value
    assert model.data(index, TaskRoles.RESULT_SUMMARY) == "complete"
    assert model.data(index, TaskRoles.COMPLETED_AT) is not None


def test_failure_roles_expose_concise_error(qapp) -> None:
    manager = TaskManager()
    model = TaskListModel(manager)
    task_id, runner = add_task(manager)
    runner.reporter.fail("short failure\nlonger detail")
    index = model.index_for_task_id(task_id)

    assert model.data(index, TaskRoles.STATE) == TaskState.FAILED.value
    assert model.data(index, TaskRoles.ERROR_SUMMARY) == "short failure"
    assert "longer detail" in model.data(index, TaskRoles.ERROR_DETAIL)


def test_bounded_history_removes_exact_row(qapp) -> None:
    manager = TaskManager(history_limit=1)
    model = TaskListModel(manager)
    first_id, first = add_task(manager)
    first.reporter.succeed("first")
    second_id, second = add_task(manager)
    removed = QSignalSpy(model.rowsRemoved)
    second.reporter.succeed("second")

    assert removed.count() == 1
    assert model.rowCount() == 1
    assert not model.index_for_task_id(first_id).isValid()
    assert model.index_for_task_id(second_id).isValid()

