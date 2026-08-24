from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6 import QtPdf, QtPdfWidgets
from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QIcon, QPainter, QPdfWriter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.models.document import Document
from app.ui.workspace.presentation import build_workspace_presentation
from app.ui.workspace.source_preview import SourcePreview, SourceState


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def make_pdf(path: Path, pages: int = 2) -> Path:
    writer = QPdfWriter(str(path))
    painter = QPainter(writer)
    for page in range(pages):
        painter.drawText(QRectF(200, 200, 1800, 500), f"Synthetic page {page + 1}")
        if page + 1 < pages:
            writer.newPage()
    painter.end()
    return path


def presentation(local_path: Path | str = "", raw_text_path: Path | str = ""):
    return build_workspace_presentation(
        Document(
            drive_file_id="pdf-doc",
            file_name="synthetic.pdf",
            folder_path="tests",
            status="needs_review",
            local_path=str(local_path),
            raw_text_path=str(raw_text_path),
        )
    )


def wait_for_terminal_state(qapp: QApplication, preview: SourcePreview) -> None:
    for _ in range(100):
        qapp.processEvents()
        if preview.source_state not in {SourceState.IDLE, SourceState.LOADING}:
            return
        QTest.qWait(10)
    raise AssertionError(f"PDF load did not finish: {preview.source_state}")


def test_verified_qt_pdf_modules_expose_native_document_and_view() -> None:
    assert hasattr(QtPdf, "QPdfDocument")
    assert hasattr(QtPdfWidgets, "QPdfView")


def test_valid_synthetic_pdf_loads_pages_and_navigates(qapp, tmp_path) -> None:
    preview = SourcePreview()
    preview.load_presentation(presentation(make_pdf(tmp_path / "two-pages.pdf")))
    wait_for_terminal_state(qapp, preview)

    assert preview.source_state is SourceState.READY
    assert preview.page_count == 2
    assert preview.current_page == 1
    assert preview.previous_page_button.isEnabled() is False
    assert preview.next_page_button.isEnabled() is True
    preview.next_page()
    qapp.processEvents()
    assert preview.current_page == 2
    assert preview.previous_page_button.isEnabled() is True
    assert preview.next_page_button.isEnabled() is False
    preview.previous_page()
    qapp.processEvents()
    assert preview.current_page == 1


def test_one_page_pdf_keeps_muted_navigation_icons_visible(qapp, tmp_path) -> None:
    preview = SourcePreview()
    preview.load_presentation(presentation(make_pdf(tmp_path / "one-page.pdf", 1)))
    wait_for_terminal_state(qapp, preview)

    assert preview.page_count == 1
    for button in (preview.previous_page_button, preview.next_page_button):
        assert button.isEnabled() is False
        assert button.text() == ""
        assert button.accessibleName()
        assert button.toolTip()
        disabled_icon = button.icon().pixmap(
            QSize(17, 17), QIcon.Mode.Disabled, QIcon.State.Off
        )
        enabled_icon = button.icon().pixmap(
            QSize(17, 17), QIcon.Mode.Normal, QIcon.State.Off
        )
        assert disabled_icon.isNull() is False
        disabled_image = disabled_icon.toImage()
        assert any(
            disabled_image.pixelColor(x, y).alpha() > 0
            for x in range(disabled_image.width())
            for y in range(disabled_image.height())
        )
        assert disabled_image != enabled_icon.toImage()


def test_zoom_is_bounded_and_fit_modes_remain_available(qapp, tmp_path) -> None:
    preview = SourcePreview()
    preview.load_presentation(presentation(make_pdf(tmp_path / "zoom.pdf", 1)))
    wait_for_terminal_state(qapp, preview)

    for _ in range(50):
        preview.zoom_in()
    assert preview.zoom_factor == pytest.approx(preview.maximum_zoom)
    for _ in range(100):
        preview.zoom_out()
    assert preview.zoom_factor == pytest.approx(preview.minimum_zoom)
    preview.fit_width()
    assert preview.zoom_label.text() == "רוחב"
    preview.fit_page()
    assert preview.zoom_label.text() == "עמוד"


def test_missing_pdf_keeps_text_fallback_available(qapp, tmp_path) -> None:
    raw = tmp_path / "source.txt"
    raw.write_text("Synthetic extracted text\nINV-17", encoding="utf-8")
    preview = SourcePreview()

    preview.load_presentation(presentation(tmp_path / "missing.pdf", raw))

    assert preview.source_state is SourceState.MISSING
    assert preview.external_button.isEnabled() is False
    assert preview.text_button.isEnabled() is True
    preview.show_extracted_text()
    assert preview.source_state is SourceState.TEXT
    assert "INV-17" in preview.text_view.toPlainText()


def test_malformed_pdf_is_nonfatal_and_external_fallback_remains(qapp, tmp_path) -> None:
    malformed = tmp_path / "malformed.pdf"
    malformed.write_bytes(b"not a pdf")
    preview = SourcePreview()
    preview.load_presentation(presentation(malformed))
    wait_for_terminal_state(qapp, preview)

    assert preview.source_state in {SourceState.INVALID, SourceState.ERROR}
    assert preview.external_button.isEnabled() is True
    assert preview.page_count == 0


def test_external_open_uses_shared_boundary_with_current_valid_path(qapp, tmp_path) -> None:
    opened: list[tuple[str, object]] = []
    pdf = make_pdf(tmp_path / "external.pdf", 1)
    preview = SourcePreview(
        external_opener=lambda path, parent: opened.append((path, parent)) or True
    )
    preview.load_presentation(presentation(pdf))
    wait_for_terminal_state(qapp, preview)

    assert preview.open_external() is True
    assert opened == [(str(pdf), preview)]


def test_loading_next_document_releases_previous_pdf_instance(qapp, tmp_path) -> None:
    first = make_pdf(tmp_path / "first.pdf", 1)
    second = make_pdf(tmp_path / "second.pdf", 2)
    preview = SourcePreview()
    preview.load_presentation(presentation(first))
    wait_for_terminal_state(qapp, preview)
    old_document = preview.pdf_document

    preview.load_presentation(presentation(second))
    wait_for_terminal_state(qapp, preview)

    assert preview.pdf_document is not old_document
    assert preview.source_state is SourceState.READY
    assert preview.page_count == 2


def test_text_toggle_returns_to_pdf_when_pdf_is_ready(qapp, tmp_path) -> None:
    pdf = make_pdf(tmp_path / "toggle.pdf", 1)
    raw = tmp_path / "toggle.txt"
    raw.write_text("text view", encoding="utf-8")
    preview = SourcePreview()
    preview.load_presentation(presentation(pdf, raw))
    wait_for_terminal_state(qapp, preview)

    preview.toggle_extracted_text()
    assert preview.source_state is SourceState.TEXT
    preview.toggle_extracted_text()
    assert preview.source_state is SourceState.READY
