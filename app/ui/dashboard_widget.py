"""
Dashboard widget — default home screen.

Shows document counts grouped by status, quick-action buttons,
and a short list of recently updated documents.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from app.services.document_store import DocumentStore


class _StatCard(QFrame):
    """Small card widget showing a label and a big count number."""

    def __init__(self, title: str, bg_color: str, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{ background:{bg_color}; border-radius:8px; }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(80)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(14, 8, 14, 8)
        vbox.setSpacing(2)

        self._title_lbl = QLabel(title)
        self._title_lbl.setFont(QFont("Arial", 9))
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._count_lbl = QLabel("0")
        self._count_lbl.setFont(QFont("Arial", 22, QFont.Weight.Bold))
        self._count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        vbox.addWidget(self._title_lbl)
        vbox.addWidget(self._count_lbl)

    def set_count(self, n: int) -> None:
        self._count_lbl.setText(str(n))


class DashboardWidget(QWidget):
    """Home screen with status overview and quick actions."""

    scan_requested    = Signal()
    process_requested = Signal()

    def __init__(self, store: "DocumentStore", parent=None) -> None:
        super().__init__(parent)
        self._store = store
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._build_ui()
        self.refresh()

    # ── Construction ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── Title ──────────────────────────────────────────────────────────────
        title = QLabel("לוח בקרה")
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignRight)
        title.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root.addWidget(title)

        # ── Stat cards ─────────────────────────────────────────────────────────
        cards_row = QWidget()
        hbox = QHBoxLayout(cards_row)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(12)

        self._cards: dict[str, _StatCard] = {}
        card_defs = [
            ("total",        'סה"כ',     "#EEEEEE"),
            ("new",          "חדשים",    "#E3F2FD"),
            ("needs_review", "לבדיקה",   "#FFF3E0"),
            ("failed",       "שגיאה",    "#FFEBEE"),
            ("approved",     "מאושרים",  "#C8E6C9"),
            ("exported",     "יוצאו",    "#E0F2F1"),
        ]
        for key, label, color in card_defs:
            card = _StatCard(label, color)
            self._cards[key] = card
            hbox.addWidget(card)

        root.addWidget(cards_row)

        # ── Quick actions ──────────────────────────────────────────────────────
        actions_label = QLabel("פעולות מהירות")
        actions_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        actions_label.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root.addWidget(actions_label)

        actions_row = QWidget()
        actions_hbox = QHBoxLayout(actions_row)
        actions_hbox.setContentsMargins(0, 0, 0, 0)
        actions_hbox.setSpacing(10)

        scan_btn = QPushButton("סרוק Drive ↻")
        scan_btn.setFixedHeight(36)
        scan_btn.setStyleSheet(
            "QPushButton { background:#1565C0; color:white; font-weight:bold;"
            " padding:4px 18px; border-radius:4px; }"
            "QPushButton:hover { background:#0D47A1; }"
        )
        scan_btn.clicked.connect(self.scan_requested)

        process_btn = QPushButton("עבד מסמכים חדשים")
        process_btn.setFixedHeight(36)
        process_btn.setStyleSheet(
            "QPushButton { background:#2E7D32; color:white; font-weight:bold;"
            " padding:4px 18px; border-radius:4px; }"
            "QPushButton:hover { background:#1B5E20; }"
        )
        process_btn.clicked.connect(self.process_requested)

        actions_hbox.addWidget(scan_btn)
        actions_hbox.addWidget(process_btn)
        actions_hbox.addStretch()
        root.addWidget(actions_row)

        # ── Recent activity ────────────────────────────────────────────────────
        recent_label = QLabel("עדכונים אחרונים")
        recent_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        recent_label.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root.addWidget(recent_label)

        self._recent_list = QListWidget()
        self._recent_list.setMinimumHeight(160)
        self._recent_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._recent_list.setFont(QFont("Arial", 9))
        self._recent_list.setStyleSheet(
            "QListWidget { border: 1px solid #E0E0E0; border-radius: 4px; }"
            "QListWidget::item { padding: 4px 8px; }"
            "QListWidget::item:alternate { background: #FAFAFA; }"
        )
        self._recent_list.setAlternatingRowColors(True)
        root.addWidget(self._recent_list)

        root.addStretch()

    # ── Public API ─────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload counts and recent-activity list from the store."""
        counts = self._store.count_by_status()
        total  = self._store.total()

        self._cards["total"].set_count(total)
        for key in ("new", "needs_review", "failed", "approved", "exported"):
            self._cards[key].set_count(counts.get(key, 0))

        # Recent docs — last 10 by updated_at
        self._recent_list.clear()
        from app.config import DOCUMENTS_JSON  # avoid circular import at module level
        docs = sorted(self._store.all(), key=lambda d: d.updated_at, reverse=True)[:10]
        for doc in docs:
            from app.ui.main_window import _STATUS_LABELS  # shared labels
            status_label = _STATUS_LABELS.get(doc.status, doc.status)
            self._recent_list.addItem(f"{doc.file_name}  —  {status_label}")
