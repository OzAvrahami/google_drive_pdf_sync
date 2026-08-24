"""Panda 2.0 Document Workspace session and editing coordination."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import QBoxLayout, QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.application.document_review_service import DocumentReviewService
from app.domain.review_draft import ReviewDraft
from app.domain.workflow_policy import can_approve_structurally, can_review_edit
from app.models.document import Document
from app.ui.components import ConfirmationDialog, FeedbackVariant
from app.ui.models.workspace_queue_model import WorkspaceQueueModel
from app.ui.theme.tokens import LAYOUT
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.workspace.presentation import build_workspace_presentation
from app.ui.workspace.queue_rail import QueueRail
from app.ui.workspace.review_panel import ReviewPanel
from app.ui.workspace.workspace_header import WorkspaceHeader

try:
    from app.ui.workspace.source_preview import SourcePreview
except ModuleNotFoundError:  # H1 remains independently stageable before native PDF H2.
    from app.ui.workspace.source_placeholder import SourcePlaceholder as SourcePreview


DocumentProvider = Callable[[str], Document | None]
DiscardConfirmation = Callable[[str], bool]


class ApprovalOutcome(Protocol):
    approved: bool
    document_id: str
    reason_codes: tuple[str, ...]
    document: Document | None
    corrections_saved: bool
    learning_failures: tuple[object, ...]
    failure_stage: str | None


ApprovalExecutor = Callable[[ReviewDraft], ApprovalOutcome]


_REASON_MESSAGES = {
    "review_not_allowed": "המסמך במצב לקריאה בלבד ואינו ניתן לעריכה.",
    "status_not_approvable": "מצב המסמך אינו מאפשר אישור.",
    "explicit_clear_not_persistable": "מחיקת ערך שמור עדיין אינה נתמכת; יש להחזיר את הערך לפני שמירה או אישור.",
    "invalid_draft_input": "יש לתקן את הערכים הלא תקינים לפני שמירה או אישור.",
    "invalid_number": "יש לתקן את הערך המספרי לפני האישור.",
    "invalid_date": "יש לתקן את התאריך לפני האישור.",
    "required_missing": "שדה חובה חסר לפי מדיניות האימות הפעילה.",
    "stale_document_status": "מצב המסמך השתנה ברקע. יש לרענן לפני שמירה או אישור.",
    "stale_document_updated": "המסמך השתנה ברקע. הטיוטה נשמרה אך לא ניתן לכתוב עד לרענון.",
    "document_not_found": "המסמך אינו זמין עוד.",
    "save_failed": "שמירת התיקון נכשלה. לא בוצע אישור.",
    "approval_persistence_failed": "התיקון נשמר, אך אישור המסמך נכשל. המסמך נשאר ללא אישור.",
    "review_preflight_failed": "לא ניתן לבדוק את הטיוטה מול המסמך השמור.",
}


class WorkspaceView(QWidget):
    backRequested = Signal(str, str)
    documentSaved = Signal(str)
    documentApproved = Signal(str)

    def __init__(
        self,
        document_provider: DocumentProvider,
        *,
        review_service: DocumentReviewService | None = None,
        approval_executor: ApprovalExecutor | None = None,
        discard_confirmation: DiscardConfirmation | None = None,
        source_preview: SourcePreview | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "workspaceView")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._provider = document_provider
        self._review_service = review_service
        self._approval_executor = approval_executor
        self._discard_confirmation = discard_confirmation
        self._draft: ReviewDraft | None = None
        self._editable = False
        self._background_changed = False
        self._suspend_current_load = False
        self.origin_route = ""
        self.origin_label = ""
        self.queue_model = WorkspaceQueueModel(parent=self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = WorkspaceHeader()
        root.addWidget(self.header)
        self.regions = QWidget()
        region_layout = QHBoxLayout(self.regions)
        region_layout.setDirection(QBoxLayout.Direction.RightToLeft)
        region_layout.setContentsMargins(0, 0, 0, 0)
        region_layout.setSpacing(0)
        self.queue_rail = QueueRail(self.queue_model, self._provider)
        self.source_preview = source_preview or SourcePreview()
        self.review_panel = ReviewPanel()
        region_layout.addWidget(self.review_panel)
        region_layout.addWidget(self.source_preview, 1)
        region_layout.addWidget(self.queue_rail)
        root.addWidget(self.regions, 1)

        self.unavailable = QLabel("המסמך אינו זמין עוד")
        self.unavailable.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unavailable.setVisible(False)
        apply_typography(self.unavailable, TypographyRole.SECTION_TITLE)
        root.addWidget(self.unavailable)

        self.header.backRequested.connect(self.return_to_queue)
        self.header.previousRequested.connect(self._request_previous)
        self.header.nextRequested.connect(self._request_next)
        self.queue_rail.documentRequested.connect(self._request_document)
        self.queue_model.currentChanged.connect(self._current_changed)
        self.review_panel.fieldChanged.connect(self._field_changed)
        self.review_panel.saveRequested.connect(self.save_current_draft)
        self.review_panel.approveRequested.connect(self.approve_current_draft)
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.escape_shortcut.activated.connect(self.return_to_queue)

    @property
    def current_document_id(self) -> str | None:
        return self.queue_model.current_document_id

    @property
    def current_draft(self) -> ReviewDraft | None:
        return self._draft

    @property
    def is_dirty(self) -> bool:
        return bool(self._draft and self._draft.is_dirty)

    @property
    def is_editable(self) -> bool:
        return self._editable

    @property
    def background_changed(self) -> bool:
        return self._background_changed

    def set_discard_confirmation(self, callback: DiscardConfirmation | None) -> None:
        self._discard_confirmation = callback

    def open_session(
        self,
        *,
        origin_route: str,
        origin_label: str,
        ordered_document_ids: Iterable[str],
        current_document_id: str,
    ) -> None:
        self.origin_route = str(origin_route)
        self.origin_label = origin_label
        self.queue_model.start_session(ordered_document_ids, current_document_id)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def confirm_discard_changes(self, reason: str) -> bool:
        if not self.is_dirty:
            return True
        if self._discard_confirmation is not None:
            discard = bool(self._discard_confirmation(reason))
        else:
            dialog = ConfirmationDialog(
                title="שינויים שלא נשמרו",
                explanation="יש בטיוטה שינויים שלא נשמרו.",
                consequence="יציאה כעת תבטל את השינויים בטיוטה בלבד.",
                primary_action="בטל שינויים",
                destructive=True,
                cancel_text="המשך עריכה",
                parent=self,
            )
            discard = dialog.exec() == QDialog.DialogCode.Accepted
        if discard:
            self._draft = None
            self.header.set_dirty(False, editable=self._editable)
        return discard

    def return_to_queue(self) -> None:
        if not self.origin_route or not self.confirm_discard_changes("back"):
            return
        self.backRequested.emit(self.origin_route, self.current_document_id or "")

    def refresh_current_document(self) -> None:
        document = (
            self._provider(self.current_document_id)
            if self.current_document_id
            else None
        )
        if self.is_dirty and document is not None and self._document_changed(document):
            self._mark_background_change()
            return
        self._load_current(self.current_document_id)

    def reconcile_queue(
        self,
        visible_document_ids: Iterable[str],
        available_document_ids: Iterable[str],
        *,
        changed_document_id: str | None = None,
    ) -> None:
        visible = list(dict.fromkeys(str(value) for value in visible_document_ids))
        available = set(str(value) for value in available_document_ids)
        current = self.current_document_id
        if current and current not in available and self.is_dirty:
            self._mark_background_change("המסמך אינו זמין עוד במאגר. הטיוטה נשמרה במסך ולא תיכתב.")
            return

        self._suspend_current_load = True
        try:
            if current and current not in available:
                self.queue_model.remove_document_id(current)
                current = self.current_document_id
            keep_detached = bool(current and current in available and current not in visible)
            self.queue_model.refresh(
                (value for value in visible if value in available),
                keep_current_if_missing=keep_detached,
            )
        finally:
            self._suspend_current_load = False

        current = self.current_document_id
        document = self._provider(current) if current else None
        current_changed = changed_document_id is None or changed_document_id == current
        if self.is_dirty and current_changed and document is not None and self._document_changed(document):
            self._mark_background_change()
            self._update_header_navigation()
        else:
            self._load_current(current)

    def save_current_draft(self) -> bool:
        if self._draft is None or self._review_service is None or not self._editable:
            return False
        try:
            result = self._review_service.save_draft(self._draft)
        except Exception:
            self.review_panel.show_feedback(
                "שמירת התיקון נכשלה. המסמך לא שונה.", FeedbackVariant.ERROR
            )
            return False
        if not result.plan.can_save:
            self.review_panel.show_feedback(
                self._message_for_reasons(result.plan.reason_codes), FeedbackVariant.ERROR
            )
            self._refresh_action_state()
            return False

        document = result.document
        self._render_document(document, create_draft=True)
        if result.saved:
            self.documentSaved.emit(document.drive_file_id)
            if result.learning_failures:
                self.review_panel.show_feedback(
                    "התיקון נשמר, אך עדכון הלמידה לא הושלם.", FeedbackVariant.WARNING
                )
            else:
                self.review_panel.show_feedback("התיקון נשמר בהצלחה.", FeedbackVariant.SUCCESS)
        else:
            self.review_panel.show_feedback("אין שינוי הדורש שמירה.", FeedbackVariant.INFO)
        return True

    def approve_current_draft(self) -> bool:
        if self._draft is None or self._approval_executor is None or not self._editable:
            return False
        result = self._approval_executor(self._draft)
        if result.document is not None and (result.corrections_saved or result.approved):
            self._render_document(result.document, create_draft=not result.approved)
        if result.corrections_saved:
            self.documentSaved.emit(result.document_id)
        if result.approved:
            self.documentApproved.emit(result.document_id)
            if result.learning_failures:
                self.review_panel.show_feedback(
                    "המסמך אושר והתיקון נשמר, אך עדכון הלמידה לא הושלם.",
                    FeedbackVariant.WARNING,
                )
            else:
                self.review_panel.show_feedback(
                    "המסמך אושר בהצלחה ומוכן לייצוא.", FeedbackVariant.SUCCESS
                )
            return True

        if result.corrections_saved and result.failure_stage == "approval":
            message = "התיקון נשמר, אך אישור המסמך נכשל. המסמך נשאר ללא אישור."
        else:
            message = self._message_for_reasons(result.reason_codes)
        self.review_panel.show_feedback(message, FeedbackVariant.ERROR)
        return False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.return_to_queue()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        compact = event.size().width() < 1000
        self.queue_rail.setFixedWidth(
            LAYOUT.workspace_queue_minimum_width if compact else LAYOUT.workspace_queue_width
        )
        self.review_panel.setFixedWidth(
            LAYOUT.workspace_fields_minimum_width if compact else LAYOUT.workspace_fields_width
        )
        super().resizeEvent(event)

    def _request_previous(self) -> None:
        if self.confirm_discard_changes("previous"):
            self.queue_model.previous()

    def _request_next(self) -> None:
        if self.confirm_discard_changes("next"):
            self.queue_model.next()

    def _request_document(self, document_id: str) -> None:
        if document_id == self.current_document_id:
            return
        if self.confirm_discard_changes("queue"):
            self.queue_model.set_current_by_id(document_id)

    def _current_changed(self, document_id: object, _index: int, _total: int) -> None:
        if not self._suspend_current_load:
            self._load_current(str(document_id) if document_id else None)

    def _load_current(self, document_id: str | None) -> None:
        document = self._provider(document_id) if document_id else None
        if document is None:
            self._draft = None
            self._editable = False
            self.unavailable.setVisible(True)
            self.regions.setVisible(False)
            self.source_preview.release_source()
            return
        self._render_document(document, create_draft=True)

    def _render_document(self, document: Document, *, create_draft: bool) -> None:
        self.unavailable.setVisible(False)
        self.regions.setVisible(True)
        presentation = build_workspace_presentation(document)
        editable = bool(self._review_service is not None and can_review_edit(document))
        draft: ReviewDraft | None = None
        if editable and create_draft:
            try:
                draft = self._review_service.load_draft(document.drive_file_id)
            except Exception:
                editable = False
        self._draft = draft
        self._editable = editable
        self._background_changed = False
        self.header.set_presentation(
            presentation,
            origin_label=self.origin_label,
            position=self.queue_model.position,
            total=self.queue_model.total,
            can_previous=self.queue_model.can_go_previous,
            can_next=self.queue_model.can_go_next,
        )
        self.header.set_dirty(False, editable=editable)
        self.review_panel.clear_feedback()
        self.review_panel.set_presentation(presentation, draft=draft, editable=editable)
        self.source_preview.load_presentation(presentation)
        self._refresh_action_state()

    def _field_changed(self, field_name: str, value: str) -> None:
        if self._draft is None or not self._editable:
            return
        self._draft.set_value(field_name, value)
        self.review_panel.update_draft(self._draft)
        self.header.set_dirty(self._draft.is_dirty, editable=True)
        self.review_panel.clear_feedback()
        self._refresh_action_state()

    def _refresh_action_state(self) -> None:
        if self._draft is None or self._review_service is None or not self._editable:
            self.review_panel.set_action_state(
                save_enabled=False,
                approve_enabled=False,
                save_reason="המסמך במצב לקריאה בלבד.",
                approve_reason="מצב המסמך אינו מאפשר אישור.",
            )
            return
        try:
            plan = self._review_service.plan_save(self._draft)
            document = self._provider(self._draft.source_document_id)
        except Exception:
            plan = None
            document = None
        save_enabled = bool(self._draft.is_dirty and plan is not None and plan.can_save)
        blockers = bool(plan and plan.validation.has_blocking_errors)
        approve_enabled = bool(
            plan is not None
            and plan.can_save
            and not blockers
            and document is not None
            and can_approve_structurally(document)
            and self._approval_executor is not None
        )
        reasons = plan.reason_codes if plan is not None else ("review_preflight_failed",)
        self.review_panel.set_action_state(
            save_enabled=save_enabled,
            approve_enabled=approve_enabled,
            save_reason=(
                ""
                if save_enabled
                else (
                    "אין שינויים שלא נשמרו."
                    if not self._draft.is_dirty and not reasons
                    else self._message_for_reasons(reasons)
                )
            ),
            approve_reason=(
                ""
                if approve_enabled
                else self._message_for_reasons(
                    (*reasons, *(issue.code for issue in plan.validation.blockers))
                    if plan is not None
                    else reasons
                )
            ),
        )

    def _document_changed(self, document: Document) -> bool:
        if self._draft is None:
            return False
        return (
            document.id != self._draft.source_record_id
            or document.status != self._draft.source_status
            or (
                bool(self._draft.source_updated_at)
                and document.updated_at != self._draft.source_updated_at
            )
        )

    def _mark_background_change(self, message: str | None = None) -> None:
        self._background_changed = True
        self.review_panel.show_feedback(
            message
            or "המסמך השתנה ברקע. הטיוטה נשמרה במסך; יש לחזור לתור ולפתוח מחדש לפני כתיבה.",
            FeedbackVariant.WARNING,
        )
        self._refresh_action_state()

    def _update_header_navigation(self) -> None:
        document = (
            self._provider(self.current_document_id)
            if self.current_document_id
            else None
        )
        if document is None:
            return
        presentation = build_workspace_presentation(document)
        self.header.set_presentation(
            presentation,
            origin_label=self.origin_label,
            position=self.queue_model.position,
            total=self.queue_model.total,
            can_previous=self.queue_model.can_go_previous,
            can_next=self.queue_model.can_go_next,
        )
        self.header.set_dirty(self.is_dirty, editable=self._editable)

    @staticmethod
    def _message_for_reasons(reason_codes: Iterable[str]) -> str:
        codes = tuple(dict.fromkeys(reason_codes))
        if not codes:
            return "הפעולה אינה זמינה במצב הנוכחי."
        return " ".join(
            _REASON_MESSAGES.get(code, "לא ניתן להשלים את הפעולה.") for code in codes
        )
