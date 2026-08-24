"""Stable document-ID selection helpers for future queue views."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QItemSelectionModel, QModelIndex

from app.ui.models.document_filter_model import DocumentFilterProxyModel


def selected_document_ids(selection_model: QItemSelectionModel) -> list[str]:
    model = selection_model.model()
    ids: list[str] = []
    seen: set[str] = set()
    for index in sorted(selection_model.selectedRows(0), key=lambda item: item.row()):
        document_id = _document_id(model, index)
        if document_id is not None and document_id not in seen:
            seen.add(document_id)
            ids.append(document_id)
    return ids


def restore_selected_document_ids(
    selection_model: QItemSelectionModel,
    document_ids: Iterable[str],
    current_document_id: str | None = None,
) -> list[str]:
    model = selection_model.model()
    selection_model.clearSelection()
    restored: list[str] = []
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    for document_id in dict.fromkeys(document_ids):
        index = _index_for_id(model, document_id)
        if index.isValid():
            selection_model.select(index, flags)
            restored.append(document_id)
    current_id = current_document_id or (restored[0] if restored else None)
    if current_id is not None:
        current = _index_for_id(model, current_id)
        if current.isValid():
            selection_model.setCurrentIndex(current, QItemSelectionModel.SelectionFlag.NoUpdate)
    return restored


def _document_id(model: object, index: QModelIndex) -> str | None:
    getter = getattr(model, "document_id_for_index", None)
    if callable(getter):
        return getter(index)
    return None


def _index_for_id(model: object, document_id: str) -> QModelIndex:
    getter = getattr(model, "index_for_document_id", None)
    if callable(getter):
        return getter(document_id, 0)
    return QModelIndex()
