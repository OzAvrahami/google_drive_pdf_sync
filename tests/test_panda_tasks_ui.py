from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.application.task_manager import TaskAccess, TaskManager, TaskState, TaskType
from app.ui.models.task_list_model import TaskListModel
from app.ui.routes import AppRoute
from app.ui.shell import PandaMainWindow
from app.ui.tasks.task_center import TaskCenter
from app.ui.tasks.task_dock import TaskDock


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class ManualRunner:
    def __init__(self, *, cancellable: bool = False) -> None:
        self.reporter = None
        self.starts = 0
        self.cancellable = cancellable

    def start(self, reporter) -> None:
        self.reporter = reporter
        self.starts += 1

    def request_cancel(self) -> bool:
        if not self.cancellable:
            return False
        self.reporter.cancelled("cancelled safely")
        return True


class ReadOnlySource:
    def __init__(self) -> None:
        self.reads = 0
        self.writes = 0

    def all(self) -> list:
        self.reads += 1
        return []


def submit(
    manager: TaskManager,
    *,
    title: str = "Demo task",
    access: TaskAccess = TaskAccess.WRITE,
    cancellable: bool = False,
) -> tuple[str, ManualRunner]:
    runner = ManualRunner(cancellable=cancellable)
    task_id = manager.submit(
        task_type=TaskType.DEVELOPMENT,
        title=title,
        access=access,
        runner=runner,
        cancellable=cancellable,
    )
    return task_id, runner


def task_ui() -> tuple[TaskManager, TaskListModel]:
    manager = TaskManager()
    return manager, TaskListModel(manager)


def test_task_dock_idle_state_and_accessibility(qapp) -> None:
    _, model = task_ui()
    dock = TaskDock(model)
    assert dock.state.task_id is None
    assert dock.state.title == "אין משימות פעילות"
    assert dock.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert dock.accessibleName()


def test_task_dock_running_determinate_progress(qapp) -> None:
    manager, model = task_ui()
    dock = TaskDock(model)
    task_id, runner = submit(manager, title="Processing")
    runner.reporter.progress(current=3, total=10, current_item="invoice.pdf")

    assert dock.state.task_id == task_id
    assert dock.state.semantic == "running"
    assert dock._progress.minimum() == 0 and dock._progress.maximum() == 10
    assert dock._progress.value() == 3
    assert dock._detail.toolTip() == "invoice.pdf"


def test_task_dock_indeterminate_progress(qapp) -> None:
    manager, model = task_ui()
    dock = TaskDock(model)
    _, runner = submit(manager)
    runner.reporter.progress(message="Scanning")
    assert dock.state.indeterminate is True
    assert dock._progress.minimum() == dock._progress.maximum() == 0


def test_task_dock_shows_multiple_pending_count(qapp) -> None:
    manager, model = task_ui()
    dock = TaskDock(model)
    submit(manager, title="Running")
    submit(manager, title="Queued")
    assert dock.state.active_count == 1
    assert dock.state.queued_count == 1
    assert dock._count.text() == "2"
    assert dock._count.isVisibleTo(dock)


@pytest.mark.parametrize(
    ("outcome", "semantic"),
    (("success", "succeeded"), ("failure", "failed")),
)
def test_task_dock_completion_semantics(qapp, outcome, semantic) -> None:
    manager, model = task_ui()
    dock = TaskDock(model)
    _, runner = submit(manager, title="Outcome")
    if outcome == "success":
        runner.reporter.succeed("Success summary")
    else:
        runner.reporter.fail("Failure summary")
    assert dock.state.semantic == semantic
    assert dock._progress.isHidden()


def test_task_center_lists_running_queued_and_recent(qapp) -> None:
    manager, model = task_ui()
    first_id, first = submit(manager, title="Running")
    queued_id, _ = submit(manager, title="Queued")
    read_id, read = submit(manager, title="Completed", access=TaskAccess.READ_ONLY)
    read.reporter.succeed("done")
    center = TaskCenter(model, manager)
    center.show()
    qapp.processEvents()

    assert set(center.rows_by_id) == {first_id, queued_id, read_id}
    assert center.rows_by_id[first_id].record.state is TaskState.RUNNING
    assert center.rows_by_id[queued_id].record.state is TaskState.QUEUED
    assert center.rows_by_id[queued_id]._state_label.text() == "בתור #1"
    assert center.rows_by_id[read_id].record.state is TaskState.SUCCEEDED
    assert center._active_count.text() == "1 פעילות · 1 בתור"
    first.reporter.succeed("finished")


def test_task_center_updates_progress_row_without_rebuilding_it(qapp) -> None:
    manager, model = task_ui()
    task_id, runner = submit(manager)
    center = TaskCenter(model, manager)
    original_row = center.rows_by_id[task_id]
    runner.reporter.progress(current=2, total=7, current_item="item.pdf")

    assert center.rows_by_id[task_id] is original_row
    assert original_row.progress.value() == 2
    assert original_row.record.current_item == "item.pdf"


def test_task_center_hides_cancel_for_non_cancellable_task(qapp) -> None:
    manager, model = task_ui()
    task_id, _ = submit(manager, cancellable=False)
    center = TaskCenter(model, manager)
    assert center.rows_by_id[task_id].cancel_button is None


def test_task_center_cancel_button_uses_cooperative_manager_cancel(qapp) -> None:
    manager, model = task_ui()
    task_id, _ = submit(manager, cancellable=True)
    center = TaskCenter(model, manager)
    button = center.rows_by_id[task_id].cancel_button
    assert button is not None
    button.click()
    assert manager.task(task_id).state is TaskState.CANCELLED


def test_task_center_is_non_modal_and_escape_closes(qapp) -> None:
    manager, model = task_ui()
    center = TaskCenter(model, manager)
    center.open_panel()
    assert center.isModal() is False
    assert center.isHidden() is False
    QTest.keyClick(center, Qt.Key.Key_Escape)
    assert center.isHidden() is True


def test_hiding_task_center_does_not_stop_active_task(qapp) -> None:
    manager, model = task_ui()
    task_id, _ = submit(manager)
    center = TaskCenter(model, manager)
    center.open_panel()
    center.close_panel()
    assert manager.task(task_id).state is TaskState.RUNNING


def test_shell_rail_and_overview_share_exact_task_model(qapp) -> None:
    source = ReadOnlySource()
    manager = TaskManager()
    shell = PandaMainWindow(source, task_manager=manager)
    task_id, runner = submit(manager, title="Shared task")
    runner.reporter.progress(current=1, total=4, message="working")

    assert shell.navigation.task_dock.state.task_id == task_id
    assert shell.overview.task_summary.model is shell.task_model
    assert shell.overview.task_summary.displayed_task_id == task_id
    assert shell.task_center._model is shell.task_model
    assert source.writes == 0
    runner.reporter.succeed("done")
    shell.close()


def test_route_navigation_remains_available_while_task_runs(qapp) -> None:
    manager = TaskManager()
    shell = PandaMainWindow(ReadOnlySource(), task_manager=manager)
    _, runner = submit(manager)
    shell.navigate(AppRoute.ATTENTION)
    assert shell.current_route is AppRoute.ATTENTION
    assert shell.navigation.button_for(AppRoute.ATTENTION).is_active is True
    runner.reporter.succeed("done")
    shell.close()


def test_shell_operational_actions_remain_disabled_with_phase_g_reason(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource())
    assert shell.scan_button.isEnabled() is False
    assert shell.process_button.isEnabled() is False
    assert "האמינות והתורים" in shell.scan_button.toolTip()
    shell.close()


def test_task_center_geometry_remains_bounded_at_minimum_shell_size(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource())
    shell.resize(1100, 680)
    shell.show()
    shell.task_center.open_panel()
    qapp.processEvents()
    assert shell.task_center.width() == 360
    assert shell.task_center.height() <= 560
    assert shell.task_center.geometry().right() < shell.navigation.geometry().left()
    shell.close()


def test_shell_refuses_force_close_while_task_is_running(qapp, monkeypatch) -> None:
    manager = TaskManager()
    shell = PandaMainWindow(ReadOnlySource(), task_manager=manager)
    _, runner = submit(manager, cancellable=False)
    warnings = []
    monkeypatch.setattr(
        "app.ui.shell.QMessageBox.warning",
        lambda *args: warnings.append(args),
    )
    event = QCloseEvent()
    shell.closeEvent(event)

    assert event.isAccepted() is False
    assert warnings
    assert manager.has_running_tasks is True
    runner.reporter.succeed("done")
    shell.close()
