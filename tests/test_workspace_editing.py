from __future__ import annotations

import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from app.application.approval_service import ApprovalService
from app.application.document_review_service import DocumentReviewService
from app.application.workspace_approval_service import WorkspaceApprovalService
from app.domain.validation import ValidationRules
from app.models.document import Document
from app.ui.components import FieldPresentationState
from app.ui.models.queue_policy import QueueRoute
from app.ui.routes import AppRoute
from app.ui.shell import PandaMainWindow
from app.ui.workspace import WorkspaceView


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class MemorySource:
    def __init__(
        self,
        documents: list[Document],
        *,
        fail_on_write: int | None = None,
    ) -> None:
        self.documents = {item.drive_file_id: deepcopy(item) for item in documents}
        self.write_count = 0
        self.fail_on_write = fail_on_write

    def all(self) -> list[Document]:
        return [deepcopy(item) for item in self.documents.values()]

    def get_by_drive_id(self, document_id: str) -> Document | None:
        document = self.documents.get(document_id)
        return deepcopy(document) if document is not None else None

    def upsert(self, document: Document) -> None:
        self.write_count += 1
        if self.fail_on_write == self.write_count:
            raise OSError("synthetic write failure")
        stored = deepcopy(document)
        stored.touch()
        self.documents[stored.drive_file_id] = stored

    def upsert_many(self, documents) -> None:
        for document in documents:
            self.upsert(document)


def document(document_id: str = "one", status: str = "needs_review", **overrides) -> Document:
    values = {
        "drive_file_id": document_id,
        "id": f"record-{document_id}",
        "file_name": f"{document_id}.pdf",
        "folder_path": "Drive / 2026",
        "status": status,
        "confidence": 0.35,
        "supplier_name": "Original Supplier",
        "invoice_number": "INV-1",
        "invoice_date": "24/08/2026",
        "subtotal": 100.0,
        "vat": 17.0,
        "total": 117.0,
        "description": "Original description",
        "extracted_data": {
            "business_name": "Original Supplier",
            "invoice_number": "INV-1",
            "invoice_date": "24/08/2026",
            "amount": 117.0,
            "document_type": "חשבונית מס",
        },
    }
    values.update(overrides)
    return Document(**values)


def make_services(source: MemorySource, *, learning=None, rules=None):
    validation_rules = rules or ValidationRules()
    review = DocumentReviewService(
        source,
        validation_rules=validation_rules,
        learning_recorder=learning or (lambda **_kwargs: None),
    )
    approval = ApprovalService(source, validation_rules=validation_rules)
    combined = WorkspaceApprovalService(source, review, approval)
    return review, approval, combined


def make_workspace(
    documents: list[Document],
    *,
    learning=None,
    fail_on_write: int | None = None,
    discard=None,
    rules=None,
):
    source = MemorySource(documents, fail_on_write=fail_on_write)
    review, _approval, combined = make_services(source, learning=learning, rules=rules)
    workspace = WorkspaceView(
        source.get_by_drive_id,
        review_service=review,
        approval_executor=combined.approve_draft,
        discard_confirmation=discard,
    )
    ids = tuple(source.documents)
    workspace.open_session(
        origin_route="attention",
        origin_label="דורש טיפול",
        ordered_document_ids=ids,
        current_document_id=ids[0],
    )
    return source, workspace


@pytest.mark.parametrize(
    ("status", "editable"),
    (
        ("processed", True),
        ("needs_review", True),
        ("new", False),
        ("failed", False),
        ("skipped", False),
        ("approved", False),
        ("exported", False),
        ("confirmed_irrelevant", False),
        ("excluded", False),
    ),
)
def test_workspace_editability_comes_from_workflow_policy(qapp, status, editable) -> None:
    _source, workspace = make_workspace([document(status=status)])

    assert workspace.is_editable is editable
    assert bool(workspace.review_panel.field_editors) is editable
    assert workspace.review_panel.save_button.isVisible() is False  # parent is not shown
    assert workspace.review_panel.save_button.isHidden() is (not editable)


def test_draft_binding_preserves_existing_correction_provenance(qapp) -> None:
    _source, workspace = make_workspace(
        [
            document(
                corrected_data={"supplier_name": "Corrected Supplier"},
                was_manually_corrected=True,
            )
        ]
    )

    field = workspace.current_draft.field("supplier_name")
    editor = workspace.review_panel.field_editors["supplier_name"]

    assert field.extracted_value == "Original Supplier"
    assert field.persisted_corrected_value == "Corrected Supplier"
    assert field.has_existing_correction is True
    assert editor.editor.text() == "Corrected Supplier"
    assert editor.state is FieldPresentationState.CORRECTED


def test_edit_revert_and_multiple_fields_drive_dirty_state(qapp) -> None:
    _source, workspace = make_workspace([document()])
    supplier = workspace.review_panel.field_editors["supplier_name"].editor
    total = workspace.review_panel.field_editors["total"].editor

    supplier.setText("Changed Supplier")
    total.setText("118,50")
    assert workspace.is_dirty is True
    assert workspace.current_draft.changed_fields == frozenset({"supplier_name", "total"})
    assert workspace.header.dirty_indicator.isHidden() is False

    supplier.setText("Original Supplier")
    total.setText("117.0")
    assert workspace.is_dirty is False
    assert workspace.header.dirty_indicator.isHidden() is True


def test_noop_assignment_remains_clean(qapp) -> None:
    source, workspace = make_workspace([document()])
    workspace.review_panel.field_editors["description"].editor.setText(
        "Original description"
    )

    assert workspace.is_dirty is False
    assert workspace.review_panel.save_button.isEnabled() is False
    assert source.write_count == 0


@pytest.mark.parametrize(
    ("field_name", "value"),
    (("total", "not-a-number"), ("invoice_date", "2026-08-24")),
)
def test_invalid_input_stays_visible_and_blocks_save_and_approval(
    qapp, field_name, value
) -> None:
    source, workspace = make_workspace([document()])
    editor = workspace.review_panel.field_editors[field_name]

    editor.editor.setText(value)

    assert editor.editor.text() == value
    assert editor.state is FieldPresentationState.INVALID
    assert workspace.review_panel.save_button.isEnabled() is False
    assert workspace.review_panel.approve_button.isEnabled() is False
    assert source.write_count == 0


def test_missing_value_is_visual_but_not_globally_blocking(qapp) -> None:
    _source, workspace = make_workspace([document(supplier_name=None)])

    assert workspace.review_panel.field_editors["supplier_name"].state is FieldPresentationState.MISSING
    assert workspace.current_draft.validation_result.has_blocking_errors is False
    assert workspace.review_panel.approve_button.isEnabled() is True


def test_configured_required_missing_value_blocks_approval(qapp) -> None:
    rules = ValidationRules(required_fields=frozenset({"supplier_name"}))
    _source, workspace = make_workspace([document(supplier_name=None)], rules=rules)

    assert workspace.current_draft.validation_result.has_blocking_errors is True
    assert workspace.review_panel.approve_button.isEnabled() is False


def test_low_document_confidence_does_not_block_valid_draft(qapp) -> None:
    _source, workspace = make_workspace([document(confidence=0.03)])

    assert workspace.header.confidence.text() == "3%"
    assert workspace.review_panel.approve_button.isEnabled() is True


def test_explicit_clear_is_retained_but_save_and_approval_are_disabled(qapp) -> None:
    source, workspace = make_workspace([document()])
    editor = workspace.review_panel.field_editors["supplier_name"]

    editor.editor.clear()

    assert workspace.current_draft.explicitly_cleared_fields == frozenset({"supplier_name"})
    assert workspace.is_dirty is True
    assert editor.state is FieldPresentationState.INVALID
    assert "אינה נתמכת" in editor.helper.text()
    assert workspace.review_panel.save_button.isEnabled() is False
    assert workspace.review_panel.approve_button.isEnabled() is False
    assert source.write_count == 0


def test_successful_save_persists_correction_learning_and_resets_dirty(qapp) -> None:
    learning_calls: list[dict] = []
    source, workspace = make_workspace(
        [document()], learning=lambda **kwargs: learning_calls.append(kwargs)
    )
    workspace.review_panel.field_editors["supplier_name"].editor.setText("Saved Supplier")

    assert workspace.save_current_draft() is True

    stored = source.get_by_drive_id("one")
    assert stored.corrected_data["supplier_name"] == "Saved Supplier"
    assert stored.was_manually_corrected is True
    assert stored.status == "needs_review"
    assert workspace.is_dirty is False
    assert source.write_count == 1
    assert learning_calls[0]["corrected_value"] == "Saved Supplier"
    assert workspace.review_panel.feedback.property("variant") == "success"


def test_ctrl_s_shortcut_uses_guarded_workspace_save(qapp) -> None:
    source, workspace = make_workspace([document()])
    workspace.review_panel.field_editors["description"].editor.setText("Updated safely")

    workspace.save_shortcut.activated.emit()

    assert source.write_count == 1
    assert source.get_by_drive_id("one").corrected_data["description"] == "Updated safely"
    assert workspace.is_dirty is False


def test_learning_failure_is_secondary_after_successful_save(qapp) -> None:
    def fail_learning(**_kwargs):
        raise RuntimeError("synthetic learning failure")

    source, workspace = make_workspace([document()], learning=fail_learning)
    workspace.review_panel.field_editors["supplier_name"].editor.setText("Saved")

    assert workspace.save_current_draft() is True
    assert source.get_by_drive_id("one").corrected_data["supplier_name"] == "Saved"
    assert workspace.review_panel.feedback.property("variant") == "warning"


def test_persistence_failure_preserves_dirty_draft(qapp) -> None:
    source, workspace = make_workspace([document()], fail_on_write=1)
    workspace.review_panel.field_editors["description"].editor.setText("Unsaved")

    assert workspace.save_current_draft() is False
    assert workspace.is_dirty is True
    assert source.get_by_drive_id("one").corrected_data == {}
    assert workspace.review_panel.feedback.property("variant") == "error"


def test_clean_save_is_noop_without_write_or_learning(qapp) -> None:
    calls: list[dict] = []
    source, workspace = make_workspace(
        [document()], learning=lambda **kwargs: calls.append(kwargs)
    )

    assert workspace.save_current_draft() is True
    assert source.write_count == 0
    assert calls == []


@pytest.mark.parametrize("status", ("processed", "needs_review"))
def test_valid_single_approval_makes_workspace_read_only(qapp, status) -> None:
    source, workspace = make_workspace([document(status=status)])

    assert workspace.approve_current_draft() is True

    assert source.get_by_drive_id("one").status == "approved"
    assert workspace.header.status_badge.status == "approved"
    assert workspace.is_editable is False
    assert workspace.current_draft is None
    assert workspace.review_panel.field_editors == {}
    assert workspace.review_panel.feedback.property("variant") == "success"


def test_dirty_approval_saves_correction_then_approves(qapp) -> None:
    source, workspace = make_workspace([document(status="processed")])
    workspace.review_panel.field_editors["total"].editor.setText("118,50")

    assert workspace.approve_current_draft() is True

    stored = source.get_by_drive_id("one")
    assert stored.corrected_data["total"] == 118.5
    assert stored.status == "approved"
    assert source.write_count == 2


def test_save_success_approval_failure_keeps_correction_and_editable_status(qapp) -> None:
    source, workspace = make_workspace([document(status="processed")], fail_on_write=2)
    workspace.review_panel.field_editors["description"].editor.setText("Saved first")

    assert workspace.approve_current_draft() is False

    stored = source.get_by_drive_id("one")
    assert stored.corrected_data["description"] == "Saved first"
    assert stored.status == "processed"
    assert workspace.is_dirty is False
    assert workspace.is_editable is True
    assert workspace.review_panel.feedback.property("variant") == "error"


def test_dirty_queue_click_requires_discard_confirmation(qapp) -> None:
    decisions = [False, True]
    source, workspace = make_workspace(
        [document("one"), document("two")],
        discard=lambda _reason: decisions.pop(0),
    )
    workspace.review_panel.field_editors["description"].editor.setText("Draft")

    workspace.queue_rail.documentRequested.emit("two")
    assert workspace.current_document_id == "one"
    assert workspace.is_dirty is True

    workspace.queue_rail.documentRequested.emit("two")
    assert workspace.current_document_id == "two"
    assert workspace.is_dirty is False
    assert source.write_count == 0


@pytest.mark.parametrize(
    ("current_id", "button_name", "destination"),
    (("one", "next_button", "two"), ("two", "previous_button", "one")),
)
def test_dirty_previous_and_next_buttons_do_not_discard_without_confirmation(
    qapp, current_id, button_name, destination
) -> None:
    decisions = [False, True]
    source = MemorySource([document("one"), document("two")])
    review, _approval, combined = make_services(source)
    workspace = WorkspaceView(
        source.get_by_drive_id,
        review_service=review,
        approval_executor=combined.approve_draft,
        discard_confirmation=lambda _reason: decisions.pop(0),
    )
    workspace.open_session(
        origin_route="attention",
        origin_label="דורש טיפול",
        ordered_document_ids=("one", "two"),
        current_document_id=current_id,
    )
    workspace.review_panel.field_editors["description"].editor.setText("Draft")

    button = getattr(workspace.header, button_name)
    button.click()
    assert workspace.current_document_id == current_id
    assert workspace.is_dirty is True
    button.click()
    assert workspace.current_document_id == destination
    assert workspace.is_dirty is False


def test_dirty_back_stays_or_discards_consistently(qapp) -> None:
    decisions = [False, True]
    _source, workspace = make_workspace(
        [document()], discard=lambda _reason: decisions.pop(0)
    )
    emitted: list[tuple[str, str]] = []
    workspace.backRequested.connect(lambda route, doc_id: emitted.append((route, doc_id)))
    workspace.review_panel.field_editors["description"].editor.setText("Draft")

    workspace.return_to_queue()
    assert emitted == []
    assert workspace.is_dirty is True
    workspace.return_to_queue()
    assert emitted == [("attention", "one")]


def test_clean_background_refresh_reloads_but_dirty_refresh_preserves_draft(qapp) -> None:
    source, workspace = make_workspace([document()])
    changed = source.documents["one"]
    changed.corrected_data["supplier_name"] = "Background Supplier"
    changed.touch()

    workspace.reconcile_queue(("one",), ("one",), changed_document_id="one")
    assert workspace.current_draft.current_value("supplier_name") == "Background Supplier"

    workspace.review_panel.field_editors["description"].editor.setText("Local Draft")
    changed = source.documents["one"]
    changed.status = "approved"
    changed.touch()
    workspace.reconcile_queue((), ("one",), changed_document_id="one")

    assert workspace.current_draft.current_value("description") == "Local Draft"
    assert workspace.is_dirty is True
    assert workspace.background_changed is True
    assert workspace.save_current_draft() is False
    assert source.write_count == 0


def test_shell_route_and_close_protect_dirty_workspace(qapp) -> None:
    source = MemorySource([document()])
    review, approval, combined = make_services(source)
    shell = PandaMainWindow(
        source,
        operational_enabled=False,
        document_review_service=review,
        approval_service=approval,
        workspace_approval_service=combined,
    )
    shell.navigate(AppRoute.ATTENTION)
    assert shell.open_workspace("one", ("one",), AppRoute.ATTENTION.value)
    shell.workspace.review_panel.field_editors["description"].editor.setText("Draft")
    shell.workspace.set_discard_confirmation(lambda _reason: False)

    assert shell.navigate(AppRoute.OVERVIEW) is False
    assert shell.workspace_active is True
    event = QCloseEvent()
    shell.closeEvent(event)
    assert event.isAccepted() is False

    shell.workspace.set_discard_confirmation(lambda _reason: True)
    assert shell.navigate(AppRoute.OVERVIEW) is True
    shell.close()


def test_needs_review_approval_refreshes_counts_and_keeps_origin_state(qapp) -> None:
    source = MemorySource([document()])
    review, approval, combined = make_services(source)
    shell = PandaMainWindow(
        source,
        operational_enabled=False,
        document_review_service=review,
        approval_service=approval,
        workspace_approval_service=combined,
    )
    shell.navigate(AppRoute.ATTENTION)
    shell.attention.search_field.setText("one")
    assert shell.open_workspace("one", ("one",), AppRoute.ATTENTION.value)

    assert shell.workspace.approve_current_draft() is True

    assert shell.workspace_active is True
    assert shell.workspace.current_document_id == "one"
    assert shell.workspace.queue_model.document_ids == ()
    assert shell._counts.for_route(QueueRoute.ATTENTION) == 0
    assert shell._counts.for_route(QueueRoute.READY) == 1
    assert shell._counts.ready_breakdown.ready_to_export == 1
    shell.workspace.return_to_queue()
    assert shell.attention.search_field.text() == "one"
    shell.close()


def test_processed_approval_changes_ready_segment_without_changing_ready_total(qapp) -> None:
    from app.ui.models.queue_policy import calculate_queue_counts

    source, workspace = make_workspace([document(status="processed")])
    before = calculate_queue_counts(source.all())

    assert workspace.approve_current_draft() is True
    after = calculate_queue_counts(source.all())

    assert before.ready == after.ready == 1
    assert before.ready_breakdown.ready_to_approve == 1
    assert before.ready_breakdown.ready_to_export == 0
    assert after.ready_breakdown.ready_to_approve == 0
    assert after.ready_breakdown.ready_to_export == 1
