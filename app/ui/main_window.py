"""
Main application window.

Layout
------
  Toolbar  : Scan Drive | Process New | Retry Selected | Export Approved
  Body     : Sidebar (navigation) | Right area
               Right area: Search bar + Stacked widget
                 Stack page 0: DashboardWidget
                 Stack page 1: Document table (filtered by active view)

Views (sidebar)
---------------
  Dashboard        — overview stats and quick actions
  New Documents    — status = new
  Results          — status = processed | needs_review | failed
  History          — status = approved | exported | skipped | excluded | confirmed_irrelevant

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
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
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
    "new":     frozenset({"new"}),
    "results": frozenset({"processed", "needs_review", "failed"}),
    "history": frozenset({"approved", "exported", "skipped", "excluded", "confirmed_irrelevant"}),
}

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
_COL_DRIVE_ID   = 8   # hidden


class MainWindow(QMainWindow):

    def __init__(self, store: DocumentStore) -> None:
        super().__init__()
        self._store           = store
        self._active_view     = "new"
        self._view_statuses: Optional[frozenset] = _VIEW_STATUSES["new"]
        self._active_workers: list = []

        self.setWindowTitle("כלי חשבונאות — מסמכים מ-Google Drive")
        self.setMinimumSize(1100, 680)
        self.resize(1340, 780)
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

        # Body: sidebar + right area
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)
        body.setHandleWidth(1)
        body.setStyleSheet("QSplitter::handle { background: #E0E0E0; }")
        vbox.addWidget(body, stretch=1)

        # Left: sidebar
        self._sidebar = SidebarWidget(parent=self)
        self._sidebar.setFixedWidth(175)
        self._sidebar.view_changed.connect(self._on_view_changed)
        body.addWidget(self._sidebar)

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
        body.addWidget(right)

        body.setSizes([175, 1165])

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
            "סכום", "סטטוס", "ביטחון", "drive_id",
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
        hh.setStretchLastSection(False)

        tbl.setColumnWidth(_COL_NAME,       220)
        tbl.setColumnWidth(_COL_FOLDER,     120)
        tbl.setColumnWidth(_COL_SUPPLIER,   160)
        tbl.setColumnWidth(_COL_DATE,        95)
        tbl.setColumnWidth(_COL_NUMBER,      95)
        tbl.setColumnWidth(_COL_TOTAL,       90)
        tbl.setColumnWidth(_COL_STATUS,     120)
        tbl.setColumnWidth(_COL_CONFIDENCE,  65)
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

        cells = [
            doc.file_name,
            doc.folder_path or "(root)",
            doc.effective("supplier_name") or "",
            doc.effective("invoice_date") or "",
            doc.effective("invoice_number") or "",
            total_str,
            _STATUS_LABELS.get(doc.status, doc.status),
            f"{conf_pct}%",
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
                # Show error_message as tooltip for failed / skipped docs
                if doc.error_message and doc.status in ("failed", "skipped", "needs_review"):
                    item.setToolTip(doc.error_message)
            self._table.setItem(row, col, item)

    def _update_row(self, row: int, doc: Document) -> None:
        """Refresh a single existing table row in-place (used for real-time updates)."""
        if not self._passes_filter(doc):
            self._table.removeRow(row)
            return

        total = doc.effective("total")
        total_str = f"₪{total:,.2f}" if isinstance(total, (int, float)) else ""
        conf_pct  = int(doc.confidence * 100)

        cells = [
            doc.file_name,
            doc.folder_path or "(root)",
            doc.effective("supplier_name") or "",
            doc.effective("invoice_date") or "",
            doc.effective("invoice_number") or "",
            total_str,
            _STATUS_LABELS.get(doc.status, doc.status),
            f"{conf_pct}%",
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

    def _passes_filter(self, doc: Document) -> bool:
        # View-based status filter
        if self._view_statuses is not None and doc.status not in self._view_statuses:
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
        if view == "dashboard":
            self._dashboard.refresh()
            self._stack.setCurrentIndex(0)
        else:
            self._view_statuses = _VIEW_STATUSES.get(view)
            self._stack.setCurrentIndex(1)
            self._refresh_table()

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
            self._sidebar.update_counts(counts)

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


# ── Style helpers ──────────────────────────────────────────────────────────────

def _btn_style(color: str) -> str:
    return (
        f"QPushButton {{ background:{color}; color:white; font-weight:bold;"
        f" padding:4px 12px; border-radius:4px; }}"
        f"QPushButton:hover {{ opacity:0.85; }}"
        f"QPushButton:disabled {{ background:#BDBDBD; }}"
    )
