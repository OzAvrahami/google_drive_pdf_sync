"""Panda 2.0 QWidget primitives; not wired into the legacy shell yet."""

from app.ui.components.badges import AuxiliaryBadgeVariant, StatusBadge
from app.ui.components.buttons import ButtonVariant, PandaButton, PandaIconButton
from app.ui.components.dialogs import ConfirmationDialog, ConfirmationPanel
from app.ui.components.feedback import EmptyState, FeedbackVariant, InlineFeedback
from app.ui.components.navigation import (
    NavigationButton,
    NavigationRail,
    TaskDockPlaceholder,
    TaskDockState,
)
from app.ui.components.fields import (
    FieldEditor,
    FieldPresentationState,
    PandaTextField,
    SearchField,
)

__all__ = [
    "AuxiliaryBadgeVariant",
    "ButtonVariant",
    "ConfirmationDialog",
    "ConfirmationPanel",
    "EmptyState",
    "FeedbackVariant",
    "FieldEditor",
    "FieldPresentationState",
    "InlineFeedback",
    "NavigationButton",
    "NavigationRail",
    "PandaButton",
    "PandaIconButton",
    "PandaTextField",
    "SearchField",
    "StatusBadge",
    "TaskDockPlaceholder",
    "TaskDockState",
]
