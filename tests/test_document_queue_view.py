from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.models.document import Document
from app.ui.models import AttentionSegment, DocumentColumn, DocumentTableModel, QueueRoute
from app.ui.views.document_queue import DocumentQueueView, QueueAttentionDelegate


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def doc(document_id: str, status: str, **overrides) -> Document:
    values = {
        "drive_file_id": document_id,
        "id": f"record-{document_id}",
        "file_name": f"{document_id}.pdf",
        "folder_path": "Drive / 2026",
        "status": status,
        "supplier_name": "ספק בדיקה",
        "invoice_number": f"INV-{document_id}",
        "invoice_date": "01/08/2026",
        "total": 100,
        "confidence": 0.75,
    }
    values.update(overrides)
    return Document(**values)


def mixed() -> list[Document]:
    return [
        doc("new-a", "new", file_name="Alpha.pdf", total=20),
        doc("new-b", "new", supplier_name="חשמל ישראל", total=3),
        doc("review", "needs_review"),
        doc("failed", "failed", error_message="bad pdf"),
        doc("skipped", "skipped"),
        doc("duplicate", "processed", is_duplicate_suspected=True),
        doc("ready", "processed"),
    ]


def test_inbox_binds_shared_model_and_route_proxy(qapp) -> None:
    model = DocumentTableModel(mixed())
    view = DocumentQueueView(model, QueueRoute.INBOX)

    assert view.table.model() is view.proxy_model
    assert view.proxy_model.sourceModel() is model
    assert view.proxy_model.rowCount() == 2
    assert view.count_label.text() == "2"
    assert view.process_button is not None


def test_inbox_search_uses_phase_d_proxy_fields(qapp) -> None:
    view = DocumentQueueView(DocumentTableModel(mixed()), QueueRoute.INBOX)

    view.search_field.setText("alpha")
    assert view.proxy_model.rowCount() == 1
    view.search_field.setText("חשמל")
    assert view.proxy_model.rowCount() == 1
    view.search_field.setText("INV-NOPE")
    assert view.proxy_model.rowCount() == 0
    assert "אין תוצאות" in view.empty_state.description_label.text()


@pytest.mark.parametrize(
    ("segment", "expected_id"),
    (
        (AttentionSegment.NEEDS_REVIEW, "review"),
        (AttentionSegment.FAILED, "failed"),
        (AttentionSegment.SKIPPED, "skipped"),
        (AttentionSegment.SUSPECTED_DUPLICATE, "duplicate"),
    ),
)
def test_attention_segments_use_overlapping_shared_policy(qapp, segment, expected_id) -> None:
    view = DocumentQueueView(DocumentTableModel(mixed()), QueueRoute.ATTENTION)
    view.set_attention_segment(segment)

    assert view.proxy_model.rowCount() == 1
    assert view.proxy_model.document_id_for_index(view.proxy_model.index(0, 0)) == expected_id
    assert view.segment_buttons[segment].isChecked()


def test_duplicate_and_needs_review_overlap_without_mutating_status(qapp) -> None:
    document = doc("overlap", "needs_review", is_duplicate_suspected=True)
    view = DocumentQueueView(DocumentTableModel([document]), QueueRoute.ATTENTION)

    view.set_attention_segment(AttentionSegment.NEEDS_REVIEW)
    assert view.proxy_model.rowCount() == 1
    view.set_attention_segment(AttentionSegment.SUSPECTED_DUPLICATE)
    assert view.proxy_model.rowCount() == 1
    assert document.status == "needs_review"


def test_typed_sorting_is_delegated_to_phase_d_proxy(qapp) -> None:
    view = DocumentQueueView(DocumentTableModel(mixed()), QueueRoute.INBOX)
    total_column = DocumentTableModel.column_for(DocumentColumn.TOTAL)

    view.proxy_model.sort(total_column, Qt.SortOrder.AscendingOrder)

    ids = [
        view.proxy_model.document_id_for_index(view.proxy_model.index(row, 0))
        for row in range(view.proxy_model.rowCount())
    ]
    assert ids == ["new-b", "new-a"]


def test_selection_uses_stable_ids_and_survives_update_and_sort(qapp) -> None:
    model = DocumentTableModel(mixed())
    view = DocumentQueueView(model, QueueRoute.INBOX)
    selected = view.proxy_model.index_for_document_id("new-a", 0)
    view.table.selectRow(selected.row())

    model.update_document(doc("new-a", "new", file_name="Zulu.pdf", total=999))
    view.proxy_model.sort(0, Qt.SortOrder.AscendingOrder)
    view.restore_selected_document_ids(("new-a",))

    assert view.selected_document_ids == ("new-a",)


def test_route_movement_removes_updated_document_from_inbox(qapp) -> None:
    model = DocumentTableModel([doc("moving", "new")])
    view = DocumentQueueView(model, QueueRoute.INBOX)

    model.update_document(doc("moving", "needs_review"))

    assert view.proxy_model.rowCount() == 0
    assert view.content_stack.currentWidget() is view.empty_state


def test_empty_inbox_scan_and_process_actions_emit_only_intent(qapp) -> None:
    view = DocumentQueueView(DocumentTableModel(), QueueRoute.INBOX)
    scan = QSignalSpy(view.scanRequested)
    process = QSignalSpy(view.processRequested)

    view.empty_state.action_button.click()
    view.process_button.click()

    assert scan.count() == 1
    assert process.count() == 1


def test_workspace_action_is_explicitly_deferred_and_selection_only(qapp) -> None:
    view = DocumentQueueView(DocumentTableModel(mixed()), QueueRoute.ATTENTION)
    assert view.workspace_button.isEnabled() is False
    assert "בשלב הבא" in view.workspace_button.text()


def test_attention_delegate_exposes_duplicate_and_manual_indicators(qapp) -> None:
    model = DocumentTableModel(
        [doc("flagged", "needs_review", is_duplicate_suspected=True, was_manually_corrected=True)]
    )
    view = DocumentQueueView(model, QueueRoute.ATTENTION)
    column = DocumentTableModel.column_for(DocumentColumn.ATTENTION)
    index = view.proxy_model.index(0, column)

    assert QueueAttentionDelegate.indicator_labels(index) == (
        "חשד לכפילות",
        "תוקן ידנית",
    )


def test_source_folder_context_is_visible(qapp) -> None:
    view = DocumentQueueView(DocumentTableModel(mixed()), QueueRoute.INBOX)
    source_column = DocumentTableModel.column_for(DocumentColumn.SOURCE)
    assert view.table.isColumnHidden(source_column) is False
