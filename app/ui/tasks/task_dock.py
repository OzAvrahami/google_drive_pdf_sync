"""Compact task status control for the bottom of the Panda 2.0 work rail."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from app.application.task_manager import TaskRecord, TaskState
from app.ui.models.task_list_model import TaskListModel
from app.ui.tasks.presentation import TASK_STATE_SEMANTICS, progress_text, task_detail
from app.ui.theme.stylesheet import repolish
from app.ui.theme.tokens import SPACING
from app.ui.theme.typography import TypographyRole, apply_typography


@dataclass(frozen=True, slots=True)
class TaskDockViewState:
    task_id: str | None
    title: str
    detail: str
    semantic: str
    active_count: int
    queued_count: int
    indeterminate: bool = False


class TaskDock(QPushButton):
    """Show one primary task without turning the rail into a log viewer."""

    taskCenterRequested = Signal()

    def __init__(self, model: TaskListModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = model
        self._state = TaskDockViewState(
            None,
            "אין משימות פעילות",
            "פעולות רקע יופיעו כאן",
            "idle",
            0,
            0,
        )
        self.setProperty("pandaComponent", "taskDock")
        self.setProperty("taskState", "idle")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("מרכז משימות הרקע")
        self.setToolTip("פתיחת מרכז משימות הרקע")
        self.setFixedHeight(98)
        self.clicked.connect(self.taskCenterRequested.emit)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)
        heading = QHBoxLayout()
        heading.setSpacing(SPACING.adjacent)
        self._indicator = QLabel()
        self._indicator.setProperty("pandaComponent", "taskIndicator")
        self._indicator.setFixedSize(9, 9)
        self._title = QLabel()
        self._title.setProperty("pandaComponent", "taskTitle")
        apply_typography(self._title, TypographyRole.COMPACT_BODY)
        self._count = QLabel()
        self._count.setProperty("pandaComponent", "taskCount")
        apply_typography(self._count, TypographyRole.BADGE)
        heading.addWidget(self._indicator)
        heading.addWidget(self._title, 1)
        heading.addWidget(self._count)
        root.addLayout(heading)

        self._progress = QProgressBar()
        self._progress.setProperty("pandaComponent", "taskProgress")
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(5)
        root.addWidget(self._progress)

        self._detail = QLabel()
        self._detail.setProperty("pandaComponent", "taskDetail")
        self._detail.setWordWrap(False)
        apply_typography(self._detail, TypographyRole.HELPER)
        root.addWidget(self._detail)

        for signal in (
            model.rowsInserted,
            model.rowsRemoved,
            model.dataChanged,
            model.modelReset,
        ):
            signal.connect(self.refresh)
        self.refresh()

    @property
    def state(self) -> TaskDockViewState:
        return self._state

    def refresh(self, *_args) -> None:
        records = self._model.records()
        active = [record for record in records if record.state is TaskState.RUNNING]
        queued = [record for record in records if record.state is TaskState.QUEUED]
        terminal = [record for record in records if record.is_terminal]
        primary = self._model.manager.primary_task()

        if primary is None:
            state = TaskDockViewState(
                None,
                "אין משימות פעילות",
                "פעולות רקע יופיעו כאן",
                "idle",
                0,
                0,
            )
        else:
            detail = task_detail(primary) or progress_text(primary)
            state = TaskDockViewState(
                primary.task_id,
                primary.title,
                detail,
                TASK_STATE_SEMANTICS[primary.state],
                len(active),
                len(queued),
                primary.state is TaskState.RUNNING and primary.progress_total is None,
            )
        self._state = state
        self.setProperty("taskState", state.semantic)
        self._indicator.setProperty("taskState", state.semantic)
        self._title.setText(state.title)
        self._title.setToolTip(state.title)
        self._detail.setText(state.detail)
        self._detail.setToolTip(state.detail)
        pending_count = len(active) + len(queued)
        self._count.setText(str(pending_count) if pending_count > 1 else "")
        self._count.setVisible(pending_count > 1)

        running = primary if primary is not None and primary.state is TaskState.RUNNING else None
        self._progress.setVisible(running is not None)
        if running is not None and running.progress_total is None:
            self._progress.setRange(0, 0)
        elif running is not None:
            self._progress.setRange(0, running.progress_total or 1)
            self._progress.setValue(running.progress_current or 0)
        self.setAccessibleDescription(
            f"{state.title}. {state.detail}. "
            f"{len(active)} פעילות, {len(queued)} בתור"
        )
        repolish(self)
        repolish(self._indicator)

