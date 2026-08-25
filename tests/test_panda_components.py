"""Headless QWidget behavior tests for Panda 2.0 reusable primitives."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.domain.status_presentation import presentation_for
from app.domain.validation import FieldState
from app.ui.components import (
    AuxiliaryBadgeVariant,
    ButtonVariant,
    ConfirmationDialog,
    ConfirmationPanel,
    EmptyState,
    FeedbackVariant,
    FieldEditor,
    FieldPresentationState,
    InlineFeedback,
    PandaButton,
    PandaIconButton,
    PandaTextField,
    SearchField,
    StatusBadge,
)
from app.ui.theme.direction import TextKind
from app.ui.theme.icons import IconName
from app.ui.theme.tokens import CONTROLS, LAYOUT


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    "status",
    [
        "new",
        "processed",
        "needs_review",
        "failed",
        "skipped",
        "approved",
        "exported",
        "confirmed_irrelevant",
        "excluded",
    ],
)
def test_status_badge_uses_domain_label_and_semantic_category(qapp, status: str) -> None:
    badge = StatusBadge(status)
    presentation = presentation_for(status)

    assert badge.status == status
    assert badge.property("status") == status
    assert presentation.label_he in badge.text()
    assert badge.semantic_category is presentation.semantic_category
    assert badge.accessibleName() == presentation.label_he


def test_auxiliary_badge_does_not_create_a_persisted_status(qapp) -> None:
    badge = StatusBadge.auxiliary(
        "חשד לכפילות", AuxiliaryBadgeVariant.DUPLICATE
    )

    assert badge.property("pandaComponent") == "auxiliaryBadge"
    assert badge.property("status") == "duplicate"
    assert "חשד לכפילות" in badge.text()


@pytest.mark.parametrize("variant", list(ButtonVariant))
def test_button_variant_is_reflected_as_a_dynamic_property(qapp, variant) -> None:
    button = PandaButton("פעולה", variant=variant)

    assert button.variant is variant
    assert button.property("variant") == variant.value
    assert button.focusPolicy() is Qt.FocusPolicy.StrongFocus


def test_approval_button_uses_dominant_approved_height(qapp) -> None:
    button = PandaButton("אישור", variant=ButtonVariant.APPROVAL)

    assert button.minimumHeight() == CONTROLS.approval_button_height


def test_button_variant_can_change_without_reconstruction(qapp) -> None:
    button = PandaButton("פעולה")

    button.set_variant(ButtonVariant.DESTRUCTIVE)

    assert button.variant is ButtonVariant.DESTRUCTIVE
    assert button.property("variant") == "destructive"


def test_disabled_button_retains_accessible_name_and_cannot_receive_focus(qapp) -> None:
    button = PandaButton("אישור מסמך", variant=ButtonVariant.APPROVAL)
    button.setEnabled(False)

    assert button.accessibleName() == "אישור מסמך"
    assert button.isEnabled() is False


def test_icon_button_requires_and_exposes_accessibility_text(qapp) -> None:
    button = PandaIconButton(IconName.SEARCH, accessible_text="חיפוש מסמכים")

    assert button.toolTip() == "חיפוש מסמכים"
    assert button.accessibleName() == "חיפוש מסמכים"
    assert button.focusPolicy() is Qt.FocusPolicy.StrongFocus
    assert button.icon().isNull() is False


def test_icon_button_rejects_missing_accessibility_text(qapp) -> None:
    with pytest.raises(ValueError, match="accessible text"):
        PandaIconButton(IconName.CLOSE, accessible_text="  ")


def test_text_field_applies_explicit_ltr_profile(qapp) -> None:
    field = PandaTextField(
        "INV-100", accessible_name="מספר מסמך", text_kind=TextKind.DOCUMENT_NUMBER
    )

    assert field.layoutDirection() is Qt.LayoutDirection.LeftToRight
    assert field.alignment() & Qt.AlignmentFlag.AlignRight
    assert field.accessibleName() == "מספר מסמך"
    assert field.focusPolicy() is Qt.FocusPolicy.StrongFocus


def test_text_field_error_state_is_dynamic(qapp) -> None:
    field = PandaTextField(accessible_name="סכום")

    field.set_error(True)
    assert field.validation_state == "error"
    field.set_error(False)
    assert field.validation_state == "normal"


def test_search_field_provides_icon_placeholder_and_clear_behavior(qapp) -> None:
    field = SearchField()

    assert field.accessibleName() == "חיפוש"
    assert "שם קובץ" in field.placeholderText()
    assert field.isClearButtonEnabled() is True
    assert field.actions()[0].icon().isNull() is False


@pytest.mark.parametrize("state", list(FieldPresentationState))
def test_field_editor_exposes_every_visual_state(qapp, state) -> None:
    field = FieldEditor("שדה", value="ערך", state=state)

    assert field.state is state
    assert field.property("validationState") == state.value
    assert field.editor.property("validationState") == state.value
    assert field.editor.isReadOnly() is (state is FieldPresentationState.DISABLED)


def test_field_editor_can_consume_review_provenance(qapp) -> None:
    field = FieldEditor("ספק")
    review_field = SimpleNamespace(
        displayed_value="ספק מתוקן",
        presentation_state=FieldState.CORRECTED,
    )

    field.apply_review_field(review_field)

    assert field.editor.text() == "ספק מתוקן"
    assert field.state is FieldPresentationState.CORRECTED


def test_field_editor_distinguishes_current_session_change(qapp) -> None:
    field = FieldEditor("ספק")
    review_field = SimpleNamespace(
        displayed_value="ספק חדש",
        presentation_state=FieldState.CORRECTED,
        changed_in_session=True,
    )

    field.apply_review_field(review_field)

    assert field.state is FieldPresentationState.CHANGED


@pytest.mark.parametrize("variant", list(FeedbackVariant))
def test_inline_feedback_exposes_semantic_variant(qapp, variant) -> None:
    feedback = InlineFeedback("הודעה", variant=variant)

    assert feedback.property("variant") == variant.value
    assert feedback.accessibleName() == "הודעה"


def test_empty_state_has_optional_focusable_action(qapp) -> None:
    empty = EmptyState("אין מסמכים", "התור ריק", action_text="סריקת Drive")

    assert empty.accessibleName() == "אין מסמכים"
    assert empty.action_button is not None
    assert empty.action_button.focusPolicy() is Qt.FocusPolicy.StrongFocus


def test_confirmation_panel_emits_confirm_and_cancel(qapp) -> None:
    panel = ConfirmationPanel(
        title="אישור",
        explanation="הסבר",
        consequence="השלכה",
        primary_action="המשך",
        destructive=True,
    )
    events: list[str] = []
    panel.confirmed.connect(lambda: events.append("confirmed"))
    panel.cancelled.connect(lambda: events.append("cancelled"))

    panel.primary_button.click()
    panel.cancel_button.click()

    assert events == ["confirmed", "cancelled"]
    assert panel.primary_button.variant is ButtonVariant.DESTRUCTIVE


def test_confirmation_dialog_connects_generic_actions(qapp) -> None:
    dialog = ConfirmationDialog(
        title="אישור",
        explanation="הסבר",
        consequence="השלכה",
        primary_action="אשר",
    )

    dialog.primary_button.click()

    assert dialog.result() == dialog.DialogCode.Accepted


def test_confirmation_dialog_defaults_keyboard_focus_to_safe_cancel(qapp) -> None:
    dialog = ConfirmationDialog(
        title="סימון כלא רלוונטי",
        explanation="הסבר",
        consequence="אין אפשרות שחזור",
        primary_action="סמן",
        destructive=True,
    )
    dialog.show()
    qapp.processEvents()

    assert dialog.cancel_button.isDefault()
    assert dialog.focusWidget() is dialog.cancel_button
    dialog.close()


def test_component_gallery_builds_at_approved_minimum_size(qapp) -> None:
    from scripts.show_panda2_components import PandaComponentGallery

    gallery = PandaComponentGallery()

    assert gallery.minimumWidth() == LAYOUT.minimum_width
    assert gallery.minimumHeight() == LAYOUT.minimum_height
    assert gallery.centralWidget() is not None
