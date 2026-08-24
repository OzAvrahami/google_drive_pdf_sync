"""Structured Workspace review panel with draft-bound edit controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.application.duplicate_comparison_service import DuplicateComparison
from app.domain.review_draft import ReviewDraft
from app.ui.components import (
    AuxiliaryBadgeVariant,
    ButtonVariant,
    FeedbackVariant,
    FieldEditor,
    FieldPresentationState,
    InlineFeedback,
    PandaButton,
    StatusBadge,
)
from app.ui.theme.tokens import LAYOUT, SPACING
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.workspace.field_display import FieldDisplay
from app.ui.workspace.duplicate_comparison import DuplicateComparisonPanel
from app.ui.workspace.presentation import WorkspaceDocumentPresentation


class ReviewPanel(QFrame):
    fieldChanged = Signal(str, str)
    saveRequested = Signal()
    approveRequested = Signal()
    irrelevantRequested = Signal()
    duplicateDismissRequested = Signal()
    duplicateConfirmRequested = Signal(str)
    openDuplicateCandidateRequested = Signal(str)

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
        self.field_widgets: list[QWidget] = []
        self.field_editors: dict[str, FieldEditor] = {}
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
        self.feedback: InlineFeedback | None = None
        self.duplicate_panel: DuplicateComparisonPanel | None = None
        self.action_layout = action_layout
        self.approve_button.clicked.connect(self.approveRequested)
        self.save_button.clicked.connect(self.saveRequested)
        self.irrelevant_button = PandaButton(
            "סמן כלא רלוונטי", variant=ButtonVariant.DESTRUCTIVE
        )
        self.irrelevant_button.clicked.connect(self.irrelevantRequested)
        action_layout.addWidget(self.approve_button)
        action_layout.addWidget(self.save_button)
        action_layout.addWidget(self.irrelevant_button)
        root.addWidget(actions)

    def set_presentation(
        self,
        presentation: WorkspaceDocumentPresentation,
        *,
        draft: ReviewDraft | None = None,
        editable: bool = False,
        duplicate_comparisons: tuple[DuplicateComparison, ...] = (),
        can_mark_irrelevant: bool = False,
    ) -> None:
        while self.context_layout.count():
            item = self.context_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for widget in self.field_widgets:
            self.body_layout.removeWidget(widget)
            widget.deleteLater()
        self.field_widgets = []
        self.field_editors = {}
        self.duplicate_panel = None

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
            self.duplicate_panel = DuplicateComparisonPanel(duplicate_comparisons)
            self.duplicate_panel.openCandidateRequested.connect(
                self.openDuplicateCandidateRequested
            )
            self.duplicate_panel.dismissRequested.connect(self.duplicateDismissRequested)
            self.duplicate_panel.confirmRequested.connect(self.duplicateConfirmRequested)
            self.context_layout.addWidget(self.duplicate_panel)
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
            if editable and draft is not None and field.name in draft.field_names:
                widget = FieldEditor(
                    field.label_he,
                    value=draft.current_value(field.name),
                    text_kind=field.text_kind,
                )
                widget.editor.textChanged.connect(
                    lambda value, name=field.name: self.fieldChanged.emit(name, value)
                )
                self.field_editors[field.name] = widget
                self._apply_draft_field(widget, draft, field.name)
            else:
                widget = FieldDisplay(field)
            self.field_widgets.append(widget)
            self.body_layout.insertWidget(insertion, widget)
            insertion += 1

        self.save_button.setVisible(editable)
        self.approve_button.setVisible(editable)
        self.irrelevant_button.setVisible(can_mark_irrelevant)
        self.irrelevant_button.setEnabled(can_mark_irrelevant)
        self.irrelevant_button.setToolTip(
            "סימון מסמך כלא רלוונטי והסרת עותק ה-PDF המקומי"
            if can_mark_irrelevant
            else "הפעולה אינה זמינה במצב הנוכחי"
        )
        if not editable:
            self.save_button.setEnabled(False)
            self.approve_button.setEnabled(False)

    def update_draft(self, draft: ReviewDraft) -> None:
        for field_name, editor in self.field_editors.items():
            self._apply_draft_field(editor, draft, field_name)

    def set_action_state(
        self,
        *,
        save_enabled: bool,
        approve_enabled: bool,
        save_reason: str = "",
        approve_reason: str = "",
    ) -> None:
        self.save_button.setEnabled(save_enabled)
        self.save_button.setToolTip(save_reason)
        self.save_button.setAccessibleDescription(save_reason)
        self.approve_button.setEnabled(approve_enabled)
        self.approve_button.setToolTip(approve_reason)
        self.approve_button.setAccessibleDescription(approve_reason)

    def show_feedback(
        self, text: str, variant: FeedbackVariant = FeedbackVariant.INFO
    ) -> None:
        self.clear_feedback()
        self.feedback = InlineFeedback(text, variant=variant)
        self.action_layout.insertWidget(0, self.feedback)

    def clear_feedback(self) -> None:
        if self.feedback is not None:
            self.action_layout.removeWidget(self.feedback)
            self.feedback.deleteLater()
            self.feedback = None

    @staticmethod
    def _apply_draft_field(
        editor: FieldEditor, draft: ReviewDraft, field_name: str
    ) -> None:
        field = draft.field(field_name)
        validation = draft.validation_result.for_field(field_name)
        if field.explicitly_cleared and field.changed_in_session:
            state = FieldPresentationState.INVALID
            helper = "מחיקת ערך שמור עדיין אינה נתמכת; לא ניתן לשמור או לאשר שינוי זה"
        elif validation is not None and validation.state.value == "invalid":
            state = FieldPresentationState.INVALID
            helper = validation.issues[0].message_he if validation.issues else "ערך לא תקין"
        elif field.changed_in_session:
            state = FieldPresentationState.CHANGED
            helper = "שונה בטיוטה הנוכחית"
        elif validation is not None and validation.state.value == "missing":
            state = FieldPresentationState.MISSING
            helper = validation.issues[0].message_he if validation.issues else "לא נמצא ערך"
        elif field.has_existing_correction:
            state = FieldPresentationState.CORRECTED
            helper = "תוקן בעבר"
        else:
            state = FieldPresentationState.NORMAL
            helper = "ערך שחולץ"
        editor.set_state(state)
        editor.set_helper_text(helper)
