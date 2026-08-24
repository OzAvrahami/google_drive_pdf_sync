"""Read-only field/provenance primitive for the Workspace review panel."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui.theme.direction import apply_text_direction
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.workspace.presentation import WorkspaceField


class FieldDisplay(QFrame):
    def __init__(self, field: WorkspaceField, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "workspaceField")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 7, 10, 7)
        root.setSpacing(3)
        heading = QHBoxLayout()
        self.label = QLabel(field.label_he)
        apply_typography(self.label, TypographyRole.LABEL)
        self.provenance = QLabel()
        self.provenance.setProperty("pandaComponent", "workspaceProvenance")
        apply_typography(self.provenance, TypographyRole.HELPER)
        heading.addWidget(self.label)
        heading.addStretch()
        heading.addWidget(self.provenance)
        root.addLayout(heading)
        self.value = QLabel()
        self.value.setProperty("pandaComponent", "workspaceFieldValue")
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        apply_typography(self.value, TypographyRole.BODY)
        root.addWidget(self.value)
        self.set_field(field)

    def set_field(self, field: WorkspaceField) -> None:
        self.field = field
        self.setProperty("fieldState", field.state.value)
        self.value.setText(field.value or "—")
        self.value.setToolTip(field.value)
        apply_text_direction(self.value, field.text_kind)
        self.provenance.setText(field.helper_text)
        self.setAccessibleName(f"{field.label_he}: {field.value or 'חסר'}; {field.helper_text}")
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

