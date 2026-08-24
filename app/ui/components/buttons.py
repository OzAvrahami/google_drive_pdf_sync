"""Panda 2.0 text and icon button primitives."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QPushButton, QWidget

from app.ui.theme.icons import IconName, IconTone, icon_for
from app.ui.theme.stylesheet import set_dynamic_property
from app.ui.theme.tokens import CONTROLS
from app.ui.theme.typography import TypographyRole, apply_typography


class ButtonVariant(str, Enum):
    PRIMARY = "primary"
    APPROVAL = "approval"
    DARK = "dark"
    SECONDARY = "secondary"
    GHOST = "ghost"
    DESTRUCTIVE = "destructive"


class PandaButton(QPushButton):
    def __init__(
        self,
        text: str,
        *,
        variant: ButtonVariant = ButtonVariant.SECONDARY,
        icon_name: IconName | str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setProperty("pandaComponent", "button")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(text)
        apply_typography(self, TypographyRole.LABEL)
        self._icon_name: IconName | str | None = None
        self._variant = ButtonVariant.SECONDARY
        self.set_variant(variant)
        if icon_name is not None:
            self.set_icon(icon_name)

    @property
    def variant(self) -> ButtonVariant:
        return self._variant

    def set_variant(self, variant: ButtonVariant) -> None:
        self._variant = ButtonVariant(variant)
        set_dynamic_property(self, "variant", self._variant.value)
        minimum = (
            CONTROLS.approval_button_height
            if self._variant is ButtonVariant.APPROVAL
            else CONTROLS.button_height
        )
        self.setMinimumHeight(minimum)
        if self._icon_name is not None:
            self.set_icon(self._icon_name)

    def set_icon(self, icon_name: IconName | str) -> None:
        self._icon_name = icon_name
        if self._variant is ButtonVariant.DESTRUCTIVE:
            tone = IconTone.ON_DARK
        elif self._variant in {
            ButtonVariant.PRIMARY,
            ButtonVariant.APPROVAL,
            ButtonVariant.DARK,
        }:
            tone = IconTone.ON_DARK
        else:
            tone = IconTone.DEFAULT
        self.setIcon(icon_for(icon_name, tone=tone, size=17))
        self.setIconSize(QSize(17, 17))


class PandaIconButton(QPushButton):
    def __init__(
        self,
        icon_name: IconName | str,
        *,
        accessible_text: str,
        destructive: bool = False,
        size: int = CONTROLS.icon_button,
        parent: QWidget | None = None,
    ) -> None:
        if not accessible_text.strip():
            raise ValueError("Icon-only buttons require accessible text")
        super().__init__(parent)
        self.setProperty("pandaComponent", "iconButton")
        self.setProperty("destructive", destructive)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(accessible_text)
        self.setAccessibleName(accessible_text)
        self.setAccessibleDescription(accessible_text)
        self.setFixedSize(size, size)
        tone = IconTone.DESTRUCTIVE if destructive else IconTone.DEFAULT
        icon_size = max(14, min(20, size - 14))
        self.setIcon(icon_for(icon_name, tone=tone, size=icon_size))
        self.setIconSize(QSize(icon_size, icon_size))
