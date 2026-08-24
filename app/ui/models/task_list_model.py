"""Incremental Qt presentation model for the Panda 2.0 session task list."""

from __future__ import annotations

from enum import IntEnum

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt

from app.application.task_manager import (
    TaskEvent,
    TaskEventType,
    TaskManager,
    TaskRecord,
)


class TaskRoles(IntEnum):
    TASK_ID = int(Qt.ItemDataRole.UserRole) + 1
    TITLE = TASK_ID + 1
    TASK_TYPE = TASK_ID + 2
    STATE = TASK_ID + 3
    PROGRESS_CURRENT = TASK_ID + 4
    PROGRESS_TOTAL = TASK_ID + 5
    PROGRESS_FRACTION = TASK_ID + 6
    MESSAGE = TASK_ID + 7
    CURRENT_ITEM = TASK_ID + 8
    CREATED_AT = TASK_ID + 9
    STARTED_AT = TASK_ID + 10
    COMPLETED_AT = TASK_ID + 11
    RESULT_SUMMARY = TASK_ID + 12
    ERROR_SUMMARY = TASK_ID + 13
    ERROR_DETAIL = TASK_ID + 14
    CANCELLABLE = TASK_ID + 15
    CANCEL_REQUESTED = TASK_ID + 16
    ACCESS = TASK_ID + 17


class TaskListModel(QAbstractListModel):
    """Expose manager snapshots while preserving stable task identity per row."""

    def __init__(self, manager: TaskManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._task_ids = [task.task_id for task in manager.tasks()]
        self._unsubscribe = manager.subscribe(self._on_task_event)

    @property
    def manager(self) -> TaskManager:
        return self._manager

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._task_ids)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._task_ids):
            return None
        record = self._manager.task(self._task_ids[index.row()])
        if role == Qt.ItemDataRole.DisplayRole:
            return record.title
        values = {
            TaskRoles.TASK_ID: record.task_id,
            TaskRoles.TITLE: record.title,
            TaskRoles.TASK_TYPE: record.task_type.value,
            TaskRoles.STATE: record.state.value,
            TaskRoles.PROGRESS_CURRENT: record.progress_current,
            TaskRoles.PROGRESS_TOTAL: record.progress_total,
            TaskRoles.PROGRESS_FRACTION: record.progress_fraction,
            TaskRoles.MESSAGE: record.message,
            TaskRoles.CURRENT_ITEM: record.current_item,
            TaskRoles.CREATED_AT: record.created_at,
            TaskRoles.STARTED_AT: record.started_at,
            TaskRoles.COMPLETED_AT: record.completed_at,
            TaskRoles.RESULT_SUMMARY: record.result.summary if record.result else "",
            TaskRoles.ERROR_SUMMARY: record.error.summary if record.error else "",
            TaskRoles.ERROR_DETAIL: record.error.detail if record.error else "",
            TaskRoles.CANCELLABLE: record.cancellable,
            TaskRoles.CANCEL_REQUESTED: record.cancel_requested,
            TaskRoles.ACCESS: record.access.value,
        }
        try:
            return values[TaskRoles(role)]
        except (KeyError, ValueError):
            return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            int(TaskRoles.TASK_ID): QByteArray(b"taskId"),
            int(TaskRoles.TITLE): QByteArray(b"title"),
            int(TaskRoles.TASK_TYPE): QByteArray(b"taskType"),
            int(TaskRoles.STATE): QByteArray(b"state"),
            int(TaskRoles.PROGRESS_CURRENT): QByteArray(b"progressCurrent"),
            int(TaskRoles.PROGRESS_TOTAL): QByteArray(b"progressTotal"),
            int(TaskRoles.PROGRESS_FRACTION): QByteArray(b"progressFraction"),
            int(TaskRoles.MESSAGE): QByteArray(b"message"),
            int(TaskRoles.CURRENT_ITEM): QByteArray(b"currentItem"),
            int(TaskRoles.CREATED_AT): QByteArray(b"createdAt"),
            int(TaskRoles.STARTED_AT): QByteArray(b"startedAt"),
            int(TaskRoles.COMPLETED_AT): QByteArray(b"completedAt"),
            int(TaskRoles.RESULT_SUMMARY): QByteArray(b"resultSummary"),
            int(TaskRoles.ERROR_SUMMARY): QByteArray(b"errorSummary"),
            int(TaskRoles.ERROR_DETAIL): QByteArray(b"errorDetail"),
            int(TaskRoles.CANCELLABLE): QByteArray(b"cancellable"),
            int(TaskRoles.CANCEL_REQUESTED): QByteArray(b"cancelRequested"),
            int(TaskRoles.ACCESS): QByteArray(b"access"),
        }

    def record_at(self, row: int) -> TaskRecord:
        if not 0 <= row < len(self._task_ids):
            raise IndexError(row)
        return self._manager.task(self._task_ids[row])

    def task_id_for_index(self, index: QModelIndex) -> str | None:
        if not index.isValid() or not 0 <= index.row() < len(self._task_ids):
            return None
        return self._task_ids[index.row()]

    def index_for_task_id(self, task_id: str) -> QModelIndex:
        try:
            row = self._task_ids.index(task_id)
        except ValueError:
            return QModelIndex()
        return self.index(row, 0)

    def records(self) -> tuple[TaskRecord, ...]:
        return tuple(self._manager.task(task_id) for task_id in self._task_ids)

    def _on_task_event(self, event: TaskEvent) -> None:
        if event.event_type is TaskEventType.ADDED:
            row = len(self._task_ids)
            self.beginInsertRows(QModelIndex(), row, row)
            self._task_ids.append(event.task_id)
            self.endInsertRows()
            return
        if event.event_type is TaskEventType.REMOVED:
            try:
                row = self._task_ids.index(event.task_id)
            except ValueError:
                return
            self.beginRemoveRows(QModelIndex(), row, row)
            self._task_ids.pop(row)
            self.endRemoveRows()
            return
        try:
            row = self._task_ids.index(event.task_id)
        except ValueError:
            return
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, list(self.roleNames()))

    def close(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

