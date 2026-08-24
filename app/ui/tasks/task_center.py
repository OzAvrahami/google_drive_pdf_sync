"""Non-modal Panda 2.0 Task Center flyout."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.application.task_manager import (
    CancellationNotSupported,
    CancellationRejected,
    TaskManager,
    TaskRecord,
    TaskState,
)
from app.ui.components.buttons import PandaIconButton
from app.ui.models.task_list_model import TaskListModel
from app.ui.tasks.presentation import (
    TASK_STATE_LABELS,
    TASK_STATE_SEMANTICS,
    completion_time,
    progress_text,
    task_detail,
)
from app.ui.theme.icons import IconName
from app.ui.theme.stylesheet import repolish
from app.ui.theme.tokens import ELEVATION
from app.ui.theme.typography import TypographyRole, apply_typography


class TaskCenterRow(QFrame):
    cancelRequested = Signal(str)

    def __init__(
        self,
        record: TaskRecord,
        *,
        queued_position: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.task_id = record.task_id
        self.setProperty("pandaComponent", "taskCenterRow")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._indicator = QLabel()
        self._indicator.setProperty("pandaComponent", "taskCenterIndicator")
        self._indicator.setFixedSize(9, 9)
        self._title = QLabel()
        apply_typography(self._title, TypographyRole.COMPACT_BODY)
        self._state_label = QLabel()
        self._state_label.setProperty("pandaComponent", "taskCenterState")
        self._state_label.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        apply_typography(self._state_label, TypographyRole.BADGE)
        top.addWidget(self._indicator)
        top.addWidget(self._title, 1)
        top.addWidget(self._state_label)
        root.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setProperty("pandaComponent", "taskCenterProgress")
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        root.addWidget(self.progress)

        bottom = QHBoxLayout()
        self._detail = QLabel()
        self._detail.setProperty("pandaComponent", "taskCenterDetail")
        self._detail.setWordWrap(False)
        apply_typography(self._detail, TypographyRole.HELPER)
        bottom.addWidget(self._detail, 1)
        self.cancel_button: QPushButton | None = None
        if record.cancellable and record.state in {TaskState.QUEUED, TaskState.RUNNING}:
            cancel = QPushButton("בטל")
            cancel.setProperty("pandaComponent", "taskCancel")
            cancel.setAccessibleName(f"ביטול המשימה {record.title}")
            cancel.setMinimumWidth(34)
            cancel.setEnabled(not record.cancel_requested)
            cancel.clicked.connect(lambda: self.cancelRequested.emit(record.task_id))
            self.cancel_button = cancel
            bottom.addWidget(cancel)
        root.addLayout(bottom)
        self.update_record(record, queued_position=queued_position)

    def update_record(self, record: TaskRecord, *, queued_position: int | None = None) -> None:
        self.record = record
        semantic = TASK_STATE_SEMANTICS[record.state]
        self.setProperty("taskState", semantic)
        self._indicator.setProperty("taskState", semantic)
        self._title.setText(record.title)
        self._title.setToolTip(record.title)
        if record.state is TaskState.QUEUED and queued_position is not None:
            state_text = f"בתור #{queued_position}"
        elif record.is_terminal:
            state_text = completion_time(record.completed_at)
        else:
            state_text = progress_text(record)
        self._state_label.setText(state_text)
        self._state_label.setProperty("taskState", semantic)
        detail_text = task_detail(record)
        self._detail.setText(detail_text)
        self._detail.setToolTip(detail_text)
        running = record.state is TaskState.RUNNING
        self.progress.setVisible(running)
        if running and record.progress_total is None:
            self.progress.setRange(0, 0)
        elif running:
            self.progress.setRange(0, record.progress_total or 1)
            self.progress.setValue(record.progress_current or 0)
        if self.cancel_button is not None:
            self.cancel_button.setEnabled(not record.cancel_requested)
        repolish(self._indicator)
        repolish(self._state_label)


class TaskCenter(QFrame):
    """A 360px non-modal flyout backed by the session TaskListModel."""

    opened = Signal()
    closed = Signal()
    cancellationFailed = Signal(str)

    def __init__(
        self,
        model: TaskListModel,
        manager: TaskManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model = model
        self._manager = manager
        self.rows_by_id: dict[str, TaskCenterRow] = {}
        self._groups: dict[str, str] = {}
        self.setProperty("pandaComponent", "taskCenter")
        self.setAccessibleName("מרכז משימות הרקע")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedWidth(360)
        self.setMaximumHeight(560)
        shadow = QGraphicsDropShadowEffect(self)
        token = ELEVATION.task_flyout
        shadow.setBlurRadius(token.blur_radius)
        shadow.setOffset(0, token.offset_y)
        shadow.setColor(QColor(token.color))
        self.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QFrame()
        header.setProperty("pandaComponent", "taskCenterHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 12, 10)
        title = QLabel("משימות רקע")
        apply_typography(title, TypographyRole.SECTION_TITLE)
        self._active_count = QLabel()
        self._active_count.setProperty("pandaComponent", "taskCenterCount")
        apply_typography(self._active_count, TypographyRole.BADGE)
        close = PandaIconButton(
            IconName.CLOSE,
            accessible_text="סגירת מרכז המשימות",
            size=30,
        )
        close.clicked.connect(self.close_panel)
        self.close_button = close
        header_layout.addWidget(title)
        header_layout.addWidget(self._active_count)
        header_layout.addStretch()
        header_layout.addWidget(close)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setProperty("pandaComponent", "taskCenterScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setProperty("pandaComponent", "taskCenterBody")
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(12, 10, 12, 12)
        self._body_layout.setSpacing(8)
        scroll.setWidget(body)
        root.addWidget(scroll)
        self._scroll = scroll

        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset):
            signal.connect(self.refresh)
        model.dataChanged.connect(self._on_data_changed)
        self.refresh()
        self.hide()

    def open_panel(self) -> None:
        self.refresh()
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.opened.emit()

    def close_panel(self) -> None:
        if self.isVisible():
            self.hide()
            self.closed.emit()

    def toggle(self) -> None:
        self.close_panel() if self.isVisible() else self.open_panel()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_panel()
            event.accept()
            return
        super().keyPressEvent(event)

    def refresh(self, *_args) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.rows_by_id.clear()
        self._groups.clear()
        records = self._model.records()
        active = [record for record in records if record.state is TaskState.RUNNING]
        queued = [record for record in records if record.state is TaskState.QUEUED]
        completed = sorted(
            (record for record in records if record.is_terminal),
            key=lambda record: record.completed_at or record.created_at,
            reverse=True,
        )
        pending = len(active) + len(queued)
        count_parts = []
        if active:
            count_parts.append(f"{len(active)} פעילות")
        if queued:
            count_parts.append(f"{len(queued)} בתור")
        self._active_count.setText(" · ".join(count_parts))
        self._active_count.setVisible(bool(pending))
        queue_positions = {record.task_id: index for index, record in enumerate(queued, 1)}
        self._add_section(
            "פעילות ובתור",
            active + queued,
            empty="אין משימות פעילות",
            queue_positions=queue_positions,
        )
        self._add_section("הושלמו לאחרונה", completed, empty="אין משימות שהושלמו במושב זה")
        self._body_layout.addStretch()

    def _add_section(
        self,
        title: str,
        records: list[TaskRecord],
        *,
        empty: str,
        queue_positions: dict[str, int] | None = None,
    ) -> None:
        label = QLabel(title)
        label.setProperty("pandaComponent", "taskCenterSection")
        apply_typography(label, TypographyRole.LABEL)
        self._body_layout.addWidget(label)
        if not records:
            empty_label = QLabel(empty)
            empty_label.setProperty("pandaRole", "muted")
            apply_typography(empty_label, TypographyRole.HELPER)
            self._body_layout.addWidget(empty_label)
            return
        for record in records:
            row = TaskCenterRow(
                record,
                queued_position=(queue_positions or {}).get(record.task_id),
            )
            row.cancelRequested.connect(self._cancel)
            self.rows_by_id[record.task_id] = row
            self._groups[record.task_id] = self._group_for(record)
            self._body_layout.addWidget(row)

    def _on_data_changed(self, top_left, bottom_right, _roles=None) -> None:
        changed = [
            self._model.record_at(row)
            for row in range(top_left.row(), bottom_right.row() + 1)
        ]
        if any(
            self._groups.get(record.task_id) != self._group_for(record)
            for record in changed
        ):
            self.refresh()
            return
        for record in changed:
            row = self.rows_by_id.get(record.task_id)
            if row is not None:
                row.update_record(record)

    @staticmethod
    def _group_for(record: TaskRecord) -> str:
        if record.state is TaskState.RUNNING:
            return "active"
        if record.state is TaskState.QUEUED:
            return "queued"
        return "completed"

    def _cancel(self, task_id: str) -> None:
        try:
            self._manager.cancel(task_id)
        except (CancellationNotSupported, CancellationRejected) as exc:
            self.cancellationFailed.emit(str(exc))
