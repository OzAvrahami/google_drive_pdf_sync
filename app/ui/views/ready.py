"""Panda 2.0 Ready queue with batch approval and selected export intent."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.application.approval_service import ApprovalService, BatchApprovalPlan
from app.ui.components import (
    ButtonVariant,
    ConfirmationDialog,
    EmptyState,
    FeedbackVariant,
    InlineFeedback,
    PandaButton,
    SearchField,
)
from app.ui.models import (
    DocumentColumn,
    DocumentFilterProxyModel,
    DocumentTableModel,
    QueueRoute,
    ReadySegment,
)
from app.ui.models.queue_policy import belongs_to_route
from app.ui.theme.icons import IconName
from app.ui.theme.tokens import COLORS, CONTROLS, SPACING
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.views.document_queue import QueueStatusDelegate


_READY_SEGMENTS: tuple[tuple[ReadySegment, str], ...] = (
    (ReadySegment.ALL, "הכל"),
    (ReadySegment.READY_TO_APPROVE, "מוכן לאישור"),
    (ReadySegment.READY_TO_EXPORT, "מוכן לייצוא"),
)

ExportConfirmation = Callable[[tuple[str, ...]], bool]


class ReadyView(QWidget):
    """One shared-model Ready route; persistence stays in application services."""

    openDocumentRequested = Signal(str, object, str)
    batchApproved = Signal(object)
    exportRequested = Signal(object)

    def __init__(
        self,
        source_model: DocumentTableModel,
        approval_service: ApprovalService,
        *,
        workbook_path: str,
        confirm_export: ExportConfirmation | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.source_model = source_model
        self.approval_service = approval_service
        self.workbook_path = workbook_path
        self._confirm_export = confirm_export or self._show_export_confirmation
        self._export_pending = False
        self._last_plan: BatchApprovalPlan | None = None
        self.proxy_model = DocumentFilterProxyModel(self)
        self.proxy_model.setSourceModel(source_model)
        self.proxy_model.set_route(QueueRoute.READY)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setProperty("pandaComponent", "readyView")
        self._build_ui()
        self._connect_signals()
        self._refresh_state()

    @property
    def selected_document_ids(self) -> tuple[str, ...]:
        selection = self.table.selectionModel()
        if selection is None:
            return ()
        result = []
        for index in sorted(selection.selectedRows(0), key=lambda item: item.row()):
            document_id = self.proxy_model.document_id_for_index(index)
            if document_id is not None:
                result.append(document_id)
        return tuple(result)

    @property
    def ordered_visible_document_ids(self) -> tuple[str, ...]:
        return tuple(
            document_id
            for row in range(self.proxy_model.rowCount())
            if (
                document_id := self.proxy_model.document_id_for_index(
                    self.proxy_model.index(row, 0)
                )
            )
            is not None
        )

    def restore_selected_document_ids(self, document_ids: Iterable[str]) -> None:
        selection = self.table.selectionModel()
        if selection is None:
            return
        selection.clearSelection()
        for document_id in document_ids:
            index = self.proxy_model.index_for_document_id(str(document_id), 0)
            if index.isValid():
                selection.select(
                    index,
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
        self._selection_changed()

    def focus_document(self, document_id: str, *, preserve_selection: bool = False) -> bool:
        index = self.proxy_model.index_for_document_id(document_id, 0)
        if not index.isValid():
            return False
        if not preserve_selection:
            self.restore_selected_document_ids((document_id,))
        self.table.setCurrentIndex(index)
        self.table.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)
        return True

    def set_ready_segment(self, segment: ReadySegment) -> None:
        segment = ReadySegment(segment)
        self.proxy_model.set_ready_segment(segment)
        self.segment_buttons[segment].setChecked(True)
        self._refresh_state()

    def set_manually_corrected_only(self, enabled: bool) -> None:
        self.manual_button.setChecked(bool(enabled))
        self.proxy_model.set_manually_corrected_only(enabled)
        self._refresh_state()

    def set_export_pending(self, pending: bool) -> None:
        self._export_pending = bool(pending)
        self._selection_changed()

    def show_export_result(self, result: dict) -> None:
        outcome = result.get("outcome")
        exported = int(result.get("exported", 0))
        persistence_error = str(result.get("status_persistence_error", "") or "")
        if persistence_error:
            self._set_feedback(
                "הקובץ נכתב, אך עדכון מצב המסמכים ב-Panda נכשל. "
                "המסמכים נשארו במוכן וניתן לנסות שוב בבטחה.",
                FeedbackVariant.WARNING,
            )
            return
        if outcome == "succeeded":
            self._set_feedback(
                f"הייצוא הושלם בהצלחה: {exported} מסמכים. הקובץ נשמר ב-{result.get('path', '')}",
                FeedbackVariant.SUCCESS,
            )
        else:
            requested = len(result.get("requested_ids", ()))
            remaining = max(0, requested - exported)
            self._set_feedback(
                f"הייצוא הושלם חלקית: {exported} יוצאו, {remaining} לא יוצאו.",
                FeedbackVariant.WARNING,
            )

    def show_export_error(self, message: str) -> None:
        self._set_feedback(f"הייצוא נכשל: {message}", FeedbackVariant.ERROR)

    def show_blockers(self) -> None:
        if self._last_plan is None or not self._last_plan.blocker_ids:
            return
        self.set_ready_segment(ReadySegment.READY_TO_APPROVE)
        self.restore_selected_document_ids(self._last_plan.blocker_ids)
        first = self._last_plan.blocker_ids[0]
        self.focus_document(first, preserve_selection=True)

    def approve_selected(self) -> None:
        selected = self.selected_document_ids
        plan = self.approval_service.preflight_batch(selected)
        self._last_plan = plan
        if plan.blocker_ids:
            self._set_feedback(
                f"האישור נחסם על-ידי {plan.blocker_count} מסמכים.",
                FeedbackVariant.WARNING,
            )
            self._selection_changed()
            return
        result = self.approval_service.approve_batch(selected)
        if result.approved_ids:
            unavailable = len(result.plan.ineligible_reasons) + len(
                result.plan.missing_ids
            )
            detail = (
                f" {unavailable} מסמכים לא היו זמינים או זכאים לאישור."
                if unavailable
                else ""
            )
            self._set_feedback(
                f"{len(result.approved_ids)} מסמכים אושרו ומוכנים לייצוא.{detail}",
                FeedbackVariant.WARNING if unavailable else FeedbackVariant.SUCCESS,
            )
            self.batchApproved.emit(result.approved_ids)
        self._selection_changed()

    def request_selected_export(self) -> None:
        selected = self.selected_document_ids
        plan = self.approval_service.preflight_batch(selected)
        approved_ids = plan.already_approved_ids
        if not approved_ids or self._export_pending:
            return
        if self._confirm_export(approved_ids):
            self.exportRequested.emit(approved_ids)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.page, SPACING.panel, SPACING.page, SPACING.page)
        root.setSpacing(SPACING.standard)

        heading = QHBoxLayout()
        title = QLabel("מוכן")
        apply_typography(title, TypographyRole.PAGE_TITLE)
        self.count_label = QLabel("0")
        self.count_label.setProperty("pandaComponent", "queueCount")
        apply_typography(self.count_label, TypographyRole.BADGE)
        heading.addWidget(title)
        heading.addWidget(self.count_label)
        heading.addStretch()
        self.open_button = PandaButton("פתיחת מסמך", variant=ButtonVariant.GHOST)
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._request_selected_open)
        heading.addWidget(self.open_button)
        root.addLayout(heading)

        controls = QHBoxLayout()
        self.search_field = SearchField()
        self.search_field.setMaximumWidth(390)
        controls.addWidget(self.search_field)
        controls.addStretch()
        self.segment_group = QButtonGroup(self)
        self.segment_group.setExclusive(True)
        self.segment_buttons: dict[ReadySegment, PandaButton] = {}
        for segment, label in _READY_SEGMENTS:
            button = PandaButton(label, variant=ButtonVariant.GHOST)
            button.setProperty("pandaComponent", "queueSegment")
            button.setCheckable(True)
            button.setMinimumHeight(CONTROLS.compact_button_height)
            button.clicked.connect(
                lambda _checked=False, value=segment: self.set_ready_segment(value)
            )
            self.segment_group.addButton(button)
            self.segment_buttons[segment] = button
            controls.addWidget(button)
        self.segment_buttons[ReadySegment.ALL].setChecked(True)
        self.manual_button = PandaButton("תוקן ידנית", variant=ButtonVariant.GHOST)
        self.manual_button.setCheckable(True)
        self.manual_button.clicked.connect(self.set_manually_corrected_only)
        controls.addWidget(self.manual_button)
        root.addLayout(controls)

        self.batch_bar = QFrame()
        self.batch_bar.setProperty("pandaComponent", "readyBatchBar")
        batch = QHBoxLayout(self.batch_bar)
        batch.setContentsMargins(12, 5, 12, 5)
        batch.setSpacing(SPACING.adjacent)
        self.selection_label = QLabel()
        apply_typography(self.selection_label, TypographyRole.LABEL)
        self.approve_button = PandaButton(
            "אשר נבחרים", variant=ButtonVariant.APPROVAL
        )
        self.approve_button.clicked.connect(self.approve_selected)
        self.export_button = PandaButton(
            "ייצוא נבחרים", variant=ButtonVariant.SECONDARY
        )
        self.export_button.clicked.connect(self.request_selected_export)
        self.show_blockers_button = PandaButton(
            "הצג מסמכים", variant=ButtonVariant.GHOST
        )
        self.show_blockers_button.clicked.connect(self.show_blockers)
        self.clear_button = PandaButton("נקה בחירה", variant=ButtonVariant.GHOST)
        self.clear_button.clicked.connect(self.table_clear_selection)
        batch.addWidget(self.selection_label)
        batch.addWidget(self.approve_button)
        batch.addWidget(self.export_button)
        batch.addWidget(self.show_blockers_button)
        batch.addStretch()
        batch.addWidget(self.clear_button)
        self.batch_bar.hide()
        root.addWidget(self.batch_bar)

        self.feedback_host = QVBoxLayout()
        self.feedback_widget: InlineFeedback | None = None
        root.addLayout(self.feedback_host)

        self.content_stack = QStackedWidget()
        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(
            DocumentTableModel.column_for(DocumentColumn.DATE),
            Qt.SortOrder.DescendingOrder,
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(CONTROLS.table_row_height)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column in range(self.source_model.columnCount()):
            self.table.setColumnWidth(
                column, self.source_model.column_spec(column).width_hint
            )
        self.table.setColumnHidden(
            DocumentTableModel.column_for(DocumentColumn.ATTENTION), True
        )
        self.table.setItemDelegateForColumn(
            DocumentTableModel.column_for(DocumentColumn.STATUS),
            QueueStatusDelegate(self.table),
        )
        self.content_stack.addWidget(self.table)
        self.empty_state = EmptyState(
            "אין מסמכים מוכנים",
            "אין כרגע מסמכים שממתינים לאישור או לייצוא.",
            icon_name=IconName.SUCCESS,
        )
        self.content_stack.addWidget(self.empty_state)
        root.addWidget(self.content_stack, 1)

    def _connect_signals(self) -> None:
        self.search_field.textChanged.connect(self._search_changed)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.table.doubleClicked.connect(self._request_index_open)
        self.table.activated.connect(self._request_index_open)
        for signal in (
            self.proxy_model.modelReset,
            self.proxy_model.rowsInserted,
            self.proxy_model.rowsRemoved,
            self.proxy_model.layoutChanged,
        ):
            signal.connect(self._refresh_state)

    def _selection_changed(self, *_args) -> None:
        selected = self.selected_document_ids
        self.open_button.setEnabled(len(selected) == 1)
        self.batch_bar.setVisible(bool(selected))
        if not selected:
            self._last_plan = None
            return
        plan = self.approval_service.preflight_batch(selected)
        self._last_plan = plan
        approved = len(plan.already_approved_ids)
        approvable = len(plan.approvable_ids)
        unavailable = len(plan.ineligible_reasons) + len(plan.missing_ids)
        unavailable_label = f" · {unavailable} לא זמינים" if unavailable else ""
        self.selection_label.setText(
            f"{len(selected)} נבחרו · {approvable} לאישור · {approved} לייצוא"
            f"{unavailable_label}"
        )
        self.approve_button.setText(f"אשר נבחרים ({approvable})")
        self.approve_button.setEnabled(plan.can_execute)
        self.export_button.setText(f"ייצוא נבחרים ({approved})")
        self.export_button.setEnabled(approved > 0 and not self._export_pending)
        self.show_blockers_button.setVisible(bool(plan.blocker_ids))
        if plan.blocker_ids:
            self.approve_button.setToolTip(
                f"האישור נחסם על-ידי {plan.blocker_count} מסמכים"
            )
        else:
            self.approve_button.setToolTip("אישור המסמכים הזכאים שנבחרו")

    def table_clear_selection(self) -> None:
        self.table.clearSelection()
        self._selection_changed()

    def _search_changed(self, query: str) -> None:
        selected = self.selected_document_ids
        self.proxy_model.set_search_query(query)
        self.restore_selected_document_ids(selected)
        self._refresh_state()

    def _request_selected_open(self) -> None:
        selected = self.selected_document_ids
        if len(selected) == 1:
            self._emit_open_request(selected[0])

    def _request_index_open(self, index: QModelIndex) -> None:
        document_id = self.proxy_model.document_id_for_index(index)
        if document_id:
            self._emit_open_request(document_id)

    def _emit_open_request(self, document_id: str) -> None:
        ids = self.ordered_visible_document_ids
        if document_id in ids:
            self.openDocumentRequested.emit(document_id, ids, QueueRoute.READY.value)

    def _refresh_state(self, *_args) -> None:
        count = self.proxy_model.rowCount()
        self.count_label.setText(str(count))
        self.content_stack.setCurrentWidget(self.table if count else self.empty_state)
        filtered = bool(self.proxy_model.search_query) or (
            self.proxy_model.ready_segment is not ReadySegment.ALL
            or self.proxy_model.manually_corrected_only
        )
        if not count and filtered and self._route_total():
            self.empty_state.description_label.setText(
                "אין תוצאות למסננים או לחיפוש הנוכחיים"
            )
        else:
            self.empty_state.description_label.setText(
                "אין כרגע מסמכים שממתינים לאישור או לייצוא."
            )

    def _route_total(self) -> int:
        return sum(
            belongs_to_route(record, QueueRoute.READY)
            for record in self.source_model.records()
        )

    def _show_export_confirmation(self, document_ids: tuple[str, ...]) -> bool:
        dialog = ConfirmationDialog(
            title="ייצוא מסמכים נבחרים",
            explanation=f"{len(document_ids)} מסמכים מאושרים ייכתבו לקובץ האקסל של Panda.",
            consequence=f"יעד: {Path(self.workbook_path).name}",
            primary_action="ייצוא לאקסל",
            parent=self,
        )
        dialog.cancel_button.setFocus()
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _set_feedback(self, text: str, variant: FeedbackVariant) -> None:
        if self.feedback_widget is not None:
            self.feedback_host.removeWidget(self.feedback_widget)
            self.feedback_widget.deleteLater()
        self.feedback_widget = InlineFeedback(text, variant=variant)
        self.feedback_host.addWidget(self.feedback_widget)
