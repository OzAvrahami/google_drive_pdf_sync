from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.application.document_review_service import DocumentReviewService
from app.application.duplicate_comparison_service import DuplicateComparisonService
from app.application.duplicate_resolution_service import DuplicateResolutionService
from app.application.irrelevant_service import IrrelevantService
from app.models.document import Document
from app.ui.models.queue_policy import QueueRoute
from app.ui.routes import AppRoute
from app.ui.shell import PandaMainWindow
from app.ui.workspace import DuplicateComparisonPanel, WorkspaceView


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def cleanup_widgets(qapp):
    yield
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, PandaMainWindow):
            widget.workspace.set_discard_confirmation(lambda _reason: True)
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


class MemorySource:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = {item.drive_file_id: deepcopy(item) for item in documents}
        self.write_count = 0

    def all(self) -> list[Document]:
        return [deepcopy(item) for item in self.documents.values()]

    def get_by_drive_id(self, document_id: str) -> Document | None:
        item = self.documents.get(document_id)
        return deepcopy(item) if item else None

    def upsert(self, document: Document) -> None:
        self.write_count += 1
        stored = deepcopy(document)
        stored.touch()
        self.documents[stored.drive_file_id] = stored

    def upsert_many(self, documents: list[Document]) -> None:
        for document in documents:
            self.upsert(document)


def doc(document_id: str, status: str = "processed", **overrides) -> Document:
    values = {
        "drive_file_id": document_id,
        "id": f"record-{document_id}",
        "file_name": f"{document_id}.pdf",
        "folder_path": "Drive / invoices",
        "status": status,
        "supplier_name": "Example Supplier",
        "invoice_number": "INV-100",
        "invoice_date": "24/08/2026",
        "total": 117.0,
        "description": "Synthetic",
    }
    values.update(overrides)
    return Document(**values)


def duplicate(document_id="current", candidates=None, confidence="exact", **overrides):
    item = doc(document_id, **overrides)
    item.is_duplicate_suspected = True
    item.suspected_duplicate_of = candidates or ["candidate"]
    item.duplicate_confidence = confidence
    return item


def workspace_for(
    source: MemorySource,
    ids: tuple[str, ...],
    *,
    discard=None,
    destructive=None,
    irrelevant_service=None,
) -> WorkspaceView:
    irrelevant = irrelevant_service or IrrelevantService(source)
    comparison = DuplicateComparisonService(source)
    resolution = DuplicateResolutionService(source, irrelevant)
    workspace = WorkspaceView(
        source.get_by_drive_id,
        review_service=DocumentReviewService(source),
        duplicate_comparison_service=comparison,
        duplicate_resolution_service=resolution,
        irrelevant_service=irrelevant,
        discard_confirmation=discard,
        destructive_confirmation=destructive,
    )
    workspace.open_session(
        origin_route="attention",
        origin_label="דורש טיפול",
        ordered_document_ids=ids,
        current_document_id=ids[0],
    )
    return workspace


def test_slim_duplicate_strip_expands_exact_comparison(qapp) -> None:
    source = MemorySource([duplicate(), doc("candidate", status="approved")])
    workspace = workspace_for(source, ("current",))
    panel = workspace.review_panel.duplicate_panel

    assert isinstance(panel, DuplicateComparisonPanel)
    assert "חשד לכפילות" in panel.summary.text()
    assert "התאמה מדויקת" in panel.summary.text()
    assert panel._expanded is False
    panel.compare_button.click()
    assert panel._expanded is True
    assert "ספק, מספר מסמך ותאריך" in panel.reason.text()


def test_high_comparison_explains_supplier_date_amount(qapp) -> None:
    source = MemorySource(
        [
            duplicate(confidence="high", invoice_number=None),
            doc("candidate", status="approved", invoice_number=None),
        ]
    )
    workspace = workspace_for(source, ("current",))
    panel = workspace.review_panel.duplicate_panel
    panel.toggle_expanded()
    assert "התאמה גבוהה" in panel.summary.text()
    assert "ספק, תאריך וסכום" in panel.reason.text()


def test_multiple_candidates_can_be_selected_and_missing_one_disables_confirm(qapp) -> None:
    source = MemorySource(
        [duplicate(candidates=["candidate", "missing"]), doc("candidate")]
    )
    workspace = workspace_for(source, ("current",))
    panel = workspace.review_panel.duplicate_panel
    assert panel.candidate_selector.count() == 2
    panel.candidate_selector.setCurrentIndex(1)
    assert "אינה זמינה" in panel.reason.text()
    assert panel.open_button.isEnabled() is False
    assert panel.confirm_button.isEnabled() is False


def test_open_existing_uses_stable_id_and_has_clean_return(qapp) -> None:
    source = MemorySource([duplicate(), doc("candidate", status="approved")])
    workspace = workspace_for(source, ("current",))

    assert workspace.open_duplicate_candidate("candidate") is True
    assert workspace.current_document_id == "candidate"
    assert workspace.header.related_back_button.isHidden() is False
    workspace.header.related_back_button.click()
    assert workspace.current_document_id == "current"
    assert workspace.header.related_back_button.isHidden() is True


def test_dirty_draft_blocks_open_and_destructive_actions(qapp) -> None:
    source = MemorySource([duplicate(), doc("candidate")])
    irrelevant = Mock()
    workspace = workspace_for(
        source,
        ("current",),
        discard=lambda _reason: False,
        destructive=lambda *_args: True,
        irrelevant_service=irrelevant,
    )
    workspace.review_panel.field_editors["supplier_name"].editor.setText("Changed")
    assert workspace.is_dirty is True
    assert workspace.open_duplicate_candidate("candidate") is False
    assert workspace.mark_current_irrelevant() is False
    irrelevant.mark_irrelevant.assert_not_called()


def test_destructive_confirmation_cancel_has_no_side_effect(qapp) -> None:
    source = MemorySource([doc("current")])
    irrelevant = Mock()
    workspace = workspace_for(
        source,
        ("current",),
        destructive=lambda *_args: False,
        irrelevant_service=irrelevant,
    )
    assert workspace.mark_current_irrelevant() is False
    irrelevant.mark_irrelevant.assert_not_called()
    assert source.write_count == 0


def test_not_duplicate_refreshes_workspace_and_emits_stable_id(qapp) -> None:
    source = MemorySource([duplicate(), doc("candidate")])
    workspace = workspace_for(source, ("current",))
    changed = QSignalSpy(workspace.duplicateResolved)

    assert workspace.dismiss_current_duplicate() is True

    assert changed.count() == 1
    assert changed.at(0)[0] == "current"
    assert source.get_by_drive_id("current").status == "processed"
    assert source.get_by_drive_id("current").is_duplicate_suspected is False
    assert workspace.review_panel.duplicate_panel is None


def test_general_irrelevant_deletes_safe_pdf_retains_text_and_shows_success(
    qapp, tmp_path: Path
) -> None:
    root = tmp_path / "downloads"
    pdf = root / "nested" / "current.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4")
    text = tmp_path / "text" / "current.txt"
    text.parent.mkdir()
    text.write_text("retained", encoding="utf-8")
    current = doc("current", local_path=str(pdf), raw_text_path=str(text))
    source = MemorySource([current])
    irrelevant = IrrelevantService(source, downloads_root=root)
    workspace = workspace_for(
        source,
        ("current",),
        destructive=lambda *_args: True,
        irrelevant_service=irrelevant,
    )
    changed = QSignalSpy(workspace.documentMarkedIrrelevant)
    with patch(
        "app.services.exclusion_service.EXCLUDED_FILES_JSON", tmp_path / "excluded.json"
    ):
        succeeded = workspace.mark_current_irrelevant()
        assert succeeded is True, workspace.review_panel.feedback.accessibleName()

    assert changed.count() == 1
    assert not pdf.exists()
    assert text.read_text(encoding="utf-8") == "retained"
    assert source.get_by_drive_id("current").status == "confirmed_irrelevant"
    assert workspace.is_editable is False
    assert workspace.review_panel.feedback.property("variant") == "success"


def test_confirm_duplicate_marks_current_only_via_shared_flow(qapp, tmp_path: Path) -> None:
    root = tmp_path / "downloads"
    pdf = root / "current.pdf"
    root.mkdir()
    pdf.write_bytes(b"%PDF-1.4")
    current = duplicate(local_path=str(pdf))
    candidate = doc("candidate", status="approved")
    source = MemorySource([current, candidate])
    workspace = workspace_for(
        source,
        ("current",),
        destructive=lambda *_args: True,
        irrelevant_service=IrrelevantService(source, downloads_root=root),
    )
    with patch(
        "app.services.exclusion_service.EXCLUDED_FILES_JSON", tmp_path / "excluded.json"
    ):
        succeeded = workspace.confirm_current_duplicate("candidate")
        assert succeeded is True, workspace.review_panel.feedback.accessibleName()

    assert source.get_by_drive_id("current").status == "confirmed_irrelevant"
    assert source.get_by_drive_id("candidate").status == "approved"
    assert not pdf.exists()


def test_shell_refreshes_attention_ready_and_irrelevant_counts(qapp, tmp_path: Path) -> None:
    root = tmp_path / "downloads"
    pdf = root / "current.pdf"
    root.mkdir()
    pdf.write_bytes(b"%PDF-1.4")
    source = MemorySource(
        [duplicate(local_path=str(pdf)), doc("candidate", status="approved")]
    )
    irrelevant = IrrelevantService(source, downloads_root=root)
    shell = PandaMainWindow(
        source, operational_enabled=False, irrelevant_service=irrelevant
    )
    shell.navigate(AppRoute.ATTENTION)
    shell.attention.focus_document("current")
    shell.open_workspace(
        "current", shell.attention.ordered_visible_document_ids, "attention"
    )
    shell.workspace._destructive_confirmation = lambda *_args: True
    changed = QSignalSpy(shell.workspace.documentMarkedIrrelevant)
    before_ready = shell._counts.ready
    with patch(
        "app.services.exclusion_service.EXCLUDED_FILES_JSON", tmp_path / "excluded.json"
    ):
        succeeded = shell.workspace.mark_current_irrelevant()
        assert succeeded is True, shell.workspace.review_panel.feedback.accessibleName()

    assert changed.count() == 1
    QApplication.processEvents()
    assert source.get_by_drive_id("current").status == "confirmed_irrelevant"
    assert shell._counts.attention == 0
    assert shell._counts.irrelevant == 1
    assert shell._counts.ready == before_ready
    assert shell.workspace.current_document_id == "current"
    assert shell.workspace.queue_model.document_ids == ()


def test_workspace_comparison_constructs_at_compact_size(qapp) -> None:
    source = MemorySource([duplicate(), doc("candidate")])
    workspace = workspace_for(source, ("current",))
    workspace.resize(860, 622)
    workspace.review_panel.duplicate_panel.toggle_expanded()
    assert workspace.queue_rail is not None
    assert workspace.source_preview is not None
    assert workspace.review_panel.duplicate_panel._expanded is True
