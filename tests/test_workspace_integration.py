from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from app.application.task_manager import TaskAccess, TaskManager, TaskType
from app.models.document import Document
from app.ui.models import AttentionSegment, DocumentColumn, DocumentTableModel
from app.ui.models.workspace_queue_model import WorkspaceQueueModel
from app.ui.routes import AppRoute
from app.ui.shell import PandaMainWindow
from app.ui.theme.tokens import LAYOUT
from app.ui.workspace import WorkspaceView


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def doc(document_id: str, status: str = "needs_review", **overrides) -> Document:
    values = {
        "drive_file_id": document_id,
        "id": f"record-{document_id}",
        "file_name": f"{document_id}.pdf",
        "folder_path": "Drive / 2026",
        "status": status,
        "supplier_name": f"Supplier {document_id}",
        "invoice_number": f"INV-{document_id}",
        "invoice_date": "24/08/2026",
        "total": 117,
        "confidence": 0.62,
    }
    values.update(overrides)
    return Document(**values)


class ReadOnlySource:
    def __init__(self, documents) -> None:
        self.documents = list(documents)
        self.write_calls = 0

    def all(self) -> list[Document]:
        return list(self.documents)

    def get_by_drive_id(self, document_id: str) -> Document | None:
        return next(
            (item for item in self.documents if item.drive_file_id == document_id), None
        )

    def upsert(self, _document) -> None:
        self.write_calls += 1
        raise AssertionError("read-only Workspace cannot persist")


class ManualRunner:
    def start(self, reporter) -> None:
        self.reporter = reporter

    def request_cancel(self) -> bool:
        return False


def attention_documents() -> list[Document]:
    return [
        doc("review-a", supplier_name="Alpha"),
        doc("review-b", supplier_name="Beta"),
        doc("failed", status="failed", error_message="Synthetic failure"),
        doc("duplicate", status="processed", is_duplicate_suspected=True),
    ]


def open_attention_workspace(shell: PandaMainWindow, document_id: str = "review-a"):
    shell.navigate(AppRoute.ATTENTION)
    view = shell.attention
    view.restore_selected_document_ids((document_id,))
    view.workspace_button.click()
    return view


def test_workspace_queue_model_starts_explicit_session_at_stable_id() -> None:
    model = WorkspaceQueueModel(["old"])
    changed = QSignalSpy(model.currentChanged)

    model.start_session(["one", "two", "three"], "two")

    assert model.document_ids == ("one", "two", "three")
    assert model.current_document_id == "two"
    assert (model.position, model.total) == (2, 3)
    assert changed.count() == 1
    with pytest.raises(ValueError):
        model.start_session(["one"], "missing")


def test_queue_opens_workspace_with_filtered_visible_identity(qapp) -> None:
    source = ReadOnlySource(attention_documents())
    shell = PandaMainWindow(source, operational_enabled=False)
    shell.attention.search_field.setText("review")

    view = open_attention_workspace(shell, "review-a")

    assert shell.workspace_active is True
    assert shell.workspace.origin_route == AppRoute.ATTENTION.value
    assert shell.workspace.queue_model.document_ids == view.ordered_visible_document_ids
    assert shell.workspace.current_document_id == "review-a"
    assert shell.navigation.button_for(AppRoute.ATTENTION).is_active
    assert source.write_calls == 0


def test_attention_segment_defines_workspace_previous_next_queue(qapp) -> None:
    documents = attention_documents() + [
        doc("duplicate-2", status="new", is_duplicate_suspected=True)
    ]
    shell = PandaMainWindow(ReadOnlySource(documents), operational_enabled=False)
    shell.navigate(AppRoute.ATTENTION)
    shell.attention.set_attention_segment(AttentionSegment.SUSPECTED_DUPLICATE)
    visible = shell.attention.ordered_visible_document_ids

    assert shell.open_workspace(visible[0], visible, AppRoute.ATTENTION.value)
    shell.workspace.queue_model.next()

    assert shell.workspace.current_document_id == visible[1]
    assert shell.workspace.header.position_label.text().strip("\u2066\u2069") == "2 / 2"


def test_queue_item_activation_navigates_without_visual_row_identity(qapp) -> None:
    documents = attention_documents()
    mapping = {item.drive_file_id: item for item in documents}
    workspace = WorkspaceView(mapping.get)
    workspace.open_session(
        origin_route="attention",
        origin_label="דורש טיפול",
        ordered_document_ids=("review-a", "review-b"),
        current_document_id="review-a",
    )

    workspace.queue_rail.list_view.activated.emit(workspace.queue_model.index(1, 0))

    assert workspace.current_document_id == "review-b"
    assert workspace.header.file_name.text() == "review-b.pdf"


def test_back_restores_search_segment_sort_and_current_document(qapp) -> None:
    source = ReadOnlySource(attention_documents())
    shell = PandaMainWindow(source, operational_enabled=False)
    shell.navigate(AppRoute.ATTENTION)
    view = shell.attention
    view.search_field.setText("review")
    view.set_attention_segment(AttentionSegment.NEEDS_REVIEW)
    supplier_column = DocumentTableModel.column_for(DocumentColumn.SUPPLIER)
    view.table.sortByColumn(supplier_column, Qt.SortOrder.DescendingOrder)
    selected_id = view.ordered_visible_document_ids[0]
    assert shell.open_workspace(
        selected_id, view.ordered_visible_document_ids, AppRoute.ATTENTION.value
    )

    shell.workspace.return_to_queue()

    assert shell.workspace_active is False
    assert shell.current_route is AppRoute.ATTENTION
    assert view.search_field.text() == "review"
    assert view.proxy_model.attention_segment is AttentionSegment.NEEDS_REVIEW
    assert view.table.horizontalHeader().sortIndicatorSection() == supplier_column
    assert view.selected_document_ids == (selected_id,)
    assert source.write_calls == 0


def test_back_preserves_multi_selection_while_focusing_opened_document(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource(attention_documents()), operational_enabled=False)
    shell.navigate(AppRoute.ATTENTION)
    view = shell.attention
    view.restore_selected_document_ids(("review-a", "review-b"))

    assert shell.open_workspace(
        "review-a", view.ordered_visible_document_ids, AppRoute.ATTENTION.value
    )
    shell.workspace.return_to_queue()

    assert set(view.selected_document_ids) == {"review-a", "review-b"}
    assert view.proxy_model.document_id_for_index(view.table.currentIndex()) == "review-a"


def test_escape_returns_to_originating_queue(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource(attention_documents()), operational_enabled=False)
    shell.show()
    open_attention_workspace(shell)
    shell.workspace.setFocus()
    qapp.processEvents()

    QTest.keyClick(shell.workspace, Qt.Key.Key_Escape)

    assert shell.workspace_active is False
    assert shell.current_route is AppRoute.ATTENTION
    shell.close()


def test_refresh_keeps_current_document_open_after_route_change(qapp) -> None:
    source = ReadOnlySource(attention_documents())
    shell = PandaMainWindow(source, operational_enabled=False)
    open_attention_workspace(shell, "review-a")
    current = source.get_by_drive_id("review-a")
    assert current is not None
    current.status = "processed"

    shell.refresh_document("review-a")

    assert shell.workspace_active is True
    assert shell.workspace.current_document_id == "review-a"
    assert shell.workspace.header.status_badge.status == "processed"


def test_refresh_removes_missing_current_and_uses_nearest_available(qapp) -> None:
    source = ReadOnlySource(attention_documents())
    shell = PandaMainWindow(source, operational_enabled=False)
    open_attention_workspace(shell, "review-a")
    source.documents = [item for item in source.documents if item.drive_file_id != "review-a"]

    shell.refresh()

    assert shell.workspace_active is True
    assert shell.workspace.current_document_id != "review-a"
    assert shell.workspace.current_document_id in shell.workspace.queue_model.document_ids


def test_workspace_remains_nonmodal_and_task_model_updates(qapp) -> None:
    manager = TaskManager()
    shell = PandaMainWindow(
        ReadOnlySource(attention_documents()),
        task_manager=manager,
        operational_enabled=False,
    )
    open_attention_workspace(shell)
    runner = ManualRunner()
    task_id = manager.submit(
        task_type=TaskType.DEVELOPMENT,
        title="Synthetic read-only task",
        runner=runner,
        access=TaskAccess.READ_ONLY,
    )
    runner.reporter.progress(current=1, total=3, message="working")
    qapp.processEvents()

    assert shell.workspace_active is True
    assert shell.task_model.rowCount() == 1
    assert manager.task(task_id).message == "working"
    assert shell.navigation.task_dock.isVisibleTo(shell.navigation)


@pytest.mark.parametrize(
    ("size", "queue_width", "review_width"),
    (
        ((1100, 680), LAYOUT.workspace_queue_minimum_width, LAYOUT.workspace_fields_minimum_width),
        ((1440, 900), LAYOUT.workspace_queue_width, LAYOUT.workspace_fields_width),
    ),
)
def test_workspace_regions_survive_supported_shell_sizes(
    qapp, size, queue_width, review_width
) -> None:
    shell = PandaMainWindow(ReadOnlySource(attention_documents()), operational_enabled=False)
    shell.resize(*size)
    open_attention_workspace(shell)
    shell.show()
    qapp.processEvents()

    assert shell.workspace.queue_rail.isVisible()
    assert shell.workspace.source_preview.isVisible()
    assert shell.workspace.review_panel.isVisible()
    assert shell.workspace.queue_rail.width() == queue_width
    assert shell.workspace.review_panel.width() == review_width
    assert shell.workspace.window().isModal() is False
    shell.close()
