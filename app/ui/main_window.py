"""
Main application window.

Layout
------
  Toolbar  : Scan Drive | Process New | Retry Selected | Export Approved
  Body     : Sidebar (fixed 175 px, not resizable) | Right area
               Right area: Search bar + Stacked widget
                 Stack page 0: DashboardWidget
                 Stack page 1: Document table (filtered by active view)

Views (sidebar)
---------------
  Dashboard            — overview stats and quick actions
  New Documents        — status = new
  Needs Attention      — status = needs_review | failed | skipped
                         (with internal sub-filters + Attention Reason column)
  Processed (Pending)  — status = processed | approved
  Irrelevant           — status = confirmed_irrelevant | excluded
  History              — status = exported  (final archive only)

Double-click a row → ReviewDialog
Right-click row(s) → context menu (open / retry / bulk process / mark irrelevant)
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.config import EXCEL_OUTPUT_PATH
from app.models.document import Document
from app.services.document_store import DocumentStore
from app.ui.confirm_irrelevant_dialog import ConfirmIrrelevantDialog
from app.ui.dashboard_widget import DashboardWidget
from app.ui.progress_dialog import ProgressDialog
from app.ui.review_dialog import ReviewDialog
from app.ui.sidebar_widget import SidebarWidget
from app.ui.workers import (
    BulkProcessWorker,
    ExportWorker,
    ProcessWorker,
    RetryWorker,
    ScanWorker,
)

logger = logging.getLogger(__name__)

# ── Status styling ─────────────────────────────────────────────────────────────
_STATUS_BG: dict[str, str] = {
    "new":                  "#E3F2FD",   # light blue
    "processed":            "#E8F5E9",   # light green
    "needs_review":         "#FFF3E0",   # light orange
    "failed":               "#FFEBEE",   # light red
    "approved":             "#C8E6C9",   # green
    "exported":             "#E0F2F1",   # teal
    "skipped":              "#F5F5F5",   # light gray  — auto-classified irrelevant
    "excluded":             "#FCE4EC",   # light pink  — legacy user exclusion
    "confirmed_irrelevant": "#FCE4EC",   # light pink  — user-confirmed irrelevant
}
_STATUS_FG: dict[str, str] = {
    "new":                  "#1565C0",
    "processed":            "#2E7D32",
    "needs_review":         "#E65100",
    "failed":               "#B71C1C",
    "approved":             "#1B5E20",
    "exported":             "#004D40",
    "skipped":              "#9E9E9E",
    "excluded":             "#880E4F",
    "confirmed_irrelevant": "#880E4F",
}
_STATUS_LABELS: dict[str, str] = {
    "new":                  "חדש",
    "processed":            "עובד",
    "needs_review":         "לבדיקה",
    "failed":               "שגיאה",
    "approved":             "מאושר",
    "exported":             "יוצא",
    "skipped":              "חשוד — לא רלוונטי",
    "excluded":             "הוחרג (ישן)",
    "confirmed_irrelevant": "לא רלוונטי (מאושר)",
}

# View key → set of statuses shown in the document table
_VIEW_STATUSES: dict[str, frozenset] = {
    "new":        frozenset({"new"}),
    "attention":  frozenset({"needs_review", "failed", "skipped"}),
    "results":    frozenset({"processed", "approved"}),
    "irrelevant": frozenset({"confirmed_irrelevant", "excluded"}),
    "history":    frozenset({"exported"}),
}

# Sub-filters within the Needs Attention view: (key, Hebrew label, statuses)
_ATTENTION_SUB_FILTERS: list[tuple] = [
    ("all",       "הכל",                frozenset({"needs_review", "failed", "skipped"})),
    ("review",    "לבדיקה",             frozenset({"needs_review"})),
    ("failed",    "שגיאה",              frozenset({"failed"})),
    ("skipped",   "חשוד — לא רלוונטי", frozenset({"skipped"})),
    ("duplicate", "כפול",               frozenset()),
]

# Sub-filters within the Processed (Results) view: (key, Hebrew label)
_RESULTS_SUB_FILTERS: list[tuple] = [
    ("all",       "הכל"),
    ("auto",      "עובד אוטומטית"),
    ("corrected", "תוקן ידנית"),
    ("approved",  "מאושר"),
]

# Statuses that cannot be marked irrelevant (already finalised)
_NO_IRRELEVANT = frozenset({"approved", "exported", "excluded", "confirmed_irrelevant"})

# Table column indices
_COL_NAME       = 0
_COL_FOLDER     = 1
_COL_SUPPLIER   = 2
_COL_DATE       = 3
_COL_NUMBER     = 4
_COL_TOTAL      = 5
_COL_STATUS     = 6
_COL_CONFIDENCE = 7
_COL_REASON     = 8   # "Attention Reason" — visible only in Needs Attention view
_COL_DRIVE_ID   = 9   # hidden


class MainWindow(QMainWindow):

    def __init__(self, store: DocumentStore) -> None:
        super().__init__()
        self._store                    = store
        self._active_view              = "new"
        self._view_statuses: Optional[frozenset] = _VIEW_STATUSES["new"]
        self._attention_sub_filter: frozenset = _VIEW_STATUSES["attention"]
        self._attention_sub_filter_key: str = "all"
        self._results_sub_filter_key: str   = "all"
        self._active_workers: list     = []

        self.setWindowTitle("כלי חשבונאות — מסמכים מ-Google Drive")
        self.setMinimumSize(1100, 680)
        self.resize(1400, 820)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._build_ui()
        self._refresh_table()
        self._update_counts()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Toolbar
        self._build_toolbar()

        # Body: sidebar (fixed) + divider + right area
        # QHBoxLayout instead of QSplitter — sidebar width is truly fixed,
        # no drag handle exists that could resize it.
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        vbox.addWidget(body_widget, stretch=1)

        # Left: sidebar — fixed width, cannot be resized
        self._sidebar = SidebarWidget(parent=self)
        self._sidebar.setFixedWidth(175)
        self._sidebar.view_changed.connect(self._on_view_changed)
        body_layout.addWidget(self._sidebar)

        # Thin vertical separator line
        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.VLine)
        _sep.setFrameShadow(QFrame.Shadow.Plain)
        _sep.setFixedWidth(1)
        _sep.setStyleSheet("color: #E0E0E0;")
        body_layout.addWidget(_sep)

        # Right: search bar + stacked widget
        right = QWidget()
        right_vbox = QVBoxLayout(right)
        right_vbox.setContentsMargins(8, 6, 8, 4)
        right_vbox.setSpacing(4)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("חיפוש לפי שם קובץ, ספק, מספר חשבונית…")
        self._search.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._refresh_table)
        right_vbox.addWidget(self._search)

        # Needs Attention sub-filter bar (hidden until attention view is active)
        self._attention_bar = self._build_attention_bar()
        self._attention_bar.setVisible(False)
        right_vbox.addWidget(self._attention_bar)

        # Results sub-filter bar (hidden until results view is active)
        self._results_bar = self._build_results_bar()
        self._results_bar.setVisible(False)
        right_vbox.addWidget(self._results_bar)

        # Stacked widget
        self._stack = QStackedWidget()

        # Page 0 — Dashboard
        self._dashboard = DashboardWidget(self._store, parent=self)
        self._dashboard.scan_requested.connect(self._on_scan)
        self._dashboard.process_requested.connect(self._on_process)
        self._stack.addWidget(self._dashboard)

        # Page 1 — Document table
        self._stack.addWidget(self._build_table())

        right_vbox.addWidget(self._stack, stretch=1)
        body_layout.addWidget(right, stretch=1)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._progress_label = QLabel("")
        self._status_bar.addWidget(self._progress_label, 1)
        self._counts_label = QLabel("")
        self._status_bar.addPermanentWidget(self._counts_label)

        # Start on table (sidebar default is "New Documents")
        self._stack.setCurrentIndex(1)

    def _build_toolbar(self) -> None:
        tb = QToolBar("פעולות")
        tb.setMovable(False)
        tb.setStyleSheet("QToolBar { spacing: 6px; padding: 4px; }")
        self.addToolBar(tb)

        def _btn(label: str, tip: str, slot) -> QPushButton:
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setFixedHeight(34)
            b.setMinimumWidth(130)
            b.clicked.connect(slot)
            return b

        self._btn_scan    = _btn("סרוק Drive ↻",    "סרוק את Google Drive לקבצי PDF חדשים", self._on_scan)
        self._btn_process = _btn("עבד מסמכים חדשים", "הורד ועבד את כל המסמכים החדשים",      self._on_process)
        self._btn_retry   = _btn("נסה שוב שנבחר",   "עבד מחדש את המסמך שנבחר",              self._on_retry)
        self._btn_export  = _btn("ייצא לאקסל ✓",    "ייצא את כל המסמכים המאושרים לאקסל",   self._on_export)

        self._btn_scan.setStyleSheet(_btn_style("#1565C0"))
        self._btn_process.setStyleSheet(_btn_style("#2E7D32"))
        self._btn_export.setStyleSheet(_btn_style("#4CAF50"))

        tb.addWidget(self._btn_scan)
        tb.addWidget(self._btn_process)
        tb.addWidget(self._btn_retry)
        tb.addSeparator()
        tb.addWidget(self._btn_export)

    def _build_table(self) -> QTableWidget:
        headers = [
            "שם קובץ", "נתיב", "ספק", "תאריך", "מסמך מספר",
            "סכום", "סטטוס", "ביטחון", "סיבה", "drive_id",
        ]
        tbl = QTableWidget(0, len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setSortingEnabled(True)
        tbl.doubleClicked.connect(self._on_row_double_click)

        # Context menu
        tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tbl.customContextMenuRequested.connect(self._show_context_menu)

        hh = tbl.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(True)

        tbl.setColumnWidth(_COL_NAME,       200)
        tbl.setColumnWidth(_COL_FOLDER,     100)
        tbl.setColumnWidth(_COL_SUPPLIER,   150)
        tbl.setColumnWidth(_COL_DATE,        90)
        tbl.setColumnWidth(_COL_NUMBER,      90)
        tbl.setColumnWidth(_COL_TOTAL,       85)
        tbl.setColumnWidth(_COL_STATUS,     115)
        tbl.setColumnWidth(_COL_CONFIDENCE,  60)
        tbl.setColumnWidth(_COL_REASON,     260)
        tbl.setColumnHidden(_COL_REASON,   True)   # shown only in Needs Attention view
        tbl.setColumnHidden(_COL_DRIVE_ID, True)

        self._table = tbl
        return tbl

    # ── Table population ───────────────────────────────────────────────────────

    def _refresh_table(self) -> None:
        docs = self._store.all()
        docs.sort(key=lambda d: d.created_at, reverse=True)

        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for doc in docs:
            if not self._passes_filter(doc):
                continue
            self._append_row(doc)

        self._table.setSortingEnabled(True)
        self._update_counts()

    def _append_row(self, doc: Document) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        total = doc.effective("total")
        total_str = f"₪{total:,.2f}" if isinstance(total, (int, float)) else ""
        conf_pct  = int(doc.confidence * 100)
        reason    = _get_attention_reason(doc)

        cells = [
            doc.file_name,
            doc.folder_path or "(root)",
            doc.effective("supplier_name") or "",
            doc.effective("invoice_date") or "",
            doc.effective("invoice_number") or "",
            total_str,
            _STATUS_LABELS.get(doc.status, doc.status),
            f"{conf_pct}%",
            reason,
            doc.drive_file_id,
        ]

        bg = QBrush(QColor(_STATUS_BG.get(doc.status, "#FFFFFF")))
        fg = QBrush(QColor(_STATUS_FG.get(doc.status, "#000000")))

        for col, value in enumerate(cells):
            item = QTableWidgetItem(value)
            item.setBackground(bg)
            if col == _COL_STATUS:
                item.setForeground(fg)
                item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                if doc.error_message and doc.status in ("failed", "skipped", "needs_review"):
                    item.setToolTip(doc.error_message)
            if col == _COL_REASON and reason:
                item.setForeground(QBrush(QColor(_STATUS_FG.get(doc.status, "#555555"))))
                item.setFont(QFont("Arial", 9))
            self._table.setItem(row, col, item)

    def _update_row(self, row: int, doc: Document) -> None:
        """Refresh a single existing table row in-place (used for real-time updates)."""
        if not self._passes_filter(doc):
            self._table.removeRow(row)
            return

        total = doc.effective("total")
        total_str = f"₪{total:,.2f}" if isinstance(total, (int, float)) else ""
        conf_pct  = int(doc.confidence * 100)
        reason    = _get_attention_reason(doc)

        cells = [
            doc.file_name,
            doc.folder_path or "(root)",
            doc.effective("supplier_name") or "",
            doc.effective("invoice_date") or "",
            doc.effective("invoice_number") or "",
            total_str,
            _STATUS_LABELS.get(doc.status, doc.status),
            f"{conf_pct}%",
            reason,
            doc.drive_file_id,
        ]

        bg = QBrush(QColor(_STATUS_BG.get(doc.status, "#FFFFFF")))
        fg = QBrush(QColor(_STATUS_FG.get(doc.status, "#000000")))

        for col, value in enumerate(cells):
            item = self._table.item(row, col)
            if item is None:
                item = QTableWidgetItem(value)
                self._table.setItem(row, col, item)
            else:
                item.setText(value)
            item.setBackground(bg)
            if col == _COL_STATUS:
                item.setForeground(fg)
                item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                if doc.error_message and doc.status in ("failed", "skipped", "needs_review"):
                    item.setToolTip(doc.error_message)
            if col == _COL_REASON and reason:
                item.setForeground(QBrush(QColor(_STATUS_FG.get(doc.status, "#555555"))))
                item.setFont(QFont("Arial", 9))

    def _passes_filter(self, doc: Document) -> bool:
        is_dup = getattr(doc, "is_duplicate_suspected", False)

        # View-based status filter
        if self._active_view == "attention":
            key = self._attention_sub_filter_key
            if key == "duplicate":
                if not is_dup:
                    return False
            elif key == "all":
                # Show status-matched docs OR suspected duplicates
                if doc.status not in self._attention_sub_filter and not is_dup:
                    return False
            else:
                if doc.status not in self._attention_sub_filter:
                    return False
        elif self._view_statuses is not None:
            if doc.status not in self._view_statuses:
                return False
            # Suspected duplicates are redirected to Needs Attention
            if is_dup:
                return False

        # Results sub-filter (applied after status check)
        if self._active_view == "results":
            key = self._results_sub_filter_key
            if key == "auto":
                if getattr(doc, "was_manually_corrected", False) or doc.status == "approved":
                    return False
            elif key == "corrected":
                if not getattr(doc, "was_manually_corrected", False):
                    return False
            elif key == "approved":
                if doc.status != "approved":
                    return False

        # Full-text search (file name, supplier, invoice number)
        q = self._search.text().strip().lower()
        if q:
            haystack = " ".join([
                doc.file_name or "",
                doc.effective("supplier_name") or "",
                doc.effective("invoice_number") or "",
            ]).lower()
            if q not in haystack:
                return False
        return True

    # ── Selection helpers ──────────────────────────────────────────────────────

    def _selected_drive_ids(self) -> list[str]:
        """Return drive_file_id for every currently selected row (unique, ordered)."""
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        ids: list[str] = []
        seen: set[str] = set()
        for row in sorted(rows):
            item = self._table.item(row, _COL_DRIVE_ID)
            if item:
                fid = item.text()
                if fid not in seen:
                    ids.append(fid)
                    seen.add(fid)
        return ids

    def _selected_drive_id(self) -> Optional[str]:
        """Return the drive_file_id of the single selected row, or None."""
        ids = self._selected_drive_ids()
        return ids[0] if ids else None

    # ── View navigation ────────────────────────────────────────────────────────

    def _on_view_changed(self, view: str) -> None:
        self._active_view = view
        is_attention = (view == "attention")
        is_results   = (view == "results")

        self._attention_bar.setVisible(is_attention)
        self._results_bar.setVisible(is_results)
        self._table.setColumnHidden(_COL_REASON, not is_attention)

        if view == "dashboard":
            self._dashboard.refresh()
            self._stack.setCurrentIndex(0)
        else:
            self._view_statuses = _VIEW_STATUSES.get(view)
            if is_attention:
                self._attention_sub_filter     = _VIEW_STATUSES["attention"]
                self._attention_sub_filter_key = "all"
                for k, btn in self._attention_btns.items():
                    btn.setChecked(k == "all")
            if is_results:
                self._results_sub_filter_key = "all"
                for k, btn in self._results_btns.items():
                    btn.setChecked(k == "all")
            self._stack.setCurrentIndex(1)
            self._refresh_table()
            if is_attention:
                self._update_attention_counts()
            if is_results:
                self._update_results_counts()

    def _build_attention_bar(self) -> QWidget:
        """Horizontal sub-filter chip bar shown inside the Needs Attention view."""
        bar = QWidget()
        bar.setStyleSheet(
            "QWidget { background: #FFF8E1; border-bottom: 1px solid #FFE082; }"
        )
        hbox = QHBoxLayout(bar)
        hbox.setContentsMargins(8, 4, 8, 4)
        hbox.setSpacing(6)

        icon = QLabel("⚠")
        icon.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        icon.setStyleSheet("color: #F57F17; background: transparent;")
        hbox.addWidget(icon)

        label = QLabel("דורש טיפול:")
        label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        label.setStyleSheet("color: #5D4037; background: transparent;")
        hbox.addWidget(label)

        hbox.addSpacing(6)

        self._attention_btns: dict[str, QPushButton] = {}
        for key, lbl, statuses in _ATTENTION_SUB_FILTERS:
            btn = QPushButton(lbl)
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.setMinimumWidth(80)
            btn.setStyleSheet(
                "QPushButton { background:#EEEEEE; border:1px solid #BDBDBD;"
                " border-radius:12px; padding:0 10px; font-size:9pt; }"
                "QPushButton:checked { background:#1565C0; color:white; border-color:#1565C0; }"
                "QPushButton:hover:!checked { background:#E3F2FD; }"
            )
            btn.clicked.connect(lambda _, k=key, s=statuses: self._set_attention_sub_filter(k, s))
            self._attention_btns[key] = btn
            hbox.addWidget(btn)

        self._attention_btns["all"].setChecked(True)
        hbox.addStretch()
        return bar

    def _set_attention_sub_filter(self, key: str, statuses: frozenset) -> None:
        """Switch the active sub-filter and refresh the table."""
        self._attention_sub_filter_key = key
        self._attention_sub_filter     = statuses
        for k, btn in self._attention_btns.items():
            btn.setChecked(k == key)
        self._refresh_table()
        self._update_attention_counts()

    def _update_attention_counts(self) -> None:
        """Refresh count badges on each sub-filter chip."""
        if not hasattr(self, "_attention_btns"):
            return
        all_docs = self._store.all()
        counts   = self._store.count_by_status()
        _attn_statuses = frozenset({"needs_review", "failed", "skipped"})
        # Duplicates already in the attention pool are counted by count_by_status().
        # Only add duplicates whose status is outside the attention pool (e.g. "processed").
        dup_extra = sum(
            1 for d in all_docs
            if getattr(d, "is_duplicate_suspected", False)
            and d.status not in _attn_statuses
        )
        dup_total = sum(1 for d in all_docs if getattr(d, "is_duplicate_suspected", False))
        badges: dict[str, int] = {
            "all":       sum(counts.get(s, 0) for s in _attn_statuses) + dup_extra,
            "review":    counts.get("needs_review", 0),
            "failed":    counts.get("failed", 0),
            "skipped":   counts.get("skipped", 0),
            "duplicate": dup_total,
        }
        base_labels = {k: lbl for k, lbl, _ in _ATTENTION_SUB_FILTERS}
        for key, btn in self._attention_btns.items():
            n    = badges.get(key, 0)
            base = base_labels.get(key, key)
            btn.setText(f"{base}  ({n})" if n else base)

    def _build_results_bar(self) -> QWidget:
        """Horizontal sub-filter chip bar shown inside the Processed view."""
        bar = QWidget()
        bar.setStyleSheet(
            "QWidget { background: #F1F8E9; border-bottom: 1px solid #C5E1A5; }"
        )
        hbox = QHBoxLayout(bar)
        hbox.setContentsMargins(8, 4, 8, 4)
        hbox.setSpacing(6)

        icon = QLabel("✅")
        icon.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        icon.setStyleSheet("color: #33691E; background: transparent;")
        hbox.addWidget(icon)

        label = QLabel("מעובד:")
        label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        label.setStyleSheet("color: #33691E; background: transparent;")
        hbox.addWidget(label)

        hbox.addSpacing(6)

        self._results_btns: dict[str, QPushButton] = {}
        for key, lbl in _RESULTS_SUB_FILTERS:
            btn = QPushButton(lbl)
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.setMinimumWidth(80)
            btn.setStyleSheet(
                "QPushButton { background:#EEEEEE; border:1px solid #BDBDBD;"
                " border-radius:12px; padding:0 10px; font-size:9pt; }"
                "QPushButton:checked { background:#2E7D32; color:white; border-color:#2E7D32; }"
                "QPushButton:hover:!checked { background:#E8F5E9; }"
            )
            btn.clicked.connect(lambda _, k=key: self._set_results_sub_filter(k))
            self._results_btns[key] = btn
            hbox.addWidget(btn)

        self._results_btns["all"].setChecked(True)
        hbox.addStretch()
        return bar

    def _set_results_sub_filter(self, key: str) -> None:
        """Switch the active results sub-filter and refresh the table."""
        self._results_sub_filter_key = key
        for k, btn in self._results_btns.items():
            btn.setChecked(k == key)
        self._refresh_table()
        self._update_results_counts()

    def _update_results_counts(self) -> None:
        """Refresh count badges on each results sub-filter chip."""
        if not hasattr(self, "_results_btns"):
            return
        all_docs     = self._store.all()
        results_docs = [
            d for d in all_docs
            if d.status in ("processed", "approved")
            and not getattr(d, "is_duplicate_suspected", False)
        ]
        counts = {
            "all":       len(results_docs),
            "auto":      sum(1 for d in results_docs
                             if not getattr(d, "was_manually_corrected", False)
                             and d.status == "processed"),
            "corrected": sum(1 for d in results_docs
                             if getattr(d, "was_manually_corrected", False)),
            "approved":  sum(1 for d in results_docs if d.status == "approved"),
        }
        base_labels = {k: lbl for k, lbl in _RESULTS_SUB_FILTERS}
        for key, btn in self._results_btns.items():
            n    = counts.get(key, 0)
            base = base_labels.get(key, key)
            btn.setText(f"{base}  ({n})" if n else base)

    # ── Context menu ───────────────────────────────────────────────────────────

    def _show_context_menu(self, pos) -> None:
        ids = self._selected_drive_ids()
        if not ids:
            return

        menu = QMenu(self)
        n = len(ids)

        if n == 1:
            open_act = QAction("פתח / ערוך", self)
            open_act.triggered.connect(self._on_row_double_click)
            menu.addAction(open_act)

            retry_act = QAction("נסה שוב", self)
            retry_act.triggered.connect(self._on_retry)
            menu.addAction(retry_act)

            menu.addSeparator()

        process_label = f"עבד ({n})" if n > 1 else "עבד מחדש"
        process_act = QAction(process_label, self)
        process_act.triggered.connect(self._on_bulk_process)
        menu.addAction(process_act)

        menu.addSeparator()

        irr_label = f"סמן כלא-רלוונטי... ({n})" if n > 1 else "סמן כלא-רלוונטי..."
        irr_act = QAction(irr_label, self)
        irr_act.triggered.connect(self._on_mark_irrelevant)
        menu.addAction(irr_act)

        # Duplicate actions — shown when at least one selected doc is suspected duplicate
        if n == 1:
            drive_id = ids[0]
            doc = self._store.get_by_drive_id(drive_id)
            if doc and getattr(doc, "is_duplicate_suspected", False):
                menu.addSeparator()
                conf_dup_act = QAction("אשר כפול — העבר ללא-רלוונטי", self)
                conf_dup_act.triggered.connect(self._on_confirm_duplicate)
                menu.addAction(conf_dup_act)

                not_dup_act = QAction("לא כפול — החזר לתצוגה הרגילה", self)
                not_dup_act.triggered.connect(self._on_not_duplicate)
                menu.addAction(not_dup_act)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _update_counts(self) -> None:
        counts = self._store.count_by_status()
        total  = self._store.total()
        parts  = [f"סה\"כ: {total}"]
        for status in (
            "new", "processed", "needs_review", "failed",
            "approved", "exported", "skipped", "excluded", "confirmed_irrelevant",
        ):
            n = counts.get(status, 0)
            if n:
                label = _STATUS_LABELS.get(status, status)
                parts.append(f"{label}: {n}")
        self._counts_label.setText("  |  ".join(parts))

        # Update sidebar badges
        if hasattr(self, "_sidebar"):
            # Only count duplicates whose status is in the results pool —
            # those are the ones being redirected out of Results into Attention.
            # Duplicates already in the attention pool (needs_review/failed/skipped)
            # are already counted via count_by_status() and must not be added again.
            dup_from_results = sum(
                1 for d in self._store.all()
                if getattr(d, "is_duplicate_suspected", False)
                and d.status in ("processed", "approved")
            )
            self._sidebar.update_counts(counts, suspected_duplicates=dup_from_results)

        # Update sub-filter counts when attention or results view is active
        if hasattr(self, "_attention_btns") and self._active_view == "attention":
            self._update_attention_counts()
        if hasattr(self, "_results_btns") and self._active_view == "results":
            self._update_results_counts()

    def _set_progress(self, msg: str) -> None:
        self._progress_label.setText(msg)

    # ── Toolbar actions ────────────────────────────────────────────────────────

    def _on_scan(self) -> None:
        self._lock_toolbar()
        worker = ScanWorker(self._store)
        dlg = ProgressDialog("סריקת Google Drive", parent=self)
        worker.progress.connect(dlg.set_status)
        worker.progress.connect(dlg.append_log)
        worker.finished.connect(dlg.on_success)
        worker.error.connect(dlg.on_error)
        self._run_worker(worker)
        dlg.exec()
        self._unlock_toolbar()
        self._refresh_table()
        if dlg.error_message:
            self._set_progress(f"שגיאה: {dlg.error_message}")
        elif dlg.outcome_summary:
            summary = dlg.outcome_summary
            msg = (
                f"סריקה הושלמה — "
                f"נמצאו: {summary['total_found']} | "
                f"חדשים: {summary['new']} | "
                f"עודכנו: {summary['updated']} | "
                f"קיימים: {summary['skipped']}"
            )
            self._set_progress(msg)
            if summary["new"] or summary["updated"]:
                QMessageBox.information(self, "סריקה הושלמה", msg)

    def _on_process(self) -> None:
        pending = len(self._store.get_by_status("new"))
        if pending == 0:
            QMessageBox.information(self, "אין מסמכים חדשים", "אין מסמכים חדשים לעיבוד.")
            return
        self._lock_toolbar()
        worker = ProcessWorker(self._store)
        dlg = ProgressDialog("עיבוד מסמכים", parent=self)
        worker.progress.connect(dlg.set_status)
        worker.progress.connect(dlg.append_log)
        worker.step.connect(dlg.set_step)
        worker.doc_updated.connect(self._on_doc_updated)
        worker.finished.connect(dlg.on_success)
        worker.error.connect(dlg.on_error)
        self._run_worker(worker)
        dlg.exec()
        self._unlock_toolbar()
        self._refresh_table()
        if dlg.error_message:
            self._set_progress(f"שגיאה: {dlg.error_message}")
        elif dlg.outcome_summary:
            summary = dlg.outcome_summary
            msg = (
                f"עיבוד הושלם — "
                f"עובדו: {summary['total']} | "
                f"הצליחו: {summary['success']} | "
                f"לבדיקה: {summary['needs_review']} | "
                f"נכשלו: {summary['failed']}"
            )
            self._set_progress(msg)

    def _on_retry(self) -> None:
        drive_id = self._selected_drive_id()
        if not drive_id:
            QMessageBox.warning(self, "לא נבחר מסמך", "בחר מסמך מהרשימה תחילה.")
            return
        self._lock_toolbar()
        worker = RetryWorker(self._store, drive_id)
        dlg = ProgressDialog("עיבוד מחדש", parent=self)
        worker.progress.connect(dlg.set_status)
        worker.progress.connect(dlg.append_log)
        worker.step.connect(dlg.set_step)
        worker.finished.connect(dlg.on_success)
        worker.error.connect(dlg.on_error)
        self._run_worker(worker)
        dlg.exec()
        self._unlock_toolbar()
        self._refresh_table()
        if dlg.error_message:
            self._set_progress(f"שגיאה: {dlg.error_message}")
        elif dlg.outcome_summary:
            summary = dlg.outcome_summary
            self._set_progress(
                f"עיבוד מחדש הושלם: {summary.get('retried')} → {summary.get('status')}"
            )

    def _on_export(self) -> None:
        approved = self._store.get_by_status("approved")
        if not approved:
            QMessageBox.information(
                self, "אין מסמכים מאושרים",
                "אין מסמכים מאושרים לייצוא.\nאשר מסמכים תחילה על-ידי לחיצה כפולה."
            )
            return
        self._lock_toolbar()
        worker = ExportWorker(self._store, str(EXCEL_OUTPUT_PATH))
        dlg = ProgressDialog("ייצוא לאקסל", parent=self)
        worker.progress.connect(dlg.set_status)
        worker.progress.connect(dlg.append_log)
        worker.finished.connect(dlg.on_success)
        worker.error.connect(dlg.on_error)
        self._run_worker(worker)
        dlg.exec()
        self._unlock_toolbar()
        self._refresh_table()
        if dlg.error_message:
            self._set_progress(f"שגיאה: {dlg.error_message}")
        elif dlg.outcome_summary:
            summary = dlg.outcome_summary
            count = summary.get("exported", 0)
            path  = summary.get("path", "")
            msg   = summary.get("message", f"יוצאו {count} מסמך/ים ל:\n{path}")
            self._set_progress(f"ייצוא הושלם: {count} מסמכים")
            box = QMessageBox(self)
            box.setWindowTitle("ייצוא הושלם")
            box.setText(msg)
            if path:
                open_btn = box.addButton("פתח קובץ", QMessageBox.ButtonRole.ActionRole)
                box.addButton("סגור", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                if box.clickedButton() == open_btn:
                    self._open_file(path)
            else:
                box.exec()

    # ── Bulk actions ───────────────────────────────────────────────────────────

    def _on_bulk_process(self) -> None:
        """Process all currently selected documents."""
        drive_ids = self._selected_drive_ids()
        if not drive_ids:
            return

        # Only attempt docs that make sense to (re-)process
        processable = [
            did for did in drive_ids
            if (doc := self._store.get_by_drive_id(did))
            and doc.status not in ("approved", "exported", "excluded", "confirmed_irrelevant")
        ]

        if not processable:
            QMessageBox.information(
                self, "אין מסמכים לעיבוד",
                "המסמכים שנבחרו כבר מאושרים / יוצאו / הוחרגו ואינם ניתנים לעיבוד מחדש."
            )
            return

        self._lock_toolbar()
        worker = BulkProcessWorker(self._store, processable)
        title  = f"עיבוד {len(processable)} מסמכים"
        dlg    = ProgressDialog(title, parent=self)
        worker.progress.connect(dlg.set_status)
        worker.progress.connect(dlg.append_log)
        worker.step.connect(dlg.set_step)
        worker.finished.connect(dlg.on_success)
        worker.error.connect(dlg.on_error)
        self._run_worker(worker)
        dlg.exec()
        self._unlock_toolbar()
        self._refresh_table()
        if dlg.error_message:
            self._set_progress(f"שגיאה: {dlg.error_message}")
        elif dlg.outcome_summary:
            summary = dlg.outcome_summary
            self._set_progress(
                f"עיבוד הושלם — "
                f"הצליחו: {summary['success']} | "
                f"לבדיקה: {summary['needs_review']} | "
                f"נכשלו: {summary['failed']}"
            )

    def _on_mark_irrelevant(self) -> None:
        """
        Mark selected documents as confirmed-irrelevant after user confirmation.

        BUSINESS RULE: A document is ONLY deleted if the user explicitly confirms
        it is irrelevant.  This method enforces that rule via a confirmation dialog.
        """
        drive_ids = self._selected_drive_ids()
        if not drive_ids:
            return

        # Filter to docs that can actually be marked irrelevant
        eligible = [
            doc
            for did in drive_ids
            if (doc := self._store.get_by_drive_id(did))
            and doc.status not in _NO_IRRELEVANT
        ]

        if not eligible:
            QMessageBox.information(
                self, "לא ניתן לבצע פעולה",
                "המסמכים שנבחרו כבר מאושרים / יוצאו / הוחרגו."
            )
            return

        dlg = ConfirmIrrelevantDialog(eligible, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        from app.services.exclusion_service import confirm_irrelevant

        errors: list[str] = []
        for doc in eligible:
            try:
                confirm_irrelevant(doc)
                doc.status = "confirmed_irrelevant"
                doc.confirmed_irrelevant_at = datetime.now(timezone.utc).isoformat()
                doc.local_path = ""
                self._store.upsert(doc)
            except Exception as exc:
                logger.error(
                    "confirm_irrelevant failed for %s: %s", doc.drive_file_id, exc
                )
                errors.append(f"{doc.file_name}: {exc}")

        if errors:
            QMessageBox.warning(
                self, "שגיאות",
                "הפעולה הושלמה חלקית. שגיאות:\n" + "\n".join(errors),
            )

        self._refresh_table()
        n = len(eligible) - len(errors)
        self._set_progress(f"{n} מסמך/ים סומנו כלא-רלוונטיים.")

    # ── Duplicate actions ──────────────────────────────────────────────────────

    def _on_confirm_duplicate(self) -> None:
        """Confirm selected document is a duplicate → treat as confirmed_irrelevant."""
        drive_id = self._selected_drive_id()
        if not drive_id:
            return
        doc = self._store.get_by_drive_id(drive_id)
        if not doc:
            return

        answer = QMessageBox.question(
            self,
            "אישור כפול",
            f"האם לאשר שהמסמך הוא כפול ולהעביר אותו ללא-רלוונטי?\n\n"
            f"{doc.file_name}\n\n"
            "• הקובץ המקומי יימחק מהדיסק.\n"
            "• המסמך יועבר לתצוגת 'לא רלוונטי'.\n"
            "• הפעולה אינה הפיכה.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            from app.services.exclusion_service import confirm_irrelevant
            confirm_irrelevant(doc)
            doc.status = "confirmed_irrelevant"
            doc.confirmed_irrelevant_at = datetime.now(timezone.utc).isoformat()
            doc.local_path = ""
            doc.is_duplicate_suspected = False
            self._store.upsert(doc)
        except Exception as exc:
            logger.error("confirm_duplicate failed for %s: %s", doc.drive_file_id, exc)
            QMessageBox.warning(self, "שגיאה", f"לא ניתן לאשר כפול:\n{exc}")
            return

        self._refresh_table()
        self._set_progress("המסמך הכפול הועבר ללא-רלוונטי.")

    def _on_not_duplicate(self) -> None:
        """Clear duplicate suspicion — document returns to its normal view."""
        drive_id = self._selected_drive_id()
        if not drive_id:
            return
        doc = self._store.get_by_drive_id(drive_id)
        if not doc:
            return

        doc.is_duplicate_suspected  = False
        doc.suspected_duplicate_of  = None
        doc.duplicate_confidence    = None
        self._store.upsert(doc)
        self._refresh_table()
        self._set_progress("סימון הכפול הוסר — המסמך חזר לתצוגה הרגילה.")

    # ── Review dialog ──────────────────────────────────────────────────────────

    def _on_row_double_click(self) -> None:
        drive_id = self._selected_drive_id()
        if not drive_id:
            return
        doc = self._store.get_by_drive_id(drive_id)
        if not doc:
            return
        dlg = ReviewDialog(doc, self._store, parent=self)
        dlg.exec()
        if dlg.was_saved:
            self._refresh_table()

    # ── Real-time row update ───────────────────────────────────────────────────

    def _on_doc_updated(self, drive_id: str) -> None:
        """Called by ProcessWorker after each document finishes — refreshes that row."""
        doc = self._store.get_by_drive_id(drive_id)
        if doc is None:
            return
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_DRIVE_ID)
            if item and item.text() == drive_id:
                self._update_row(row, doc)
                self._update_counts()
                return

    # ── Worker lifecycle ───────────────────────────────────────────────────────

    def _run_worker(self, worker) -> None:
        self._active_workers.append(worker)
        worker.finished.connect(lambda _: self._active_workers.remove(worker))
        worker.error.connect(lambda _: self._active_workers.remove(worker))
        worker.start()

    def _lock_toolbar(self) -> None:
        for btn in (self._btn_scan, self._btn_process, self._btn_retry, self._btn_export):
            btn.setEnabled(False)

    def _unlock_toolbar(self) -> None:
        for btn in (self._btn_scan, self._btn_process, self._btn_retry, self._btn_export):
            btn.setEnabled(True)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _open_file(self, path: str) -> None:
        from app.ui.file_opener import open_local_file
        open_local_file(path, parent=self)


# ── Attention reason helper ────────────────────────────────────────────────────

def _get_attention_reason(doc: Document) -> str:
    """
    Return a short human-readable explanation of why a document needs attention.
    Used to populate the 'Attention Reason' column in the Needs Attention view.
    """
    if doc.status == "failed":
        msg = doc.error_message or "שגיאת עיבוד"
        return msg[:90] + ("…" if len(msg) > 90 else "")

    if doc.status == "skipped":
        msg = doc.error_message or ""
        prefix = "מסמך לא רלוונטי: "
        if msg.startswith(prefix):
            doc_type = msg[len(prefix):]
            return f"סווג אוטומטית: {doc_type}"
        return msg or "סווג אוטומטית כלא-רלוונטי"

    if getattr(doc, "is_duplicate_suspected", False):
        conf = getattr(doc, "duplicate_confidence", None)
        conf_label = "התאמה מדויקת" if conf == "exact" else "ביטחון גבוה"
        dup_ids = getattr(doc, "suspected_duplicate_of", None) or []
        if dup_ids:
            return f"כפול חשוד ({conf_label}) — כפול של מסמך קיים"
        return f"כפול חשוד ({conf_label})"

    if doc.status == "needs_review":
        _FIELD_LABELS = {
            "supplier_name": "ספק",
            "invoice_date":  "תאריך",
            "invoice_number": "מספר חשבונית",
            "total":         "סכום",
        }
        missing: list[str] = []
        if not doc.effective("supplier_name"):  missing.append(_FIELD_LABELS["supplier_name"])
        if not doc.effective("invoice_date"):   missing.append(_FIELD_LABELS["invoice_date"])
        if not doc.effective("invoice_number"): missing.append(_FIELD_LABELS["invoice_number"])
        if not doc.effective("total"):          missing.append(_FIELD_LABELS["total"])
        conf_pct = int(doc.confidence * 100)
        if missing:
            return f"חסר: {', '.join(missing)}  •  ביטחון {conf_pct}%"
        return f"ביטחון נמוך ({conf_pct}%)"

    return ""


# ── Style helpers ──────────────────────────────────────────────────────────────

def _btn_style(color: str) -> str:
    return (
        f"QPushButton {{ background:{color}; color:white; font-weight:bold;"
        f" padding:4px 12px; border-radius:4px; }}"
        f"QPushButton:hover {{ opacity:0.85; }}"
        f"QPushButton:disabled {{ background:#BDBDBD; }}"
    )
