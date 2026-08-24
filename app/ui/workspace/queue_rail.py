"""Compact stable-ID queue context for Document Workspace."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QModelIndex, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from app.models.document import Document
from app.ui.models.workspace_queue_model import WorkspaceQueueModel, WorkspaceQueueRoles
from app.ui.theme.tokens import COLORS, CONTROLS, LAYOUT
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.workspace.presentation import build_workspace_presentation


DocumentProvider = Callable[[str], Document | None]


class WorkspaceQueueDelegate(QStyledItemDelegate):
    def __init__(self, provider: DocumentProvider, parent=None) -> None:
        super().__init__(parent)
        self._provider = provider

    def sizeHint(self, option, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), CONTROLS.table_row_height + 6)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        document_id = str(index.data(int(WorkspaceQueueRoles.DOCUMENT_ID)) or "")
        document = self._provider(document_id)
        current = bool(index.data(int(WorkspaceQueueRoles.IS_CURRENT)))
        base = QStyleOptionViewItem(option)
        self.initStyleOption(base, index)
        base.text = ""
        if current:
            base.palette.setColor(QPalette.ColorRole.Base, QColor(COLORS.selection))
            base.palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS.selection))
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, base, painter, option.widget)
        rect = option.rect.adjusted(10, 6, -10, -6)
        painter.save()
        if current:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS.brand))
            painter.drawRoundedRect(rect.right() - 3, rect.top(), 3, rect.height(), 1, 1)
        if document is None:
            primary, secondary = "מסמך לא זמין", document_id
            confidence = ""
        else:
            presentation = build_workspace_presentation(document)
            supplier = next(
                (field.value for field in presentation.fields if field.name == "supplier_name"),
                "",
            )
            primary = supplier or presentation.file_name or "מסמך ללא שם"
            secondary = presentation.file_name
            confidence = (
                f"{int(presentation.confidence * 100)}%"
                if presentation.confidence is not None
                else ""
            )
        metrics = option.fontMetrics
        painter.setPen(QColor(COLORS.text_heading))
        painter.drawText(
            rect.adjusted(0, 0, -4, -rect.height() // 2),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(primary, Qt.TextElideMode.ElideRight, rect.width() - 4),
        )
        painter.setPen(QColor(COLORS.text_secondary))
        secondary_rect = rect.adjusted(0, rect.height() // 2, -36, 0)
        painter.drawText(
            secondary_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(secondary, Qt.TextElideMode.ElideMiddle, secondary_rect.width()),
        )
        if confidence:
            painter.drawText(
                rect.adjusted(rect.width() - 34, rect.height() // 2, 0, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                confidence,
            )
        painter.restore()


class QueueRail(QFrame):
    def __init__(
        self,
        model: WorkspaceQueueModel,
        provider: DocumentProvider,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model = model
        self.setProperty("pandaComponent", "workspaceQueueRail")
        self.setMinimumWidth(LAYOUT.workspace_queue_minimum_width)
        self.setMaximumWidth(LAYOUT.workspace_queue_width)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.heading = QLabel("תור הטיפול · 0/0")
        self.heading.setContentsMargins(12, 10, 12, 10)
        apply_typography(self.heading, TypographyRole.LABEL)
        root.addWidget(self.heading)
        self.list_view = QListView()
        self.list_view.setProperty("pandaComponent", "workspaceQueueList")
        self.list_view.setAccessibleName("תור המסמכים בסביבת העבודה")
        self.list_view.setModel(model)
        self.list_view.setItemDelegate(WorkspaceQueueDelegate(provider, self.list_view))
        self.list_view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.list_view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.list_view.clicked.connect(self._activate)
        self.list_view.activated.connect(self._activate)
        root.addWidget(self.list_view, 1)
        model.currentChanged.connect(self._current_changed)

    def _activate(self, index: QModelIndex) -> None:
        document_id = index.data(int(WorkspaceQueueRoles.DOCUMENT_ID))
        if document_id:
            self.model.set_current_by_id(str(document_id))

    def _current_changed(self, document_id: object, index: int, total: int) -> None:
        self.heading.setText(f"תור הטיפול · {index + 1 if index >= 0 else 0}/{total}")
        if index >= 0:
            self.list_view.setCurrentIndex(self.model.index(index, 0))
            self.list_view.scrollTo(self.model.index(index, 0))
        self.list_view.viewport().update()

