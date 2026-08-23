"""Status and auxiliary badges backed by Panda domain presentation metadata."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from app.domain.status_presentation import SemanticCategory, presentation_for
from app.ui.theme.stylesheet import set_dynamic_property
from app.ui.theme.typography import TypographyRole, apply_typography


class AuxiliaryBadgeVariant(str, Enum):
    MANUAL_CORRECTION = "manual"
    DUPLICATE = "duplicate"


class StatusBadge(QLabel):
    def __init__(self, status: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "statusBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_typography(self, TypographyRole.BADGE)
        self._status = ""
        self._semantic_category = SemanticCategory.NEUTRAL
        self.set_status(status)

    @classmethod
    def auxiliary(
        cls,
        text: str,
        variant: AuxiliaryBadgeVariant,
        parent: QWidget | None = None,
    ) -> "StatusBadge":
        badge = cls.__new__(cls)
        QLabel.__init__(badge, parent)
        badge.setProperty("pandaComponent", "auxiliaryBadge")
        badge.setProperty("status", variant.value)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_typography(badge, TypographyRole.BADGE)
        badge._status = variant.value
        badge._semantic_category = SemanticCategory.NEUTRAL
        badge.setText(f"●  {text}")
        badge.setAccessibleName(text)
        return badge

    @property
    def status(self) -> str:
        return self._status

    @property
    def semantic_category(self) -> SemanticCategory:
        return self._semantic_category

    def set_status(self, status: str) -> None:
        presentation = presentation_for(status)
        self._status = status
        self._semantic_category = presentation.semantic_category
        self.setText(f"●  {presentation.label_he}")
        self.setAccessibleName(presentation.label_he)
        set_dynamic_property(self, "status", status)
