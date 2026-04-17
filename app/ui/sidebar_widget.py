"""
Sidebar navigation widget.

Displays six named views with live document-count badges:
  Dashboard | New Documents | Needs Attention | Processed (Pending) | Irrelevant | History
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

# view_key → (display label, set of statuses that belong to this view)
_VIEWS = [
    ("dashboard",  "📊  לוח בקרה",            frozenset()),
    ("new",        "🆕  מסמכים חדשים",         frozenset({"new"})),
    ("attention",  "⚠   דורש טיפול",           frozenset({"needs_review", "failed", "skipped"})),
    ("results",    "✅  מעובד (ממתין)",         frozenset({"processed", "approved"})),
    ("irrelevant", "🗑️  לא רלוונטי",          frozenset({"confirmed_irrelevant", "excluded"})),
    ("history",    "📋  היסטוריה",             frozenset({"exported"})),
]

_BASE_LABELS = {key: label for key, label, _ in _VIEWS}


class SidebarWidget(QWidget):
    """Navigation list that emits ``view_changed(view_key)`` on selection."""

    view_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    # ── Construction ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 8, 0, 8)
        vbox.setSpacing(0)

        self._list = QListWidget()
        self._list.setFrameShape(QListWidget.Shape.NoFrame)
        self._list.setSpacing(2)
        self._list.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        font = QFont("Arial", 10)

        for key, label, _ in _VIEWS:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFont(font)
            self._list.addItem(item)

        self._list.setStyleSheet(
            "QListWidget { background: #F5F5F5; border-right: 1px solid #E0E0E0; }"
            "QListWidget::item { padding: 10px 12px; border-radius: 4px; }"
            "QListWidget::item:selected { background: #BBDEFB; color: #1565C0; font-weight: bold; }"
            "QListWidget::item:hover:!selected { background: #E3F2FD; }"
        )

        self._list.currentItemChanged.connect(self._on_item_changed)
        # Default: "New Documents" (row 1)
        self._list.setCurrentRow(1)

        vbox.addWidget(self._list)

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _on_item_changed(self, current, _previous) -> None:
        if current:
            self.view_changed.emit(current.data(Qt.ItemDataRole.UserRole))

    # ── Public API ─────────────────────────────────────────────────────────────

    def update_counts(self, counts: dict) -> None:
        """Refresh count badges next to each view label.  ``counts`` is the
        dict returned by ``DocumentStore.count_by_status()``."""
        def _sum(statuses):
            return sum(counts.get(s, 0) for s in statuses)

        badges = {
            "dashboard":  None,
            "new":        _sum({"new"}),
            "attention":  _sum({"needs_review", "failed", "skipped"}),
            "results":    _sum({"processed", "approved"}),
            "irrelevant": _sum({"confirmed_irrelevant", "excluded"}),
            "history":    _sum({"exported"}),
        }

        for i in range(self._list.count()):
            item  = self._list.item(i)
            key   = item.data(Qt.ItemDataRole.UserRole)
            base  = _BASE_LABELS.get(key, key)
            count = badges.get(key)
            item.setText(f"{base}  ({count})" if count else base)

    def select_view(self, view_key: str) -> None:
        """Programmatically switch to a view by key (suppresses signal re-emit)."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == view_key:
                self._list.setCurrentRow(i)
                break
