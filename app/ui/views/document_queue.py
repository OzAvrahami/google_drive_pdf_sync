"""Real Panda 2.0 Inbox and Needs Attention queue views."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from PySide6.QtCore import QItemSelectionModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.ui.components import ButtonVariant, EmptyState, PandaButton, SearchField
from app.ui.models import (
    AttentionSegment,
    DocumentColumn,
    DocumentFilterProxyModel,
    DocumentRoles,
    DocumentTableModel,
    QueueRoute,
)
from app.ui.models.queue_policy import belongs_to_route
from app.ui.theme.icons import IconName
from app.ui.theme.tokens import COLORS, CONTROLS, SPACING
from app.ui.theme.typography import TypographyRole, apply_typography


_ATTENTION_SEGMENTS: tuple[tuple[AttentionSegment, str], ...] = (
    (AttentionSegment.ALL, "הכל"),
    (AttentionSegment.NEEDS_REVIEW, "לבדיקה"),
    (AttentionSegment.FAILED, "נכשל"),
    (AttentionSegment.SKIPPED, "דולג"),
    (AttentionSegment.SUSPECTED_DUPLICATE, "חשד לכפילות"),
)

_STATUS_COLORS = {
    "new": (COLORS.surface_secondary, COLORS.informational),
    "needs_review": (COLORS.warning_tint, COLORS.warning),
    "failed": (COLORS.error_tint, COLORS.error),
    "skipped": (COLORS.irrelevant_tint, COLORS.irrelevant),
    "processed": (COLORS.irrelevant_tint, COLORS.processed),
    "approved": (COLORS.approval_tint, COLORS.approval),
    "exported": (COLORS.brand_tint, COLORS.exported),
    "confirmed_irrelevant": (COLORS.irrelevant_tint, COLORS.irrelevant),
    "excluded": (COLORS.irrelevant_tint, COLORS.irrelevant),
}


@dataclass(frozen=True, slots=True)
class QueueViewPresentation:
    title: str
    accessible_name: str
    empty_title: str
    empty_description: str
    empty_icon: IconName
    visible_columns: frozenset[DocumentColumn]


_QUEUE_PRESENTATION = {
    QueueRoute.INBOX: QueueViewPresentation(
        title="נכנסו",
        accessible_name="טבלת מסמכים נכנסים",
        empty_title="אין מסמכים חדשים",
        empty_description=(
            "לא נמצאו מסמכים שממתינים לעיבוד. אפשר לסרוק את Drive כדי לבדוק שוב."
        ),
        empty_icon=IconName.DOCUMENT,
        visible_columns=frozenset(
            {
                DocumentColumn.DOCUMENT,
                DocumentColumn.SELECTION,
                DocumentColumn.SOURCE,
                DocumentColumn.DOCUMENT_NUMBER,
                DocumentColumn.DATE,
                DocumentColumn.STATUS,
                DocumentColumn.CONFIDENCE,
            }
        ),
    ),
    QueueRoute.ATTENTION: QueueViewPresentation(
        title="דורש טיפול",
        accessible_name="טבלת מסמכים הדורשים טיפול",
        empty_title="אין מסמכים שדורשים טיפול",
        empty_description="אין כרגע מסמכים בקטגוריה שנבחרה.",
        empty_icon=IconName.SUCCESS,
        visible_columns=frozenset(
            {
                DocumentColumn.DOCUMENT,
                DocumentColumn.SELECTION,
                DocumentColumn.SUPPLIER,
                DocumentColumn.DOCUMENT_NUMBER,
                DocumentColumn.DATE,
                DocumentColumn.TOTAL,
                DocumentColumn.STATUS,
                DocumentColumn.CONFIDENCE,
                DocumentColumn.ATTENTION,
            }
        ),
    ),
    QueueRoute.IRRELEVANT: QueueViewPresentation(
        title="לא רלוונטי",
        accessible_name="טבלת מסמכים לא רלוונטיים",
        empty_title="אין מסמכים לא רלוונטיים",
        empty_description="לא סומנו מסמכים כלא רלוונטיים.",
        empty_icon=IconName.TRASH,
        visible_columns=frozenset(
            {
                DocumentColumn.DOCUMENT,
                DocumentColumn.SELECTION,
                DocumentColumn.SOURCE,
                DocumentColumn.SUPPLIER,
                DocumentColumn.DOCUMENT_NUMBER,
                DocumentColumn.DATE,
                DocumentColumn.TOTAL,
                DocumentColumn.STATUS,
            }
        ),
    ),
    QueueRoute.HISTORY: QueueViewPresentation(
        title="היסטוריה",
        accessible_name="טבלת מסמכים שיוצאו",
        empty_title="היסטוריית הייצוא ריקה",
        empty_description="עדיין לא יוצאו מסמכים לקובץ Excel.",
        empty_icon=IconName.ARCHIVE,
        visible_columns=frozenset(
            {
                DocumentColumn.DOCUMENT,
                DocumentColumn.SELECTION,
                DocumentColumn.SOURCE,
                DocumentColumn.SUPPLIER,
                DocumentColumn.DOCUMENT_NUMBER,
                DocumentColumn.DATE,
                DocumentColumn.TOTAL,
                DocumentColumn.STATUS,
            }
        ),
    ),
}


class QueueStatusDelegate(QStyledItemDelegate):
    """Render status semantics as a compact badge without coloring whole rows."""

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        raw_status = str(index.data(int(DocumentRoles.RAW_STATUS)) or "")
        label = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        background, foreground = _STATUS_COLORS.get(
            raw_status, (COLORS.irrelevant_tint, COLORS.text_muted)
        )

        base = QStyleOptionViewItem(option)
        self.initStyleOption(base, index)
        base.text = ""
        style = option.widget.style() if option.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, base, painter, option.widget)

        painter.save()
        metrics = option.fontMetrics
        width = min(option.rect.width() - 12, metrics.horizontalAdvance(label) + 18)
        badge = option.rect.adjusted(6, 9, 6 - option.rect.width() + width, -9)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(badge, 7, 7)
        painter.setPen(QColor(foreground))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()


class QueueSelectionDelegate(QStyledItemDelegate):
    """Render native row selection as the approved compact checkbox gutter."""

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        base = QStyleOptionViewItem(option)
        self.initStyleOption(base, index)
        base.text = ""
        style = option.widget.style() if option.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, base, painter, option.widget)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        size = 16
        box = option.rect.adjusted(
            (option.rect.width() - size) // 2,
            (option.rect.height() - size) // 2,
            -(option.rect.width() - size + 1) // 2,
            -(option.rect.height() - size + 1) // 2,
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(COLORS.brand if selected else COLORS.border_strong), 1.5))
        painter.setBrush(QColor(COLORS.brand if selected else COLORS.surface))
        painter.drawRoundedRect(box, 4, 4)
        if selected:
            painter.setPen(
                QPen(
                    QColor(COLORS.text_on_color),
                    1.8,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawLine(box.left() + 4, box.center().y(), box.left() + 7, box.bottom() - 4)
            painter.drawLine(box.left() + 7, box.bottom() - 4, box.right() - 3, box.top() + 4)
        painter.restore()


class QueueAttentionDelegate(QStyledItemDelegate):
    """Expose overlapping duplicate/manual state without full-row warning color."""

    @staticmethod
    def indicator_labels(index: QModelIndex) -> tuple[str, ...]:
        labels: list[str] = []
        if bool(index.data(int(DocumentRoles.DUPLICATE_SUSPECTED))):
            labels.append("חשד לכפילות")
        if bool(index.data(int(DocumentRoles.MANUALLY_CORRECTED))):
            labels.append("תוקן ידנית")
        return tuple(labels)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        decorated = QStyleOptionViewItem(option)
        self.initStyleOption(decorated, index)
        labels = self.indicator_labels(index)
        if labels:
            suffix = " · ".join(labels)
            decorated.text = f"{decorated.text}  ·  {suffix}" if decorated.text else suffix
            decorated.palette.setColor(
                decorated.palette.ColorRole.Text,
                QColor(COLORS.duplicate if "חשד לכפילות" in labels else COLORS.brand_hover),
            )
        style = option.widget.style() if option.widget is not None else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, decorated, painter, option.widget
        )


class DocumentQueueView(QWidget):
    """One route-specific proxy and native table over a shared source model."""

    processRequested = Signal()
    scanRequested = Signal()
    openDocumentRequested = Signal(str, object, str)

    def __init__(
        self,
        source_model: DocumentTableModel,
        route: QueueRoute,
        *,
        parent: QWidget | None = None,
    ) -> None:
        if route not in _QUEUE_PRESENTATION:
            raise ValueError(f"Unsupported document queue route: {route!r}")
        super().__init__(parent)
        self.route = route
        self.source_model = source_model
        self.proxy_model = DocumentFilterProxyModel(self)
        self.proxy_model.setSourceModel(source_model)
        self.proxy_model.set_route(route)
        self.presentation = _QUEUE_PRESENTATION[route]
        self.setProperty("pandaComponent", "documentQueueView")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._build_ui()
        self._connect_model_signals()
        self._refresh_state()

    @property
    def selected_document_ids(self) -> tuple[str, ...]:
        selection = self.table.selectionModel()
        if selection is None:
            return ()
        result: list[str] = []
        rows = sorted({index.row() for index in selection.selectedIndexes()})
        for row in rows:
            index = self.proxy_model.index(row, 0)
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
        else:
            selection = self.table.selectionModel()
            if selection is not None:
                selection.setCurrentIndex(
                    index, QItemSelectionModel.SelectionFlag.NoUpdate
                )
        self.table.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)
        self.table.setFocus()
        return True

    def set_attention_segment(self, segment: AttentionSegment) -> None:
        if self.route is not QueueRoute.ATTENTION:
            return
        segment = AttentionSegment(segment)
        self.proxy_model.set_attention_segment(segment)
        button = self.segment_buttons.get(segment)
        if button is not None:
            button.setChecked(True)
        self._refresh_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.page, SPACING.panel, SPACING.page, SPACING.page)
        root.setSpacing(SPACING.standard)

        heading = QHBoxLayout()
        heading.setSpacing(SPACING.adjacent)
        title = QLabel(self.presentation.title)
        apply_typography(title, TypographyRole.PAGE_TITLE)
        self.count_label = QLabel("0")
        self.count_label.setProperty("pandaComponent", "queueCount")
        apply_typography(self.count_label, TypographyRole.BADGE)
        heading.addWidget(title)
        heading.addWidget(self.count_label)
        heading.addSpacing(SPACING.section)
        self.search_field = SearchField()
        self.search_field.setMaximumWidth(390)
        self.search_field.textChanged.connect(self._search_changed)
        heading.addWidget(self.search_field, 1)
        heading.addStretch()

        self.workspace_button = PandaButton("פתיחת מסמך", variant=ButtonVariant.GHOST)
        self.workspace_button.setEnabled(False)
        self.workspace_button.setToolTip("בחרו מסמך לפתיחה בסביבת העבודה")
        self.workspace_button.clicked.connect(self._request_selected_open)
        heading.addWidget(self.workspace_button)
        if self.route is QueueRoute.INBOX:
            self.scan_button = PandaButton(
                "סריקת Drive",
                variant=ButtonVariant.SECONDARY,
                icon_name=IconName.SCAN,
            )
            self.scan_button.clicked.connect(self.scanRequested)
            heading.addWidget(self.scan_button)
            self.process_button = PandaButton(
                "עיבוד מסמכים",
                variant=ButtonVariant.PRIMARY,
                icon_name=IconName.PROCESS,
            )
            self.process_button.clicked.connect(self.processRequested)
            heading.addWidget(self.process_button)
        else:
            self.scan_button = None
            self.process_button = None
        root.addLayout(heading)

        self.segment_buttons: dict[AttentionSegment, PandaButton] = {}
        self.segment_group: QButtonGroup | None = None
        if self.route is QueueRoute.ATTENTION:
            controls = QHBoxLayout()
            controls.setSpacing(SPACING.adjacent)
            self.segment_group = QButtonGroup(self)
            self.segment_group.setExclusive(True)
            for segment, label in _ATTENTION_SEGMENTS:
                button = PandaButton(label, variant=ButtonVariant.GHOST)
                button.setProperty("pandaComponent", "queueSegment")
                button.setCheckable(True)
                button.setMinimumHeight(CONTROLS.compact_button_height)
                button.clicked.connect(
                    lambda _checked=False, value=segment: self.set_attention_segment(value)
                )
                self.segment_group.addButton(button)
                self.segment_buttons[segment] = button
                controls.addWidget(button)
            self.segment_buttons[AttentionSegment.ALL].setChecked(True)
            controls.addStretch()
            root.addLayout(controls)

        self.content_stack = QStackedWidget()
        self.table = QTableView()
        self.table.setProperty("pandaComponent", "documentQueueTable")
        self.table.setAccessibleName(self.presentation.accessible_name)
        self.table.setModel(self.proxy_model)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(
            DocumentTableModel.column_for(DocumentColumn.DATE),
            Qt.SortOrder.DescendingOrder,
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._request_index_open)
        self.table.activated.connect(self._request_index_open)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(CONTROLS.table_row_height)
        header = self.table.horizontalHeader()
        header.setFixedHeight(CONTROLS.table_header_height)
        header.setStretchLastSection(True)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, spec in enumerate(DocumentTableModel.column_spec(i) for i in range(self.source_model.columnCount())):
            self.table.setColumnWidth(column, spec.width_hint)
            self.table.setColumnHidden(column, spec.key not in self.presentation.visible_columns)
        selection_column = DocumentTableModel.column_for(DocumentColumn.SELECTION)
        header.setSectionResizeMode(selection_column, QHeaderView.ResizeMode.Fixed)
        self.table.setItemDelegateForColumn(
            selection_column, QueueSelectionDelegate(self.table)
        )
        status_column = DocumentTableModel.column_for(DocumentColumn.STATUS)
        self.table.setItemDelegateForColumn(status_column, QueueStatusDelegate(self.table))
        attention_column = DocumentTableModel.column_for(DocumentColumn.ATTENTION)
        self.table.setItemDelegateForColumn(
            attention_column, QueueAttentionDelegate(self.table)
        )
        self.content_stack.addWidget(self.table)

        self._empty_description = self.presentation.empty_description
        if self.route is QueueRoute.INBOX:
            self.empty_state = EmptyState(
                self.presentation.empty_title,
                self._empty_description,
                icon_name=self.presentation.empty_icon,
                action_text="סריקת Drive",
            )
            assert self.empty_state.action_button is not None
            self.empty_state.action_button.clicked.connect(self.scanRequested)
        else:
            self.empty_state = EmptyState(
                self.presentation.empty_title,
                self._empty_description,
                icon_name=self.presentation.empty_icon,
            )
        self.content_stack.addWidget(self.empty_state)
        root.addWidget(self.content_stack, 1)

        self.search_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.search_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.search_shortcut.activated.connect(self._focus_search)

    def _connect_model_signals(self) -> None:
        for signal in (
            self.proxy_model.modelReset,
            self.proxy_model.rowsInserted,
            self.proxy_model.rowsRemoved,
            self.proxy_model.layoutChanged,
        ):
            signal.connect(self._refresh_state)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_selection: self._selection_changed()
        )

    def _search_changed(self, query: str) -> None:
        self.proxy_model.set_search_query(query)
        self._refresh_state()

    def _focus_search(self) -> None:
        self.search_field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_field.selectAll()

    def _selection_changed(self, *_args) -> None:
        selected = self.selected_document_ids
        self.workspace_button.setEnabled(len(selected) == 1)
        self.workspace_button.setToolTip(
            "פתיחת המסמך הנבחר בסביבת העבודה"
            if len(selected) == 1
            else "בחרו מסמך אחד לפתיחה"
        )

    def _request_selected_open(self) -> None:
        selected = self.selected_document_ids
        if len(selected) == 1:
            self._emit_open_request(selected[0])

    def _request_index_open(self, index: QModelIndex) -> None:
        document_id = self.proxy_model.document_id_for_index(index)
        if document_id is not None:
            self._emit_open_request(document_id)

    def _emit_open_request(self, document_id: str) -> None:
        visible_ids = self.ordered_visible_document_ids
        if document_id in visible_ids:
            self.openDocumentRequested.emit(document_id, visible_ids, self.route.value)

    def _route_total(self) -> int:
        return sum(belongs_to_route(record, self.route) for record in self.source_model.records())

    def _refresh_state(self, *_args) -> None:
        visible = self.proxy_model.rowCount()
        self.count_label.setText(str(visible))
        self.content_stack.setCurrentWidget(self.table if visible else self.empty_state)
        if visible:
            return
        filtered = bool(self.proxy_model.search_query) or (
            self.route is QueueRoute.ATTENTION
            and self.proxy_model.attention_segment is not AttentionSegment.ALL
        )
        if filtered and self._route_total():
            self.empty_state.title_label.setText("לא נמצאו תוצאות")
            self.empty_state.description_label.setText(
                "אין תוצאות למסננים או לחיפוש הנוכחיים"
            )
        else:
            self.empty_state.title_label.setText(self.presentation.empty_title)
            self.empty_state.description_label.setText(self._empty_description)
