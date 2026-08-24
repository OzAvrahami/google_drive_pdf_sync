"""Panda 2.0 text fields and review-field presentation shell."""

from __future__ import annotations

from enum import Enum
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from app.ui.theme.direction import TextKind, apply_text_direction
from app.ui.theme.icons import IconName, icon_for
from app.ui.theme.stylesheet import repolish, set_dynamic_property
from app.ui.theme.tokens import SPACING
from app.ui.theme.typography import TypographyRole, apply_typography


class FieldPresentationState(str, Enum):
    NORMAL = "normal"
    CORRECTED = "corrected"
    CHANGED = "changed"
    LOW_CONFIDENCE = "low_confidence"
    MISSING = "missing"
    INVALID = "invalid"
    DISABLED = "disabled"


class PandaTextField(QLineEdit):
    def __init__(
        self,
        text: str = "",
        *,
        accessible_name: str = "",
        text_kind: TextKind = TextKind.AUTO,
        icon_name: IconName | str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setProperty("pandaComponent", "textField")
        self.setProperty("validationState", "normal")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if accessible_name:
            self.setAccessibleName(accessible_name)
        apply_typography(
            self,
            TypographyRole.TECHNICAL
            if text_kind not in {TextKind.HEBREW, TextKind.AUTO}
            else TypographyRole.BODY,
        )
        apply_text_direction(self, text_kind)
        self._leading_action: QAction | None = None
        if icon_name is not None:
            self._leading_action = self.addAction(
                icon_for(icon_name, size=16), QLineEdit.ActionPosition.LeadingPosition
            )

    @property
    def validation_state(self) -> str:
        return str(self.property("validationState"))

    def set_validation_state(self, state: FieldPresentationState | str) -> None:
        value = state.value if isinstance(state, FieldPresentationState) else str(state)
        set_dynamic_property(self, "validationState", value)

    def set_error(self, has_error: bool) -> None:
        self.set_validation_state("error" if has_error else "normal")


class SearchField(PandaTextField):
    def __init__(
        self,
        *,
        placeholder: str = "חיפוש לפי שם קובץ, ספק או מספר מסמך",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            accessible_name="חיפוש",
            text_kind=TextKind.AUTO,
            icon_name=IconName.SEARCH,
            parent=parent,
        )
        self.setProperty("pandaComponent", "textField")
        self.setProperty("fieldRole", "search")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)


_STATE_LABELS = {
    FieldPresentationState.NORMAL: "",
    FieldPresentationState.CORRECTED: "תוקן",
    FieldPresentationState.CHANGED: "שונה כעת",
    FieldPresentationState.LOW_CONFIDENCE: "ביטחון נמוך",
    FieldPresentationState.MISSING: "חסר",
    FieldPresentationState.INVALID: "לא תקין",
    FieldPresentationState.DISABLED: "לקריאה בלבד",
}


class FieldEditor(QFrame):
    """Presentation-only shell for future ReviewDraft field bindings."""

    def __init__(
        self,
        label: str,
        *,
        value: str = "",
        state: FieldPresentationState = FieldPresentationState.NORMAL,
        helper_text: str = "",
        text_kind: TextKind = TextKind.HEBREW,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "fieldEditor")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACING.tight)

        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(SPACING.adjacent)
        self.label = QLabel(label)
        apply_typography(self.label, TypographyRole.LABEL)
        self.state_label = QLabel()
        self.state_label.setProperty("pandaComponent", "fieldStateLabel")
        apply_typography(self.state_label, TypographyRole.HELPER)
        heading.addWidget(self.label)
        heading.addStretch()
        heading.addWidget(self.state_label)
        root.addLayout(heading)

        self.editor = PandaTextField(
            value,
            accessible_name=label,
            text_kind=text_kind,
        )
        root.addWidget(self.editor)

        self.helper = QLabel(helper_text)
        self.helper.setProperty("pandaRole", "helper")
        self.helper.setWordWrap(True)
        apply_typography(self.helper, TypographyRole.HELPER)
        self.helper.setVisible(bool(helper_text))
        root.addWidget(self.helper)

        self._state = FieldPresentationState.NORMAL
        self.set_state(state)

    @property
    def state(self) -> FieldPresentationState:
        return self._state

    def set_state(self, state: FieldPresentationState) -> None:
        self._state = FieldPresentationState(state)
        value = self._state.value
        self.setProperty("validationState", value)
        self.editor.set_validation_state(value)
        self.state_label.setProperty("validationState", value)
        self.state_label.setText(_STATE_LABELS[self._state])
        self.editor.setReadOnly(self._state is FieldPresentationState.DISABLED)
        repolish(self)
        repolish(self.state_label)

    def set_helper_text(self, text: str) -> None:
        self.helper.setText(text)
        self.helper.setVisible(bool(text))

    def apply_review_field(self, field: Any, *, read_only: bool = False) -> None:
        """Consume ReviewField-compatible provenance without persisting it."""
        self.editor.setText(str(getattr(field, "displayed_value", "")))
        if read_only:
            state = FieldPresentationState.DISABLED
        else:
            raw_state = getattr(
                getattr(field, "presentation_state", None), "value", "normal"
            )
            if raw_state in {"invalid", "missing"}:
                state = FieldPresentationState(raw_state)
            elif bool(getattr(field, "changed_in_session", False)):
                state = FieldPresentationState.CHANGED
            else:
                state = FieldPresentationState(raw_state)
        self.set_state(state)
