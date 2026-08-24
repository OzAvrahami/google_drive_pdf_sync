"""Intentional read-only placeholders for queue routes not migrated in Phase E."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.ui.components import EmptyState
from app.ui.routes import RouteDefinition
from app.ui.theme.icons import IconName


class QueueRoutePlaceholder(QWidget):
    def __init__(self, definition: RouteDefinition, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.definition = definition
        self.setProperty("pandaComponent", "routePlaceholder")
        self.setAccessibleName(definition.label_he)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state = EmptyState(
            definition.label_he,
            "מסך התור יתחבר למודל המסמכים בשלב הבא. בשלב זה התצוגה לקריאה בלבד.",
            icon_name=definition.icon if definition.icon else IconName.DOCUMENT,
        )
        self.empty_state.setFixedWidth(520)
        self.empty_state.setFixedHeight(260)
        layout.addWidget(self.empty_state, alignment=Qt.AlignmentFlag.AlignCenter)
