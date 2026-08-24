"""Typed QAbstractTableModel for Panda 2.0 document queues."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import Callable, Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt

from app.models.document import Document
from app.ui.models.document_record import DocumentPresentationRecord
from app.ui.models.queue_policy import route_for
from app.ui.theme.direction import TextKind, direction_profile_for
from app.ui.theme.tokens import CONTROLS


class DocumentColumn(StrEnum):
    DOCUMENT = "document"
    SOURCE = "source"
    SUPPLIER = "supplier"
    DOCUMENT_NUMBER = "document_number"
    DATE = "date"
    TOTAL = "total"
    STATUS = "status"
    CONFIDENCE = "confidence"
    ATTENTION = "attention"


class ColumnSemantic(StrEnum):
    DOCUMENT = "document"
    SOURCE = "source"
    PARTY = "party"
    IDENTIFIER = "identifier"
    DATE = "date"
    MONEY = "money"
    WORKFLOW = "workflow"
    CONFIDENCE = "confidence"
    ATTENTION = "attention"


class DocumentRoles(IntEnum):
    SORT = int(Qt.ItemDataRole.UserRole) + 1
    RAW_VALUE = SORT + 1
    DOCUMENT_ID = SORT + 2
    RECORD_ID = SORT + 3
    RAW_STATUS = SORT + 4
    STATUS_LABEL = SORT + 5
    STATUS_CATEGORY = SORT + 6
    QUEUE_ROUTE = SORT + 7
    DUPLICATE_SUSPECTED = SORT + 8
    MANUALLY_CORRECTED = SORT + 9
    ATTENTION_REASON = SORT + 10
    COLUMN_KEY = SORT + 11
    TEXT_KIND = SORT + 12
    PRESENTATION_RECORD = SORT + 13


DisplayAccessor = Callable[[DocumentPresentationRecord], str]
ValueAccessor = Callable[[DocumentPresentationRecord], object]


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    key: DocumentColumn
    header_he: str
    display_accessor: DisplayAccessor
    sort_accessor: ValueAccessor
    raw_accessor: ValueAccessor
    text_kind: TextKind
    default_visible: bool
    width_hint: int
    semantic_role: ColumnSemantic


_STATUS_SORT_RANK = {
    "new": 0,
    "needs_review": 10,
    "failed": 11,
    "skipped": 12,
    "processed": 20,
    "approved": 21,
    "exported": 30,
    "confirmed_irrelevant": 40,
    "excluded": 41,
}


def _empty(value: str | None) -> str:
    return value or ""


def _format_amount(value: Decimal | None) -> str:
    return "" if value is None else f"₪{value:,.2f}"


def _format_confidence(value: float | None) -> str:
    return "" if value is None else f"{int(value * 100)}%"


COLUMN_SPECS: tuple[ColumnSpec, ...] = (
    ColumnSpec(
        DocumentColumn.DOCUMENT,
        "מסמך",
        lambda record: record.file_name,
        lambda record: record.file_name.casefold(),
        lambda record: record.file_name,
        TextKind.FILENAME,
        True,
        230,
        ColumnSemantic.DOCUMENT,
    ),
    ColumnSpec(
        DocumentColumn.SOURCE,
        "מקור",
        lambda record: record.folder_path,
        lambda record: record.folder_path.casefold(),
        lambda record: record.folder_path,
        TextKind.PATH,
        False,
        145,
        ColumnSemantic.SOURCE,
    ),
    ColumnSpec(
        DocumentColumn.SUPPLIER,
        "ספק",
        lambda record: _empty(record.supplier_name),
        lambda record: _empty(record.supplier_name).casefold(),
        lambda record: record.supplier_name,
        TextKind.HEBREW,
        False,
        160,
        ColumnSemantic.PARTY,
    ),
    ColumnSpec(
        DocumentColumn.DOCUMENT_NUMBER,
        "מספר מסמך",
        lambda record: _empty(record.document_number),
        lambda record: _empty(record.document_number).casefold(),
        lambda record: record.document_number,
        TextKind.DOCUMENT_NUMBER,
        True,
        120,
        ColumnSemantic.IDENTIFIER,
    ),
    ColumnSpec(
        DocumentColumn.DATE,
        "תאריך",
        lambda record: _empty(record.document_date),
        lambda record: record.date_sort_value,
        lambda record: record.document_date,
        TextKind.DATE,
        True,
        100,
        ColumnSemantic.DATE,
    ),
    ColumnSpec(
        DocumentColumn.TOTAL,
        "סכום",
        lambda record: _format_amount(record.total),
        lambda record: record.total,
        lambda record: record.total,
        TextKind.AMOUNT,
        True,
        110,
        ColumnSemantic.MONEY,
    ),
    ColumnSpec(
        DocumentColumn.STATUS,
        "סטטוס",
        lambda record: record.status_label,
        lambda record: _STATUS_SORT_RANK[record.status],
        lambda record: record.status,
        TextKind.HEBREW,
        True,
        120,
        ColumnSemantic.WORKFLOW,
    ),
    ColumnSpec(
        DocumentColumn.CONFIDENCE,
        "ביטחון",
        lambda record: _format_confidence(record.confidence),
        lambda record: record.confidence,
        lambda record: record.confidence,
        TextKind.PERCENTAGE,
        True,
        86,
        ColumnSemantic.CONFIDENCE,
    ),
    ColumnSpec(
        DocumentColumn.ATTENTION,
        "סיבת טיפול",
        lambda record: record.attention_text,
        lambda record: record.attention_text.casefold(),
        lambda record: record.attention_reason.value,
        TextKind.HEBREW,
        True,
        240,
        ColumnSemantic.ATTENTION,
    ),
)


class DocumentTableModel(QAbstractTableModel):
    """A detached presentation snapshot with stable Drive-file identity."""

    def __init__(
        self,
        documents: Iterable[Document | DocumentPresentationRecord] = (),
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._records: list[DocumentPresentationRecord] = []
        self._rows_by_id: dict[str, int] = {}
        self.replace_documents(documents)

    @staticmethod
    def _record(document: Document | DocumentPresentationRecord) -> DocumentPresentationRecord:
        if isinstance(document, DocumentPresentationRecord):
            return document
        return DocumentPresentationRecord.from_document(document)

    @staticmethod
    def column_spec(column: int | DocumentColumn) -> ColumnSpec:
        if isinstance(column, DocumentColumn):
            return next(spec for spec in COLUMN_SPECS if spec.key is column)
        return COLUMN_SPECS[column]

    @staticmethod
    def column_for(key: DocumentColumn) -> int:
        return next(index for index, spec in enumerate(COLUMN_SPECS) if spec.key is key)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMN_SPECS)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._records)):
            return None
        record = self._records[index.row()]
        spec = COLUMN_SPECS[index.column()]

        if role == int(Qt.ItemDataRole.DisplayRole):
            return spec.display_accessor(record)
        if role == int(Qt.ItemDataRole.TextAlignmentRole):
            alignment = direction_profile_for(spec.text_kind).alignment | Qt.AlignmentFlag.AlignVCenter
            return int(alignment)
        if role == int(Qt.ItemDataRole.ToolTipRole):
            if spec.key is DocumentColumn.DOCUMENT:
                return record.local_path or record.file_name
            if spec.key is DocumentColumn.ATTENTION:
                return record.attention_text or None
        if role == DocumentRoles.SORT:
            return spec.sort_accessor(record)
        if role == DocumentRoles.RAW_VALUE:
            return spec.raw_accessor(record)
        if role == DocumentRoles.DOCUMENT_ID:
            return record.document_id
        if role == DocumentRoles.RECORD_ID:
            return record.record_id
        if role == DocumentRoles.RAW_STATUS:
            return record.status
        if role == DocumentRoles.STATUS_LABEL:
            return record.status_label
        if role == DocumentRoles.STATUS_CATEGORY:
            return record.status_category.value
        if role == DocumentRoles.QUEUE_ROUTE:
            return route_for(record).value
        if role == DocumentRoles.DUPLICATE_SUSPECTED:
            return record.is_duplicate_suspected
        if role == DocumentRoles.MANUALLY_CORRECTED:
            return record.was_manually_corrected
        if role == DocumentRoles.ATTENTION_REASON:
            return record.attention_reason.value
        if role == DocumentRoles.COLUMN_KEY:
            return spec.key.value
        if role == DocumentRoles.TEXT_KIND:
            return spec.text_kind.value
        if role == DocumentRoles.PRESENTATION_RECORD:
            return record
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object:
        if orientation is Qt.Orientation.Horizontal and 0 <= section < len(COLUMN_SPECS):
            if role == int(Qt.ItemDataRole.DisplayRole):
                return COLUMN_SPECS[section].header_he
            if role == int(Qt.ItemDataRole.TextAlignmentRole):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if role == int(Qt.ItemDataRole.SizeHintRole):
                from PySide6.QtCore import QSize

                return QSize(COLUMN_SPECS[section].width_hint, CONTROLS.table_header_height)
        if orientation is Qt.Orientation.Vertical and role == int(Qt.ItemDataRole.DisplayRole):
            return section + 1
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def roleNames(self) -> dict[int, bytes]:
        names = dict(super().roleNames())
        for role in DocumentRoles:
            names[int(role)] = role.name.lower().encode("ascii")
        return names

    def records(self) -> tuple[DocumentPresentationRecord, ...]:
        return tuple(self._records)

    def record_at(self, row: int) -> DocumentPresentationRecord | None:
        return self._records[row] if 0 <= row < len(self._records) else None

    def document_id_at(self, row: int) -> str | None:
        record = self.record_at(row)
        return record.document_id if record is not None else None

    def row_for_document_id(self, document_id: str) -> int | None:
        return self._rows_by_id.get(document_id)

    def index_for_document_id(self, document_id: str, column: int = 0) -> QModelIndex:
        row = self._rows_by_id.get(document_id)
        return QModelIndex() if row is None else self.index(row, column)

    def replace_documents(
        self, documents: Iterable[Document | DocumentPresentationRecord]
    ) -> None:
        records = [self._record(document) for document in documents]
        ids = [record.document_id for record in records]
        if len(ids) != len(set(ids)):
            raise ValueError("Document queue contains duplicate drive_file_id values")
        self.beginResetModel()
        self._records = records
        self._reindex()
        self.endResetModel()

    def insert_document(
        self,
        document: Document | DocumentPresentationRecord,
        row: int | None = None,
    ) -> int:
        record = self._record(document)
        existing = self._rows_by_id.get(record.document_id)
        if existing is not None:
            self.update_document(record)
            return existing
        target = len(self._records) if row is None else max(0, min(row, len(self._records)))
        self.beginInsertRows(QModelIndex(), target, target)
        self._records.insert(target, record)
        self._reindex()
        self.endInsertRows()
        return target

    def update_document(self, document: Document | DocumentPresentationRecord) -> bool:
        record = self._record(document)
        row = self._rows_by_id.get(record.document_id)
        if row is None:
            return False
        if self._records[row] == record:
            return True
        self._records[row] = record
        self.dataChanged.emit(
            self.index(row, 0),
            self.index(row, len(COLUMN_SPECS) - 1),
            [int(Qt.ItemDataRole.DisplayRole), *[int(role) for role in DocumentRoles]],
        )
        return True

    def refresh_documents(
        self, documents: Iterable[Document | DocumentPresentationRecord]
    ) -> None:
        for document in documents:
            record = self._record(document)
            if not self.update_document(record):
                self.insert_document(record)

    def remove_document(self, document_id: str) -> bool:
        row = self._rows_by_id.get(document_id)
        if row is None:
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._records[row]
        self._reindex()
        self.endRemoveRows()
        return True

    def _reindex(self) -> None:
        self._rows_by_id = {
            record.document_id: row for row, record in enumerate(self._records)
        }
