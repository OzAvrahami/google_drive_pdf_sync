"""Inline feedback and queue empty-state primitives."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui.components.buttons import ButtonVariant, PandaButton
from app.ui.theme.icons import IconName, IconTone, icon_for
from app.ui.theme.tokens import SPACING
from app.ui.theme.typography import TypographyRole, apply_typography


class FeedbackVariant(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


_FEEDBACK_ICONS = {
    FeedbackVariant.INFO: IconName.INFO,
    FeedbackVariant.WARNING: IconName.WARNING,
    FeedbackVariant.ERROR: IconName.ERROR,
    FeedbackVariant.SUCCESS: IconName.SUCCESS,
}


class InlineFeedback(QFrame):
    def __init__(
        self,
        text: str,
        *,
        variant: FeedbackVariant = FeedbackVariant.INFO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "feedback")
        self.setProperty("variant", variant.value)
        self.setAccessibleName(text)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(SPACING.adjacent)
        icon_label = QLabel()
        tone = IconTone.DESTRUCTIVE if variant is FeedbackVariant.ERROR else IconTone.DEFAULT
        icon_label.setPixmap(icon_for(_FEEDBACK_ICONS[variant], tone=tone, size=17).pixmap(17, 17))
        icon_label.setFixedSize(18, 18)
        message = QLabel(text)
        message.setWordWrap(True)
        apply_typography(message, TypographyRole.COMPACT_BODY)
        layout.addWidget(icon_label)
        layout.addWidget(message, 1)


class EmptyState(QFrame):
    def __init__(
        self,
        title: str,
        description: str,
        *,
        icon_name: IconName | str = IconName.DOCUMENT,
        action_text: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "emptyState")
        self.setAccessibleName(title)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(SPACING.adjacent)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_label = QLabel()
        icon_label.setProperty("pandaComponent", "emptyIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setPixmap(icon_for(icon_name, tone=IconTone.BRAND, size=28).pixmap(28, 28))
        root.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_typography(self.title_label, TypographyRole.SECTION_TITLE)
        root.addWidget(self.title_label)

        self.description_label = QLabel(description)
        self.description_label.setProperty("pandaRole", "muted")
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label.setWordWrap(True)
        apply_typography(self.description_label, TypographyRole.COMPACT_BODY)
        root.addWidget(self.description_label)

        self.action_button: PandaButton | None = None
        if action_text:
            self.action_button = PandaButton(action_text, variant=ButtonVariant.PRIMARY)
            root.addWidget(self.action_button, alignment=Qt.AlignmentFlag.AlignCenter)
