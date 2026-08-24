"""Structured, strictly read-only document information panel."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.components import AuxiliaryBadgeVariant, ButtonVariant, PandaButton, StatusBadge
from app.ui.theme.tokens import LAYOUT, SPACING
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.workspace.field_display import FieldDisplay
from app.ui.workspace.presentation import WorkspaceDocumentPresentation


class ReviewPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "workspaceReviewPanel")
        self.setMinimumWidth(LAYOUT.workspace_fields_minimum_width)
        self.setMaximumWidth(LAYOUT.workspace_fields_width)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        heading = QLabel("פרטי המסמך")
        heading.setContentsMargins(16, 12, 16, 10)
        apply_typography(heading, TypographyRole.SECTION_TITLE)
        root.addWidget(heading)

        self.scroll = QScrollArea()
        self.scroll.setProperty("pandaComponent", "workspaceReviewScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setProperty("pandaComponent", "workspaceReviewBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(14, 0, 14, 14)
        self.body_layout.setSpacing(SPACING.adjacent)
        self.context_layout = QVBoxLayout()
        self.context_layout.setSpacing(SPACING.tight)
        self.body_layout.addLayout(self.context_layout)
        self.field_widgets: list[FieldDisplay] = []
        self.body_layout.addStretch()
        self.scroll.setWidget(self.body)
        root.addWidget(self.scroll, 1)

        actions = QFrame()
        actions.setProperty("pandaComponent", "workspaceReadOnlyActions")
        action_layout = QVBoxLayout(actions)
        action_layout.setContentsMargins(14, 10, 14, 12)
        self.approve_button = PandaButton("אישור מסמך", variant=ButtonVariant.APPROVAL)
        self.approve_button.setEnabled(False)
        self.approve_button.setToolTip("אישור ועריכה יחוברו בשלב ההגירה הבא")
        self.save_button = PandaButton("שמירת תיקון", variant=ButtonVariant.GHOST)
        self.save_button.setEnabled(False)
        self.save_button.setToolTip("Workspace זה הוא לקריאה בלבד")
        action_layout.addWidget(self.approve_button)
        action_layout.addWidget(self.save_button)
        root.addWidget(actions)

    def set_presentation(self, presentation: WorkspaceDocumentPresentation) -> None:
        while self.context_layout.count():
            item = self.context_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for widget in self.field_widgets:
            self.body_layout.removeWidget(widget)
            widget.deleteLater()
        self.field_widgets = []

        badges = QWidget()
        badge_layout = QHBoxLayout(badges)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setSpacing(SPACING.tight)
        badge_layout.addWidget(StatusBadge(presentation.status))
        if presentation.was_manually_corrected:
            badge_layout.addWidget(
                StatusBadge.auxiliary("תוקן ידנית", AuxiliaryBadgeVariant.MANUAL_CORRECTION)
            )
        badge_layout.addStretch()
        self.context_layout.addWidget(badges)

        if presentation.is_duplicate_suspected:
            warning = QLabel(
                "חשד לכפילות"
                + (
                    f" · {presentation.duplicate_candidate_count} מועמדים אפשריים"
                    if presentation.duplicate_candidate_count
                    else ""
                )
            )
            warning.setProperty("pandaComponent", "workspaceDuplicateNotice")
            warning.setWordWrap(True)
            warning.setToolTip("פתרון כפילויות יתווסף בשלב מאוחר יותר")
            apply_typography(warning, TypographyRole.COMPACT_BODY)
            self.context_layout.addWidget(warning)
        if presentation.attention_text:
            attention = QLabel(presentation.attention_text)
            attention.setProperty("pandaComponent", "workspaceAttention")
            attention.setWordWrap(True)
            apply_typography(attention, TypographyRole.COMPACT_BODY)
            self.context_layout.addWidget(attention)
        if presentation.error_message:
            error = QLabel(presentation.error_message)
            error.setProperty("pandaComponent", "workspaceError")
            error.setWordWrap(True)
            apply_typography(error, TypographyRole.COMPACT_BODY)
            self.context_layout.addWidget(error)

        insertion = 1
        for field in presentation.fields:
            widget = FieldDisplay(field)
            self.field_widgets.append(widget)
            self.body_layout.insertWidget(insertion, widget)
            insertion += 1

