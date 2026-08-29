"""Compact SHA-backed corpus navigation list."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from app.ui.theme.icons import IconName, IconTone, icon_for
from app.ui.theme.tokens import SPACING
from app.ui.theme.typography import TypographyRole, apply_typography


_SHA_ROLE = Qt.ItemDataRole.UserRole


class CorpusList(QFrame):
    documentRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "benchmarkCorpusList")
        self.setMinimumWidth(190)
        self.setMaximumWidth(280)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(SPACING.adjacent)

        self.heading = QLabel("מסמכים")
        apply_typography(self.heading, TypographyRole.SECTION_TITLE)
        self.count_label = QLabel("0 / 0")
        self.count_label.setProperty("pandaRole", "muted")
        apply_typography(self.count_label, TypographyRole.HELPER)
        root.addWidget(self.heading)
        root.addWidget(self.count_label)

        self.list = QListWidget()
        self.list.setProperty("pandaComponent", "benchmarkCorpusListView")
        self.list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.list.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.list.setWordWrap(False)
        self.list.currentItemChanged.connect(self._current_changed)
        root.addWidget(self.list, 1)

    @property
    def current_sha(self) -> str | None:
        item = self.list.currentItem()
        return str(item.data(_SHA_ROLE)) if item is not None else None

    @property
    def ordered_shas(self) -> tuple[str, ...]:
        return tuple(str(self.list.item(index).data(_SHA_ROLE)) for index in range(self.list.count()))

    def set_records(
        self,
        records: Sequence[Mapping[str, object]],
        *,
        total: int,
        preferred_sha: str | None = None,
        preferred_index: int | None = None,
    ) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        selected_row = -1
        for index, record in enumerate(records):
            item = QListWidgetItem(self._item_text(record))
            sha = str(record.get("sha256") or "")
            item.setData(_SHA_ROLE, sha)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            item.setToolTip(str(record.get("relative_path") or ""))
            item.setData(Qt.ItemDataRole.AccessibleTextRole, self._accessible_text(record))
            item.setIcon(self._icon(record))
            item.setSizeHint(QSize(0, 54))
            self.list.addItem(item)
            if sha == preferred_sha:
                selected_row = index
        if selected_row < 0 and records:
            selected_row = min(preferred_index or 0, len(records) - 1)
        if selected_row >= 0:
            self.list.setCurrentRow(selected_row)
        self.list.blockSignals(False)
        self.count_label.setText(f"{len(records)} / {total}")
        if selected_row >= 0:
            self.documentRequested.emit(str(self.list.item(selected_row).data(_SHA_ROLE)))

    def select_sha(self, sha256: str) -> bool:
        for index in range(self.list.count()):
            item = self.list.item(index)
            if str(item.data(_SHA_ROLE)) == sha256:
                self.list.setCurrentItem(item)
                return True
        return False

    def current_index(self) -> int:
        return self.list.currentRow()

    def _current_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is not None:
            self.documentRequested.emit(str(current.data(_SHA_ROLE)))

    @staticmethod
    def _item_text(record: Mapping[str, object]) -> str:
        source = record.get("source_detection") or {}
        source_name = source.get("source_system", "Unknown") if isinstance(source, Mapping) else "Unknown"
        confidence = int(float(record.get("confidence") or 0) * 100)
        state = "נבדק" if record.get("reviewed") is True else "ממתין לבדיקה"
        return (
            f"{record.get('filename') or '<unnamed>'}\n"
            f"{source_name} · {record.get('status') or 'unanalyzed'} · {confidence}% · {state}"
        )

    @staticmethod
    def _accessible_text(record: Mapping[str, object]) -> str:
        if record.get("fully_correct") is False:
            state = "נבדק עם אי התאמה"
        elif record.get("fully_correct") is True:
            state = "נבדק ונמצא תקין"
        else:
            state = "טרם נבדק"
        return f"{record.get('filename') or ''}, {state}"

    @staticmethod
    def _icon(record: Mapping[str, object]):
        if record.get("fully_correct") is False:
            return icon_for(IconName.ERROR, tone=IconTone.DESTRUCTIVE, size=16)
        if record.get("fully_correct") is True:
            return icon_for(IconName.CHECK, tone=IconTone.BRAND, size=16)
        if record.get("status") in {"needs_review", "failed"}:
            return icon_for(IconName.WARNING, size=16)
        return icon_for(IconName.DOCUMENT, size=16)
