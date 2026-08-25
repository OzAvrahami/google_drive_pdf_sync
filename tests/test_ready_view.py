from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.application.approval_service import ApprovalService
from app.domain.validation import ValidationRules
from app.models.document import Document
from app.ui.models import DocumentColumn, DocumentTableModel, ReadySegment
from app.ui.views.ready import ReadyView


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    application = QApplication.instance() or QApplication([])
    existing_widgets = set(application.topLevelWidgets())
    yield application
    for widget in set(application.topLevelWidgets()) - existing_widgets:
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()


def doc(document_id: str, status: str = "processed", **overrides) -> Document:
    values = dict(
        drive_file_id=document_id,
        file_name=f"{document_id}.pdf",
        folder_path="Drive / 2026",
        status=status,
        supplier_name="ספק בדיקה",
        invoice_number=f"INV-{document_id}",
        invoice_date="25/08/2026",
        total=100.0,
        confidence=0.9,
    )
    values.update(overrides)
    return Document(**values)


class Repository:
    def __init__(self, *documents: Document) -> None:
        self.documents = {item.drive_file_id: item for item in documents}
        self.upsert_many_calls: list[list[Document]] = []

    def all(self):
        return list(self.documents.values())

    def get_by_drive_id(self, document_id):
        return self.documents.get(document_id)

    def upsert(self, item):
        self.documents[item.drive_file_id] = item

    def upsert_many(self, items):
        self.upsert_many_calls.append(items)
        for item in items:
            self.documents[item.drive_file_id] = item


def build_view(*documents, rules=None, confirmer=lambda _ids: True):
    repository = Repository(*documents)
    model = DocumentTableModel(documents)
    service = ApprovalService(repository, validation_rules=rules)
    view = ReadyView(
        model,
        service,
        workbook_path="C:/synthetic/invoices.xlsx",
        confirm_export=confirmer,
    )
    return view, model, repository


def test_ready_route_contains_only_processed_and_approved(qapp) -> None:
    view, _, _ = build_view(doc("processed"), doc("approved", "approved"), doc("new", "new"))
    assert view.ordered_visible_document_ids == ("processed", "approved")
    assert view.count_label.text() == "2"


@pytest.mark.parametrize(
    "segment, expected",
    [
        (ReadySegment.ALL, {"processed", "approved", "manual"}),
        (ReadySegment.READY_TO_APPROVE, {"processed", "manual"}),
        (ReadySegment.READY_TO_EXPORT, {"approved"}),
    ],
)
def test_ready_segments_are_derived_not_persisted(qapp, segment, expected) -> None:
    view, _, _ = build_view(
        doc("processed"),
        doc("approved", "approved"),
        doc("manual", was_manually_corrected=True),
    )
    view.set_ready_segment(segment)
    assert set(view.ordered_visible_document_ids) == expected


def test_manual_correction_filter_intersects_ready_segment(qapp) -> None:
    view, _, _ = build_view(
        doc("processed"),
        doc("manual", was_manually_corrected=True),
        doc("approved-manual", "approved", was_manually_corrected=True),
    )
    view.set_ready_segment(ReadySegment.READY_TO_APPROVE)
    view.set_manually_corrected_only(True)
    assert view.ordered_visible_document_ids == ("manual",)


def test_search_and_typed_sorting_reuse_phase_d_proxy(qapp) -> None:
    view, _, _ = build_view(
        doc("large", supplier_name="Alpha", total=500.0),
        doc("small", supplier_name="ספק ירושלים", total=20.0),
    )
    view.search_field.setText("ירושלים")
    assert view.ordered_visible_document_ids == ("small",)
    view.search_field.clear()
    total_column = DocumentTableModel.column_for(DocumentColumn.TOTAL)
    view.table.sortByColumn(total_column, Qt.SortOrder.AscendingOrder)
    assert view.ordered_visible_document_ids == ("small", "large")


def test_mixed_selection_scopes_approval_and_export_separately(qapp) -> None:
    view, _, _ = build_view(doc("processed"), doc("approved", "approved"))
    view.restore_selected_document_ids(("processed", "approved"))
    assert "1 לאישור" in view.selection_label.text()
    assert "1 לייצוא" in view.selection_label.text()
    assert view.approve_button.isEnabled()
    assert view.export_button.isEnabled()


def test_stale_ineligible_selection_is_reloaded_and_reported(qapp) -> None:
    view, _, repository = build_view(doc("valid"), doc("stale"))
    repository.documents["stale"].status = "failed"
    view.restore_selected_document_ids(("valid", "stale"))

    assert "1 לא זמינים" in view.selection_label.text()
    view.approve_selected()

    assert repository.documents["valid"].status == "approved"
    assert repository.documents["stale"].status == "failed"
    assert view.feedback_widget is not None
    assert "1 מסמכים לא היו זמינים" in view.feedback_widget.accessibleName()


def test_validation_blocker_prevents_every_batch_approval_write(qapp) -> None:
    rules = ValidationRules(required_fields=frozenset({"invoice_number"}))
    view, _, repository = build_view(
        doc("valid"), doc("blocked", invoice_number=None), rules=rules
    )
    view.restore_selected_document_ids(("valid", "blocked"))

    assert view.approve_button.isEnabled() is False
    assert view.show_blockers_button.isVisible() is False  # parent view is not shown
    assert view.show_blockers_button.isHidden() is False
    view.approve_selected()
    assert repository.upsert_many_calls == []
    assert repository.documents["valid"].status == "processed"


def test_show_blockers_focuses_only_blocking_stable_ids(qapp) -> None:
    rules = ValidationRules(required_fields=frozenset({"invoice_number"}))
    view, _, _ = build_view(
        doc("valid"), doc("blocked", invoice_number=None), rules=rules
    )
    view.restore_selected_document_ids(("valid", "blocked"))
    view.show_blockers()
    assert view.selected_document_ids == ("blocked",)


def test_successful_batch_approval_uses_one_bulk_write_and_emits_ids(qapp) -> None:
    view, _, repository = build_view(doc("one"), doc("two"))
    approved = QSignalSpy(view.batchApproved)
    view.restore_selected_document_ids(("one", "two"))
    view.approve_selected()

    assert len(repository.upsert_many_calls) == 1
    assert [item.status for item in repository.upsert_many_calls[0]] == [
        "approved",
        "approved",
    ]
    assert approved.count() == 1


def test_selected_export_emits_only_reloaded_already_approved_ids(qapp) -> None:
    confirmations = []
    view, _, _ = build_view(
        doc("processed"),
        doc("approved", "approved"),
        confirmer=lambda ids: confirmations.append(ids) or True,
    )
    requested = QSignalSpy(view.exportRequested)
    view.restore_selected_document_ids(("processed", "approved"))
    view.request_selected_export()

    assert confirmations == [("approved",)]
    assert requested.count() == 1
    assert tuple(requested.at(0)[0]) == ("approved",)


def test_export_cancel_and_pending_state_never_submit(qapp) -> None:
    view, _, _ = build_view(
        doc("approved", "approved"), confirmer=lambda _ids: False
    )
    requested = QSignalSpy(view.exportRequested)
    view.restore_selected_document_ids(("approved",))
    view.request_selected_export()
    assert requested.count() == 0
    view.set_export_pending(True)
    assert view.export_button.isEnabled() is False


def test_stable_selection_survives_sort_and_visible_filter(qapp) -> None:
    view, model, _ = build_view(doc("one", total=10), doc("two", total=20))
    view.restore_selected_document_ids(("two",))
    view.table.sortByColumn(
        DocumentTableModel.column_for(DocumentColumn.TOTAL),
        Qt.SortOrder.DescendingOrder,
    )
    assert view.selected_document_ids == ("two",)
    model.update_document(doc("two", "approved", total=30))
    assert view.selected_document_ids == ("two",)


def test_empty_filtered_state_is_distinct(qapp) -> None:
    view, _, _ = build_view(doc("processed"))
    view.set_ready_segment(ReadySegment.READY_TO_EXPORT)
    assert view.content_stack.currentWidget() is view.empty_state
    assert view.empty_state.title_label.text() == "לא נמצאו תוצאות"
    assert "מסננים" in view.empty_state.description_label.text()
