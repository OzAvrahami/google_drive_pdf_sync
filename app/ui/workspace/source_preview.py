"""Native Qt PDF source viewer with read-only text/external fallbacks."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.components import ButtonVariant, PandaButton
from app.ui.file_opener import open_local_file
from app.ui.theme.direction import TextKind, apply_text_direction
from app.ui.theme.icons import IconName
from app.ui.theme.tokens import SPACING
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.workspace.presentation import WorkspaceDocumentPresentation


class SourceState(str, Enum):
    IDLE = "idle"
    LOADING = "loading"
    READY = "ready"
    MISSING = "missing"
    INVALID = "invalid"
    LOCKED = "locked"
    ERROR = "error"
    TEXT = "text"


ExternalOpener = Callable[[str, QWidget | None], bool]


class SourcePreview(QFrame):
    stateChanged = Signal(str)
    pageChanged = Signal(int, int)

    minimum_zoom = 0.25
    maximum_zoom = 4.0
    zoom_step = 1.2

    def __init__(
        self,
        *,
        external_opener: ExternalOpener = open_local_file,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "sourcePreview")
        self.setMinimumWidth(260)
        self._external_opener = external_opener
        self._pdf_document: QPdfDocument | None = None
        self._local_path = ""
        self._raw_text = ""
        self._pdf_ready = False
        self._state = SourceState.IDLE
        self._page_count = 0
        self._build_ui()
        self._set_state(SourceState.IDLE, "בחרו מסמך להצגת המקור")

    @property
    def source_state(self) -> SourceState:
        return self._state

    @property
    def pdf_document(self) -> QPdfDocument | None:
        return self._pdf_document

    @property
    def current_page(self) -> int:
        if self._pdf_document is None or not self._pdf_ready:
            return 0
        return self.pdf_view.pageNavigator().currentPage() + 1

    @property
    def page_count(self) -> int:
        return self._page_count

    @property
    def zoom_factor(self) -> float:
        return float(self.pdf_view.zoomFactor())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        toolbar = QFrame()
        toolbar.setProperty("pandaComponent", "sourceToolbar")
        controls = QHBoxLayout(toolbar)
        controls.setContentsMargins(10, 7, 10, 7)
        controls.setSpacing(SPACING.tight)
        self.previous_page_button = PandaButton(
            "", variant=ButtonVariant.GHOST, icon_name=IconName.PAGE_PREVIOUS
        )
        self.previous_page_button.setAccessibleName("העמוד הקודם")
        self.previous_page_button.setToolTip("העמוד הקודם")
        self.previous_page_button.setFixedWidth(28)
        self.next_page_button = PandaButton(
            "", variant=ButtonVariant.GHOST, icon_name=IconName.PAGE_NEXT
        )
        self.next_page_button.setAccessibleName("העמוד הבא")
        self.next_page_button.setToolTip("העמוד הבא")
        self.next_page_button.setFixedWidth(28)
        self.page_label = QLabel("0 / 0")
        apply_typography(self.page_label, TypographyRole.TECHNICAL)
        apply_text_direction(self.page_label, TextKind.TECHNICAL)
        self.zoom_out_button = PandaButton("−", variant=ButtonVariant.GHOST)
        self.zoom_out_button.setAccessibleName("הקטנת תצוגת PDF")
        self.zoom_out_button.setToolTip("הקטנת תצוגת PDF")
        self.zoom_out_button.setFixedWidth(28)
        self.zoom_in_button = PandaButton("+", variant=ButtonVariant.GHOST)
        self.zoom_in_button.setAccessibleName("הגדלת תצוגת PDF")
        self.zoom_in_button.setToolTip("הגדלת תצוגת PDF")
        self.zoom_in_button.setFixedWidth(28)
        self.zoom_label = QLabel("100%")
        apply_typography(self.zoom_label, TypographyRole.TECHNICAL)
        self.fit_width_button = PandaButton("רוחב", variant=ButtonVariant.SECONDARY)
        self.fit_width_button.setToolTip("התאמת ה-PDF לרוחב התצוגה")
        self.fit_page_button = PandaButton("עמוד", variant=ButtonVariant.GHOST)
        self.fit_page_button.setToolTip("התאמת עמוד שלם לתצוגה")
        self.text_button = PandaButton("טקסט", variant=ButtonVariant.GHOST)
        self.text_button.setToolTip("הצגת הטקסט שחולץ")
        self.external_button = PandaButton("פתיחה חיצונית", variant=ButtonVariant.GHOST)
        controls.addWidget(self.previous_page_button)
        controls.addWidget(self.page_label)
        controls.addWidget(self.next_page_button)
        controls.addSpacing(SPACING.adjacent)
        controls.addWidget(self.zoom_out_button)
        controls.addWidget(self.zoom_label)
        controls.addWidget(self.zoom_in_button)
        controls.addWidget(self.fit_width_button)
        controls.addWidget(self.fit_page_button)
        controls.addStretch()
        controls.addWidget(self.text_button)
        controls.addWidget(self.external_button)
        root.addWidget(toolbar)

        self.stack = QStackedWidget()
        self.pdf_view = QPdfView()
        self.pdf_view.setProperty("pandaComponent", "pdfView")
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self._empty_pdf_document = QPdfDocument(self)
        self.pdf_view.setDocument(self._empty_pdf_document)
        self.stack.addWidget(self.pdf_view)
        self.text_view = QPlainTextEdit()
        self.text_view.setProperty("pandaComponent", "extractedTextView")
        self.text_view.setReadOnly(True)
        self.text_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        apply_typography(self.text_view, TypographyRole.TECHNICAL)
        apply_text_direction(self.text_view, TextKind.TECHNICAL)
        self.stack.addWidget(self.text_view)
        self.state_panel = QWidget()
        state_layout = QVBoxLayout(self.state_panel)
        state_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_title = QLabel()
        self.state_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_title.setWordWrap(True)
        apply_typography(self.state_title, TypographyRole.SECTION_TITLE)
        self.state_detail = QLabel()
        self.state_detail.setProperty("pandaRole", "muted")
        self.state_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_detail.setWordWrap(True)
        apply_typography(self.state_detail, TypographyRole.COMPACT_BODY)
        state_layout.addWidget(self.state_title)
        state_layout.addWidget(self.state_detail)
        self.stack.addWidget(self.state_panel)
        root.addWidget(self.stack, 1)

        self.previous_page_button.clicked.connect(self.previous_page)
        self.next_page_button.clicked.connect(self.next_page)
        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.fit_width_button.clicked.connect(self.fit_width)
        self.fit_page_button.clicked.connect(self.fit_page)
        self.text_button.clicked.connect(self.toggle_extracted_text)
        self.external_button.clicked.connect(self.open_external)

    def load_presentation(self, presentation: WorkspaceDocumentPresentation) -> None:
        self.release_source()
        self._local_path = presentation.local_path
        self._raw_text = self._read_extracted_text(presentation.raw_text_path)
        self.text_view.setPlainText(self._raw_text)
        self.text_button.setEnabled(bool(self._raw_text))
        path = Path(self._local_path) if self._local_path else None
        valid_local = bool(path and path.is_file())
        self.external_button.setEnabled(valid_local)
        if not valid_local:
            self._set_state(
                SourceState.MISSING,
                "הקובץ המקומי אינו זמין",
                "ניתן להמשיך לעיין בפרטי המסמך"
                + (" או בטקסט שחולץ" if self._raw_text else ""),
            )
            return

        self._set_state(SourceState.LOADING, "טוען PDF…")
        document = QPdfDocument(self)
        document.statusChanged.connect(self._pdf_status_changed)
        document.pageCountChanged.connect(self._page_count_changed)
        self._pdf_document = document
        self.pdf_view.setDocument(document)
        navigator = self.pdf_view.pageNavigator()
        navigator.currentPageChanged.connect(self._current_page_changed)
        result = document.load(str(path))
        if result is not QPdfDocument.Error.None_:
            self._show_pdf_error(result)

    def release_source(self) -> None:
        previous, self._pdf_document = self._pdf_document, None
        self._pdf_ready = False
        self._page_count = 0
        self._local_path = ""
        self._raw_text = ""
        self.text_view.clear()
        self.text_button.setEnabled(False)
        self.external_button.setEnabled(False)
        self.pdf_view.setDocument(self._empty_pdf_document)
        if previous is not None:
            previous.close()
            previous.deleteLater()
            # Destructive Workspace actions may safely delete the just-viewed
            # cached PDF immediately after release. Flush only this deferred
            # document deletion so Windows no longer retains its file handle.
            QCoreApplication.sendPostedEvents(previous, QEvent.Type.DeferredDelete)
        self._update_controls()

    def previous_page(self) -> None:
        if self._pdf_ready and self.current_page > 1:
            self._jump_to(self.current_page - 2)

    def next_page(self) -> None:
        if self._pdf_ready and self.current_page < self._page_count:
            self._jump_to(self.current_page)

    def zoom_in(self) -> None:
        self._set_zoom(self.zoom_factor * self.zoom_step)

    def zoom_out(self) -> None:
        self._set_zoom(self.zoom_factor / self.zoom_step)

    def fit_width(self) -> None:
        if self._pdf_ready:
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            self._update_zoom_label()

    def fit_page(self) -> None:
        if self._pdf_ready:
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView)
            self._update_zoom_label()

    def show_extracted_text(self) -> None:
        if self._raw_text:
            self._set_state(SourceState.TEXT)

    def show_pdf(self) -> None:
        if self._pdf_ready:
            self._set_state(SourceState.READY)

    def toggle_extracted_text(self) -> None:
        if self._state is SourceState.TEXT and self._pdf_ready:
            self.show_pdf()
        else:
            self.show_extracted_text()

    def open_external(self) -> bool:
        if not self.external_button.isEnabled():
            return False
        return bool(self._external_opener(self._local_path, self))

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.fit_page_button.setVisible(event.size().width() >= 480)
        super().resizeEvent(event)

    def _set_zoom(self, factor: float) -> None:
        if not self._pdf_ready:
            return
        bounded = min(self.maximum_zoom, max(self.minimum_zoom, float(factor)))
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.pdf_view.setZoomFactor(bounded)
        self._update_zoom_label()

    def _jump_to(self, zero_based_page: int) -> None:
        navigator = self.pdf_view.pageNavigator()
        navigator.jump(zero_based_page, QPointF(), self.pdf_view.zoomFactor())

    def _pdf_status_changed(self, status: QPdfDocument.Status) -> None:
        if self._pdf_document is None:
            return
        if status is QPdfDocument.Status.Ready:
            self._pdf_ready = True
            self._page_count_changed(self._pdf_document.pageCount())
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            self._set_state(SourceState.READY)
        elif status is QPdfDocument.Status.Error:
            self._show_pdf_error(self._pdf_document.error())

    def _show_pdf_error(self, error: QPdfDocument.Error) -> None:
        self._pdf_ready = False
        if error in {
            QPdfDocument.Error.IncorrectPassword,
            QPdfDocument.Error.UnsupportedSecurityScheme,
        }:
            state, title = SourceState.LOCKED, "לא ניתן לפתוח PDF מוגן"
        elif error is QPdfDocument.Error.InvalidFileFormat:
            state, title = SourceState.INVALID, "קובץ ה-PDF אינו תקין"
        elif error is QPdfDocument.Error.FileNotFound:
            state, title = SourceState.MISSING, "הקובץ המקומי אינו זמין"
        else:
            state, title = SourceState.ERROR, "לא ניתן להציג את קובץ ה-PDF"
        self._set_state(
            state,
            title,
            "פרטי המסמך נשארים זמינים"
            + ("; ניתן לעבור לטקסט שחולץ" if self._raw_text else ""),
        )

    def _page_count_changed(self, count: int) -> None:
        self._page_count = max(0, int(count))
        self._update_controls()

    def _current_page_changed(self, _page: int) -> None:
        self._update_controls()

    def _update_controls(self) -> None:
        current = self.current_page
        self.page_label.setText(f"{current} / {self._page_count}")
        self.previous_page_button.setEnabled(self._pdf_ready and current > 1)
        self.next_page_button.setEnabled(
            self._pdf_ready and current < self._page_count
        )
        for button in (
            self.zoom_in_button,
            self.zoom_out_button,
            self.fit_width_button,
            self.fit_page_button,
        ):
            button.setEnabled(self._pdf_ready)
        self._update_zoom_label()
        self.pageChanged.emit(current, self._page_count)

    def _update_zoom_label(self) -> None:
        if not self._pdf_ready:
            self.zoom_label.setText("—")
        elif self.pdf_view.zoomMode() is QPdfView.ZoomMode.FitToWidth:
            self.zoom_label.setText("רוחב")
        elif self.pdf_view.zoomMode() is QPdfView.ZoomMode.FitInView:
            self.zoom_label.setText("עמוד")
        else:
            self.zoom_label.setText(f"{int(self.zoom_factor * 100)}%")

    def _set_state(self, state: SourceState, title: str = "", detail: str = "") -> None:
        self._state = state
        self.setProperty("sourceState", state.value)
        if state is SourceState.READY:
            self.stack.setCurrentWidget(self.pdf_view)
            self.text_button.setText("טקסט")
        elif state is SourceState.TEXT:
            self.stack.setCurrentWidget(self.text_view)
            self.text_button.setText("PDF" if self._pdf_ready else "טקסט")
        else:
            self.state_title.setText(title)
            self.state_detail.setText(detail)
            self.stack.setCurrentWidget(self.state_panel)
            self.text_button.setText("טקסט")
        self.stateChanged.emit(state.value)
        self._update_controls()

    @staticmethod
    def _read_extracted_text(raw_text_path: str) -> str:
        if not raw_text_path:
            return ""
        path = Path(raw_text_path)
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ""
