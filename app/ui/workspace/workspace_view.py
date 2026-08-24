"""Composition and read-only session coordination for Document Workspace."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import QBoxLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.models.document import Document
from app.ui.models.workspace_queue_model import WorkspaceQueueModel
from app.ui.theme.tokens import LAYOUT
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.workspace.presentation import build_workspace_presentation
from app.ui.workspace.queue_rail import QueueRail
from app.ui.workspace.review_panel import ReviewPanel
from app.ui.workspace.workspace_header import WorkspaceHeader

try:
    from app.ui.workspace.source_preview import SourcePreview
except ModuleNotFoundError:  # H1 remains independently stageable before native PDF H2.
    from app.ui.workspace.source_placeholder import SourcePlaceholder as SourcePreview


DocumentProvider = Callable[[str], Document | None]


class WorkspaceView(QWidget):
    backRequested = Signal(str, str)

    def __init__(
        self,
        document_provider: DocumentProvider,
        *,
        source_preview: SourcePreview | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "workspaceView")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._provider = document_provider
        self.origin_route = ""
        self.origin_label = ""
        self.queue_model = WorkspaceQueueModel(parent=self)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = WorkspaceHeader()
        root.addWidget(self.header)
        self.regions = QWidget()
        region_layout = QHBoxLayout(self.regions)
        region_layout.setDirection(QBoxLayout.Direction.RightToLeft)
        region_layout.setContentsMargins(0, 0, 0, 0)
        region_layout.setSpacing(0)
        self.queue_rail = QueueRail(self.queue_model, self._provider)
        self.source_preview = source_preview or SourcePreview()
        self.review_panel = ReviewPanel()
        region_layout.addWidget(self.review_panel)
        region_layout.addWidget(self.source_preview, 1)
        region_layout.addWidget(self.queue_rail)
        root.addWidget(self.regions, 1)

        self.unavailable = QLabel("המסמך אינו זמין עוד")
        self.unavailable.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unavailable.setVisible(False)
        apply_typography(self.unavailable, TypographyRole.SECTION_TITLE)
        root.addWidget(self.unavailable)

        self.header.backRequested.connect(self.return_to_queue)
        self.header.previousRequested.connect(self.queue_model.previous)
        self.header.nextRequested.connect(self.queue_model.next)
        self.queue_model.currentChanged.connect(self._current_changed)
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.escape_shortcut.activated.connect(self.return_to_queue)

    @property
    def current_document_id(self) -> str | None:
        return self.queue_model.current_document_id

    def open_session(
        self,
        *,
        origin_route: str,
        origin_label: str,
        ordered_document_ids: Iterable[str],
        current_document_id: str,
    ) -> None:
        self.origin_route = str(origin_route)
        self.origin_label = origin_label
        self.queue_model.start_session(ordered_document_ids, current_document_id)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def return_to_queue(self) -> None:
        if self.origin_route:
            self.backRequested.emit(
                self.origin_route, self.current_document_id or ""
            )

    def refresh_current_document(self) -> None:
        self._load_current(self.current_document_id)

    def reconcile_queue(
        self,
        visible_document_ids: Iterable[str],
        available_document_ids: Iterable[str],
    ) -> None:
        visible = list(dict.fromkeys(str(value) for value in visible_document_ids))
        available = set(str(value) for value in available_document_ids)
        current = self.current_document_id
        old_index = self.queue_model.current_index
        if current and current not in available:
            self.queue_model.remove_document_id(current)
            current = self.current_document_id
        if current and current not in visible:
            visible.insert(min(max(old_index, 0), len(visible)), current)
        self.queue_model.refresh(value for value in visible if value in available)
        self.refresh_current_document()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.return_to_queue()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        compact = event.size().width() < 1000
        self.queue_rail.setFixedWidth(
            LAYOUT.workspace_queue_minimum_width
            if compact
            else LAYOUT.workspace_queue_width
        )
        self.review_panel.setFixedWidth(
            LAYOUT.workspace_fields_minimum_width
            if compact
            else LAYOUT.workspace_fields_width
        )
        super().resizeEvent(event)

    def _current_changed(self, document_id: object, _index: int, _total: int) -> None:
        self._load_current(str(document_id) if document_id else None)

    def _load_current(self, document_id: str | None) -> None:
        document = self._provider(document_id) if document_id else None
        if document is None:
            self.unavailable.setVisible(True)
            self.regions.setVisible(False)
            self.source_preview.release_source()
            return
        self.unavailable.setVisible(False)
        self.regions.setVisible(True)
        presentation = build_workspace_presentation(document)
        self.header.set_presentation(
            presentation,
            origin_label=self.origin_label,
            position=self.queue_model.position,
            total=self.queue_model.total,
            can_previous=self.queue_model.can_go_previous,
            can_next=self.queue_model.can_go_next,
        )
        self.review_panel.set_presentation(presentation)
        self.source_preview.load_presentation(presentation)
