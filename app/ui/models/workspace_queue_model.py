"""Stable-ID navigation state for the Panda 2.0 Workspace."""

from __future__ import annotations

from collections.abc import Iterable
from enum import IntEnum

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, Qt, Signal


class WorkspaceQueueRoles(IntEnum):
    DOCUMENT_ID = int(Qt.ItemDataRole.UserRole) + 1
    IS_CURRENT = DOCUMENT_ID + 1


class WorkspaceQueueModel(QAbstractListModel):
    currentChanged = Signal(object, int, int)

    def __init__(self, document_ids: Iterable[str] = (), parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._document_ids: list[str] = []
        self._current_id: str | None = None
        self.set_document_ids(document_ids, preserve_current=False)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._document_ids)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._document_ids)):
            return None
        document_id = self._document_ids[index.row()]
        if role in (int(Qt.ItemDataRole.DisplayRole), int(WorkspaceQueueRoles.DOCUMENT_ID)):
            return document_id
        if role == int(WorkspaceQueueRoles.IS_CURRENT):
            return document_id == self._current_id
        return None

    def roleNames(self) -> dict[int, bytes]:
        names = dict(super().roleNames())
        names[int(WorkspaceQueueRoles.DOCUMENT_ID)] = b"document_id"
        names[int(WorkspaceQueueRoles.IS_CURRENT)] = b"is_current"
        return names

    @property
    def document_ids(self) -> tuple[str, ...]:
        return tuple(self._document_ids)

    @property
    def current_document_id(self) -> str | None:
        return self._current_id

    @property
    def current_index(self) -> int:
        if self._current_id is None:
            return -1
        try:
            return self._document_ids.index(self._current_id)
        except ValueError:
            return -1

    @property
    def position(self) -> int:
        index = self.current_index
        return index + 1 if index >= 0 else 0

    @property
    def total(self) -> int:
        return len(self._document_ids)

    @property
    def can_go_previous(self) -> bool:
        return self.current_index > 0

    @property
    def can_go_next(self) -> bool:
        index = self.current_index
        return bool(self._document_ids) if index < 0 else index < len(self._document_ids) - 1

    def set_document_ids(self, document_ids: Iterable[str], preserve_current: bool = True) -> None:
        ids = list(dict.fromkeys(str(document_id) for document_id in document_ids))
        old_id = self._current_id
        old_index = self.current_index
        self.beginResetModel()
        self._document_ids = ids
        if preserve_current and old_id in ids:
            self._current_id = old_id
        else:
            self._current_id = ids[0] if ids else None
        self.endResetModel()
        if self._current_id != old_id or self.current_index != old_index:
            self._emit_current()

    def refresh(
        self,
        document_ids: Iterable[str],
        *,
        keep_current_if_missing: bool = False,
    ) -> None:
        ids = list(dict.fromkeys(str(document_id) for document_id in document_ids))
        old_id = self._current_id
        self.beginResetModel()
        self._document_ids = ids
        if old_id in ids or (keep_current_if_missing and old_id is not None):
            self._current_id = old_id
        else:
            self._current_id = ids[0] if ids else None
        self.endResetModel()
        self._emit_current()

    def start_session(self, document_ids: Iterable[str], current_document_id: str) -> None:
        """Atomically establish one visible queue and its requested stable ID."""
        ids = list(dict.fromkeys(str(document_id) for document_id in document_ids))
        if current_document_id not in ids:
            raise ValueError("Current Workspace document must belong to the visible queue")
        self.beginResetModel()
        self._document_ids = ids
        self._current_id = current_document_id
        self.endResetModel()
        self._emit_current()

    def set_current_by_id(self, document_id: str) -> bool:
        if document_id not in self._document_ids:
            return False
        if document_id == self._current_id:
            return True
        old_index = self.current_index
        self._current_id = document_id
        new_index = self.current_index
        if old_index >= 0:
            self.dataChanged.emit(
                self.index(old_index, 0),
                self.index(old_index, 0),
                [int(WorkspaceQueueRoles.IS_CURRENT)],
            )
        self.dataChanged.emit(
            self.index(new_index, 0),
            self.index(new_index, 0),
            [int(WorkspaceQueueRoles.IS_CURRENT)],
        )
        self._emit_current()
        return True

    def previous(self) -> str | None:
        if not self.can_go_previous:
            return self._current_id
        document_id = self._document_ids[self.current_index - 1]
        self.set_current_by_id(document_id)
        return document_id

    def next(self) -> str | None:
        if not self.can_go_next:
            return self._current_id
        document_id = (
            self._document_ids[0]
            if self.current_index < 0
            else self._document_ids[self.current_index + 1]
        )
        self.set_current_by_id(document_id)
        return document_id

    def remove_document_id(self, document_id: str) -> bool:
        try:
            row = self._document_ids.index(document_id)
        except ValueError:
            return False
        old_id = self._current_id
        old_index = self.current_index
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._document_ids[row]
        self.endRemoveRows()
        if document_id == old_id:
            if self._document_ids:
                self._current_id = self._document_ids[min(row, len(self._document_ids) - 1)]
            else:
                self._current_id = None
        if self._current_id != old_id or self.current_index != old_index:
            self._emit_current()
        return True

    def _emit_current(self) -> None:
        self.currentChanged.emit(self._current_id, self.current_index, self.total)
