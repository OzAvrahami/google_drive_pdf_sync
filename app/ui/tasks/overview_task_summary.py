"""Small Overview projection of the shared Panda task model."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from app.application.task_manager import TaskState
from app.ui.models.task_list_model import TaskListModel
from app.ui.tasks.presentation import TASK_STATE_LABELS, TASK_STATE_SEMANTICS, task_detail
from app.ui.theme.stylesheet import repolish
from app.ui.theme.typography import TypographyRole, apply_typography


class OverviewTaskSummary(QFrame):
    taskCenterRequested = Signal()

    def __init__(self, model: TaskListModel | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = model
        self.setProperty("pandaComponent", "overviewTaskSummary")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        top = QHBoxLayout()
        self._indicator = QLabel()
        self._indicator.setProperty("pandaComponent", "overviewTaskIndicator")
        self._indicator.setFixedSize(8, 8)
        self._title = QLabel()
        apply_typography(self._title, TypographyRole.COMPACT_BODY)
        self._state_label = QLabel()
        self._state_label.setProperty("pandaRole", "muted")
        apply_typography(self._state_label, TypographyRole.BADGE)
        top.addWidget(self._indicator)
        top.addWidget(self._title, 1)
        top.addWidget(self._state_label)
        root.addLayout(top)
        self._progress = QProgressBar()
        self._progress.setProperty("pandaComponent", "overviewTaskProgress")
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        root.addWidget(self._progress)
        self._detail = QLabel()
        self._detail.setProperty("pandaRole", "muted")
        self._detail.setWordWrap(True)
        apply_typography(self._detail, TypographyRole.HELPER)
        root.addWidget(self._detail)
        self._open = QPushButton("מרכז המשימות")
        self._open.setProperty("pandaComponent", "taskLink")
        self._open.setAccessibleName("פתיחת מרכז משימות הרקע")
        self._open.clicked.connect(self.taskCenterRequested.emit)
        root.addWidget(self._open)

        if model is not None:
            for signal in (
                model.rowsInserted,
                model.rowsRemoved,
                model.dataChanged,
                model.modelReset,
            ):
                signal.connect(self.refresh)
        self.refresh()

    @property
    def model(self) -> TaskListModel | None:
        return self._model

    @property
    def displayed_task_id(self) -> str | None:
        return self._displayed_task_id

    def refresh(self, *_args) -> None:
        record = self._model.manager.primary_task() if self._model is not None else None
        self._displayed_task_id = record.task_id if record is not None else None
        if record is None:
            title, detail, state_label, semantic = (
                "אין משימות פעילות",
                "פעולות רקע חדשות יוצגו כאן בלי לחסום את העבודה.",
                "לא פעילות",
                "idle",
            )
        else:
            title = record.title
            detail = task_detail(record) or record.description
            state_label = TASK_STATE_LABELS[record.state]
            semantic = TASK_STATE_SEMANTICS[record.state]
        self._title.setText(title)
        self._detail.setText(detail)
        self._state_label.setText(state_label)
        self._indicator.setProperty("taskState", semantic)
        running = record is not None and record.state is TaskState.RUNNING
        self._progress.setVisible(running)
        if running and record.progress_total is None:
            self._progress.setRange(0, 0)
        elif running:
            self._progress.setRange(0, record.progress_total or 1)
            self._progress.setValue(record.progress_current or 0)
        repolish(self._indicator)

