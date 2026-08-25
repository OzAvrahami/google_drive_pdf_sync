"""Composable filtering and typed sorting for Panda 2.0 document queues."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt

from app.ui.models.document_record import DocumentPresentationRecord
from app.ui.models.document_table_model import DocumentRoles, DocumentTableModel
from app.ui.models.queue_policy import (
    AttentionSegment,
    QueueRoute,
    ReadySegment,
    belongs_to_route,
    matches_attention_segment,
    matches_ready_segment,
)


class DocumentFilterProxyModel(QSortFilterProxyModel):
    """View-state-free proxy configured through explicit filter setters."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._route: QueueRoute | None = None
        self._search_query = ""
        self._attention_segment = AttentionSegment.ALL
        self._ready_segment = ReadySegment.ALL
        self._suspected_duplicate_only = False
        self._manually_corrected_only = False
        self.setDynamicSortFilter(True)
        self.setSortRole(int(DocumentRoles.SORT))

    @property
    def route(self) -> QueueRoute | None:
        return self._route

    @property
    def search_query(self) -> str:
        return self._search_query

    @property
    def attention_segment(self) -> AttentionSegment:
        return self._attention_segment

    @property
    def ready_segment(self) -> ReadySegment:
        return self._ready_segment

    @property
    def manually_corrected_only(self) -> bool:
        return self._manually_corrected_only

    def set_route(self, route: QueueRoute | None) -> None:
        route = QueueRoute(route) if route is not None else None
        if route != self._route:
            self.beginFilterChange()
            self._route = route
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def set_search_query(self, query: str | None) -> None:
        normalized = (query or "").strip().casefold()
        if normalized != self._search_query:
            self.beginFilterChange()
            self._search_query = normalized
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def set_attention_segment(self, segment: AttentionSegment) -> None:
        segment = AttentionSegment(segment)
        if segment is not self._attention_segment:
            self.beginFilterChange()
            self._attention_segment = segment
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def set_ready_segment(self, segment: ReadySegment) -> None:
        segment = ReadySegment(segment)
        if segment is not self._ready_segment:
            self.beginFilterChange()
            self._ready_segment = segment
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def set_suspected_duplicate_only(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled != self._suspected_duplicate_only:
            self.beginFilterChange()
            self._suspected_duplicate_only = enabled
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def set_manually_corrected_only(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled != self._manually_corrected_only:
            self.beginFilterChange()
            self._manually_corrected_only = enabled
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def clear_filters(self) -> None:
        self.beginFilterChange()
        self._route = None
        self._search_query = ""
        self._attention_segment = AttentionSegment.ALL
        self._ready_segment = ReadySegment.ALL
        self._suspected_duplicate_only = False
        self._manually_corrected_only = False
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source = self.sourceModel()
        if source is None:
            return False
        index = source.index(source_row, 0, source_parent)
        record = source.data(index, int(DocumentRoles.PRESENTATION_RECORD))
        if not isinstance(record, DocumentPresentationRecord):
            return False

        if self._route is not None and not belongs_to_route(record, self._route):
            return False
        if self._attention_segment is not AttentionSegment.ALL and not matches_attention_segment(
            record, self._attention_segment
        ):
            return False
        if self._ready_segment is not ReadySegment.ALL and not matches_ready_segment(
            record, self._ready_segment
        ):
            return False
        if self._suspected_duplicate_only and not record.is_duplicate_suspected:
            return False
        if self._manually_corrected_only and not record.was_manually_corrected:
            return False
        if self._search_query:
            haystack = " ".join(
                (
                    record.file_name,
                    record.supplier_name or "",
                    record.document_number or "",
                )
            ).casefold()
            if self._search_query not in haystack:
                return False
        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        source = self.sourceModel()
        if source is None:
            return False
        left_value = source.data(left, int(DocumentRoles.SORT))
        right_value = source.data(right, int(DocumentRoles.SORT))

        if left_value is None or right_value is None:
            if left_value is None and right_value is None:
                return self._tie_break(left, right)
            return left_value is None
        if left_value == right_value:
            return self._tie_break(left, right)
        try:
            return left_value < right_value
        except TypeError:
            return str(left_value).casefold() < str(right_value).casefold()

    def _tie_break(self, left: QModelIndex, right: QModelIndex) -> bool:
        source = self.sourceModel()
        left_id = source.data(left, int(DocumentRoles.DOCUMENT_ID))
        right_id = source.data(right, int(DocumentRoles.DOCUMENT_ID))
        return str(left_id).casefold() < str(right_id).casefold()

    def document_id_for_index(self, index: QModelIndex) -> str | None:
        if not index.isValid():
            return None
        value = self.data(index, int(DocumentRoles.DOCUMENT_ID))
        return str(value) if value is not None else None

    def index_for_document_id(self, document_id: str, column: int = 0) -> QModelIndex:
        source = self.sourceModel()
        if not isinstance(source, DocumentTableModel):
            return QModelIndex()
        source_index = source.index_for_document_id(document_id, column)
        return self.mapFromSource(source_index) if source_index.isValid() else QModelIndex()
