from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from app.services.pdf_corpus_service import ManifestWriteError, PdfCorpusService, read_manifest
from app.ui.benchmark import PdfBenchmarkPage


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class PreviewStub(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.presentations = []
        self.release_calls = 0

    def load_presentation(self, presentation) -> None:
        self.presentations.append(presentation)

    def release_source(self) -> None:
        self.release_calls += 1


def analyzer(path: Path, root: Path) -> dict:
    non_native = path.name.startswith("scan")
    skipped = path.name.startswith("receipt")
    return {
        "filename": path.name,
        "relative_path": path.relative_to(root).as_posix(),
        "parser_result": (
            {"document_type": "קבלה"}
            if skipped
            else {
                "document_type": "payment_request",
                "business_name": f"Supplier {path.stem}",
                "invoice_number": path.stem[-1:],
                "invoice_date": "29/01/2026",
                "amount": 802.0,
            }
            if not non_native
            else {"document_type": None}
        ),
        "source_detection": {
            "source_system": "Morning" if not non_native else "Unknown",
            "source_confidence": "high" if not non_native else "unknown",
            "source_evidence": ["synthetic"],
        },
        "extraction_metrics": {"native_text": not non_native, "meaningful_chars": 100 if not non_native else 0},
        "confidence": 0.9 if not (non_native or skipped) else 0.0,
        "status": "skipped" if skipped else "needs_review" if non_native else "processed",
        "errors": {"extraction": None, "parser": None},
        "warnings": [],
    }


def make_page(tmp_path: Path, names=("invoice1.pdf",), *, confirmer=lambda _reason: True):
    for name in names:
        (tmp_path / name).write_bytes(f"synthetic-{name}".encode())
    service = PdfCorpusService(
        tmp_path,
        benchmark_path=tmp_path / "missing.json",
        analyzer=analyzer,
    )
    preview = PreviewStub()
    page = PdfBenchmarkPage(
        service,
        source_preview=preview,
        asynchronous_analysis=False,
        discard_confirmer=confirmer,
    )
    page.open_page()
    return page, service, preview


def set_combo(combo, value: str) -> None:
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


def test_page_opens_corpus_and_displays_current_panda_values(qapp, tmp_path: Path) -> None:
    page, service, preview = make_page(tmp_path)

    assert page.splitter.layoutDirection() == Qt.LayoutDirection.LeftToRight
    assert page.splitter.indexOf(page.corpus_list) == 0
    assert page.splitter.indexOf(page.source_preview) == 1
    assert page.splitter.indexOf(page.review_panel) == 2
    assert len(page.visible_records) == 1
    assert page.current_sha == service.records[0]["sha256"]
    assert preview.presentations[-1].local_path.endswith("invoice1.pdf")
    assert page.review_panel.fields["expected_supplier"].panda_value.text() == "Supplier invoice1"
    assert page.review_panel.fields["expected_amount"].editor.text() == "802.00"
    assert not service.manifest_path.exists()


def test_empty_corpus_has_intentional_empty_state(qapp, tmp_path: Path) -> None:
    service = PdfCorpusService(tmp_path, benchmark_path=tmp_path / "missing.json", analyzer=analyzer)
    page = PdfBenchmarkPage(service, source_preview=PreviewStub(), asynchronous_analysis=False)

    page.open_page()

    assert page.content_stack.currentWidget() is page.empty_state
    assert "_incoming" in page.empty_state.description_label.text()


def test_everything_correct_persists_updates_progress_and_advances(qapp, tmp_path: Path) -> None:
    page, service, _preview = make_page(tmp_path, ("invoice1.pdf", "invoice2.pdf"))
    first_sha = page.current_sha

    page.everything_correct()

    assert first_sha is not None
    assert service.record_by_sha(first_sha)["reviewed"] is True
    assert page.current_sha != first_sha
    assert page.progress_label.text().startswith("נבדקו 1 / 2")
    rows = read_manifest(service.manifest_path)
    assert next(row for row in rows if row["sha256"] == first_sha)["expected_amount"] == "802.00"


def test_manual_field_correction_persists_visible_mismatch(qapp, tmp_path: Path) -> None:
    page, service, _preview = make_page(tmp_path)
    digest = page.current_sha
    page.review_panel.fields["expected_invoice_number"].editor.setText("92804")

    page.save_and_next()
    set_combo(page.review_filter, "mismatches")

    saved = service.record_by_sha(digest)
    assert saved["expected_invoice_number"] == "92804"
    assert saved["invoice_number_correct"] is False
    assert page.visible_records[0]["sha256"] == digest
    assert page.review_panel.fields["expected_invoice_number"].state_label.text() == "אי התאמה"


def test_intentional_blank_control_persists_blank(qapp, tmp_path: Path) -> None:
    page, service, _preview = make_page(tmp_path)
    digest = page.current_sha
    page.review_panel.fields["expected_supplier"].intentional_blank.setChecked(True)

    page.save_and_next()

    assert service.record_by_sha(digest)["expected_supplier"] == ""
    assert service.record_by_sha(digest)["reviewed"] is True


def test_unsaved_selection_change_can_be_rejected(qapp, tmp_path: Path) -> None:
    page, _service, _preview = make_page(
        tmp_path,
        ("invoice1.pdf", "invoice2.pdf"),
        confirmer=lambda _reason: False,
    )
    original = page.current_sha
    page.review_panel.fields["expected_supplier"].editor.setText("unsaved")
    other = next(sha for sha in page.corpus_list.ordered_shas if sha != original)

    page.corpus_list.select_sha(other)

    assert page.current_sha == original
    assert page.is_dirty


def test_skipped_document_is_policy_state_not_failure(qapp, tmp_path: Path) -> None:
    page, _service, _preview = make_page(tmp_path, ("receipt1.pdf",))

    page.include_skipped.setChecked(True)

    assert page.current_sha is not None
    assert "דולג לפי מדיניות" in page.review_panel.state_feedback.text()


def test_non_native_document_is_available_outside_default_native_filter(qapp, tmp_path: Path) -> None:
    page, _service, _preview = make_page(tmp_path, ("scan1.pdf",))

    assert page.visible_records == ()
    set_combo(page.native_filter, "all")

    assert len(page.visible_records) == 1
    assert "OCR אינו מיושם" in page.review_panel.state_feedback.text()


def test_locked_manifest_error_is_concise_and_preserves_draft(qapp, tmp_path: Path, monkeypatch) -> None:
    page, service, _preview = make_page(tmp_path)
    page.review_panel.fields["expected_supplier"].editor.setText("Corrected")
    monkeypatch.setattr(
        service,
        "save_review",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ManifestWriteError("locked")),
    )

    page.save_and_next()

    assert page.review_panel._feedback is not None
    assert "pdf_manifest.csv" in page.review_panel._feedback.accessibleName()
    assert page.is_dirty


def test_filter_controls_and_shortcut_tooltips_are_available(qapp, tmp_path: Path) -> None:
    page, _service, _preview = make_page(tmp_path)

    assert page.review_filter.findData("unreviewed") >= 0
    assert page.review_filter.findData("mismatches") >= 0
    assert page.status_filter.findData("skipped") >= 0
    assert page.native_filter.findData("non_native") >= 0
    assert "Ctrl+Enter" in page.review_panel.save_next_button.toolTip()
    assert "Alt+A" in page.review_panel.everything_correct_button.toolTip()
