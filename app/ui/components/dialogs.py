"""Generic Panda confirmation content and dialog shell."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui.components.buttons import ButtonVariant, PandaButton
from app.ui.theme.icons import IconName, IconTone, icon_for
from app.ui.theme.tokens import LAYOUT, SPACING
from app.ui.theme.typography import TypographyRole, apply_typography


class ConfirmationPanel(QFrame):
    confirmed = Signal()
    cancelled = Signal()

    def __init__(
        self,
        *,
        title: str,
        explanation: str,
        consequence: str,
        primary_action: str,
        destructive: bool = False,
        cancel_text: str = "ביטול",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "confirmationPanel")
        self.setMinimumWidth(LAYOUT.confirmation_width)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 16)
        root.setSpacing(SPACING.standard)

        heading = QHBoxLayout()
        heading.setSpacing(SPACING.standard)
        icon_label = QLabel()
        tone = IconTone.DESTRUCTIVE if destructive else IconTone.BRAND
        icon_name = IconName.WARNING if destructive else IconName.INFO
        icon_label.setPixmap(icon_for(icon_name, tone=tone, size=22).pixmap(22, 22))
        icon_label.setFixedSize(28, 28)
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        apply_typography(title_label, TypographyRole.PAGE_TITLE)
        heading.addWidget(icon_label)
        heading.addWidget(title_label, 1)
        root.addLayout(heading)

        explanation_label = QLabel(explanation)
        explanation_label.setWordWrap(True)
        apply_typography(explanation_label, TypographyRole.BODY)
        root.addWidget(explanation_label)

        consequence_frame = QFrame()
        consequence_frame.setProperty("pandaComponent", "consequence")
        consequence_frame.setProperty("destructive", destructive)
        consequence_layout = QHBoxLayout(consequence_frame)
        consequence_layout.setContentsMargins(12, 9, 12, 9)
        consequence_label = QLabel(consequence)
        consequence_label.setWordWrap(True)
        apply_typography(consequence_label, TypographyRole.COMPACT_BODY)
        consequence_layout.addWidget(consequence_label)
        root.addWidget(consequence_frame)

        actions = QHBoxLayout()
        actions.setSpacing(SPACING.adjacent)
        self.primary_button = PandaButton(
            primary_action,
            variant=(ButtonVariant.DESTRUCTIVE if destructive else ButtonVariant.PRIMARY),
        )
        self.cancel_button = PandaButton(cancel_text, variant=ButtonVariant.SECONDARY)
        self.primary_button.clicked.connect(self.confirmed)
        self.cancel_button.clicked.connect(self.cancelled)
        actions.addWidget(self.primary_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        root.addLayout(actions)


class ConfirmationDialog(QDialog):
    def __init__(
        self,
        *,
        title: str,
        explanation: str,
        consequence: str,
        primary_action: str,
        destructive: bool = False,
        cancel_text: str = "ביטול",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(LAYOUT.confirmation_width)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.panel = ConfirmationPanel(
            title=title,
            explanation=explanation,
            consequence=consequence,
            primary_action=primary_action,
            destructive=destructive,
            cancel_text=cancel_text,
        )
        self.panel.confirmed.connect(self.accept)
        self.panel.cancelled.connect(self.reject)
        root.addWidget(self.panel)
        self.cancel_button.setDefault(True)
        self.cancel_button.setAutoDefault(True)
        self.cancel_button.setFocus()

    @property
    def primary_button(self) -> PandaButton:
        return self.panel.primary_button

    @property
    def cancel_button(self) -> PandaButton:
        return self.panel.cancel_button
