"""Panda 2.0 application shell, available through the development selector."""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.models.document import Document
from app.ui.components import ButtonVariant, NavigationRail, PandaButton
from app.ui.models.queue_policy import calculate_queue_counts
from app.ui.routes import AppRoute, ROUTES, RouteViewKind, route_definition
from app.ui.theme import apply_panda_theme
from app.ui.theme.tokens import LAYOUT, SPACING
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.views import OverviewView, QueueRoutePlaceholder


class ReadOnlyDocumentSource(Protocol):
    def all(self) -> list[Document]: ...


_DEVELOPMENT_ACTION_REASON = (
    "הפעולה אינה זמינה במעטפת הפיתוח של Panda 2.0. "
    "הפעלת משימות הרקע תעבור למרכז המשימות בשלב הבא."
)


class PandaMainWindow(QMainWindow):
    """Read-only Panda 2.0 shell; legacy MainWindow remains independent."""

    routeChanged = Signal(str)

    def __init__(self, document_source: ReadOnlyDocumentSource, parent=None) -> None:
        super().__init__(parent)
        self._document_source = document_source
        self._documents: tuple[Document, ...] = ()
        self._current_route = AppRoute.OVERVIEW
        self._views: dict[AppRoute, QWidget] = {}
        self.setWindowTitle("Panda 2.0")
        self.setMinimumSize(LAYOUT.minimum_width, LAYOUT.minimum_height)
        self.resize(LAYOUT.target_width, LAYOUT.target_height)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._build_ui()
        self.refresh()
        self.navigate(AppRoute.OVERVIEW)

    @property
    def current_route(self) -> AppRoute:
        return self._current_route

    @property
    def documents(self) -> tuple[Document, ...]:
        return self._documents

    def view_for(self, route: AppRoute | str) -> QWidget:
        return self._views[AppRoute(route)]

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("panda2ShellRoot")
        root.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        apply_panda_theme(root)
        self.setCentralWidget(root)
        shell_layout = QHBoxLayout(root)
        # Keep the physical split deterministic: flexible content on the left,
        # fixed work rail on the right. Child widgets remain Hebrew-first RTL.
        shell_layout.setDirection(QBoxLayout.Direction.LeftToRight)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        content = QWidget()
        content.setProperty("pandaComponent", "shellContent")
        content.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        shell_layout.addWidget(content, 1)

        self.navigation = NavigationRail()
        self.navigation.routeRequested.connect(self.navigate)
        shell_layout.addWidget(self.navigation)

        self.header = QFrame()
        self.header.setProperty("pandaComponent", "screenHeader")
        self.header.setFixedHeight(LAYOUT.screen_header_height)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(24, 0, 24, 0)
        header_layout.setSpacing(SPACING.adjacent)
        title_block = QWidget()
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 7, 0, 7)
        title_layout.setSpacing(1)
        self.header_title = QLabel()
        apply_typography(self.header_title, TypographyRole.PAGE_TITLE)
        self.header_subtitle = QLabel()
        self.header_subtitle.setProperty("pandaRole", "muted")
        apply_typography(self.header_subtitle, TypographyRole.HELPER)
        title_layout.addWidget(self.header_title)
        title_layout.addWidget(self.header_subtitle)
        header_layout.addWidget(title_block)
        header_layout.addStretch()

        self.scan_button = PandaButton("סריקת Drive", variant=ButtonVariant.SECONDARY)
        self.process_button = PandaButton("עיבוד מסמכים", variant=ButtonVariant.PRIMARY)
        for button in (self.scan_button, self.process_button):
            button.setEnabled(False)
            button.setToolTip(_DEVELOPMENT_ACTION_REASON)
            button.setAccessibleDescription(_DEVELOPMENT_ACTION_REASON)
        header_layout.addWidget(self.scan_button)
        header_layout.addWidget(self.process_button)
        content_layout.addWidget(self.header)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        for definition in ROUTES:
            if definition.view_kind is RouteViewKind.OVERVIEW:
                view = OverviewView()
                view.routeRequested.connect(self.navigate)
                self.overview = view
            else:
                view = QueueRoutePlaceholder(definition)
            self._views[definition.route] = view
            self.stack.addWidget(view)

    def navigate(self, route: AppRoute | str) -> None:
        destination = AppRoute(route)
        definition = route_definition(destination)
        changed = destination is not self._current_route
        self._current_route = destination
        self.stack.setCurrentWidget(self._views[destination])
        self.navigation.set_active_route(destination)
        self.header_title.setText(definition.label_he)
        if destination is AppRoute.OVERVIEW:
            self.header_subtitle.setText("תמונת מצב עדכנית של המסמכים המקומיים")
        else:
            count = (
                self._counts.for_route(definition.queue_route)
                if definition.queue_route is not None
                else 0
            )
            self.header_subtitle.setText(
                f"{count} מסמכים · תצוגת התור תושלם בשלב הבא"
            )
        if changed:
            self.routeChanged.emit(destination.value)

    def refresh(self) -> None:
        """Reload the current in-memory store projection without persistence writes."""
        self._documents = tuple(self._document_source.all())
        self._counts = calculate_queue_counts(self._documents)
        self.navigation.set_counts(self._counts)
        self.overview.refresh(self._documents)
        if hasattr(self, "header_title"):
            self.navigate(self._current_route)
