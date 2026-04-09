"""
Main application window.

Layout
------
  Toolbar  : Scan Drive | Process New | Retry Selected | Export Approved
  Filter   : All | New | Needs Review | Failed | Approved | Exported
  Table    : File Name | Supplier | Date | Invoice # | Total | Status | Confidence
  Status bar: document counts

Double-click a row → ReviewDialog
"""
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
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
from app.ui.progress_dialog import ProgressDialog
from app.ui.review_dialog import ReviewDialog
from app.ui.workers import ExportWorker, ProcessWorker, RetryWorker, ScanWorker

logger = logging.getLogger(__name__)

# ── Status styling ─────────────────────────────────────────────────────────────
_STATUS_BG: dict[str, str] = {
    "new":          "#E3F2FD",   # light blue
    "processed":    "#E8F5E9",   # light green
    "needs_review": "#FFF3E0",   # light orange
    "failed":       "#FFEBEE",   # light red
    "approved":     "#C8E6C9",   # green
    "exported":     "#E0F2F1",   # teal
}
_STATUS_FG: dict[str, str] = {
    "new":          "#1565C0",
    "processed":    "#2E7D32",
    "needs_review": "#E65100",
    "failed":       "#B71C1C",
    "approved":     "#1B5E20",
    "exported":     "#004D40",
}
_STATUS_LABELS: dict[str, str] = {
    "new":          "חדש",
    "processed":    "עובד",
    "needs_review": "לבדיקה",
    "failed":       "שגיאה",
    "approved":     "מאושר",
    "exported":     "יוצא",
}
_FILTER_ALL = "__all__"

# Table column indices
_COL_NAME       = 0
_COL_FOLDER     = 1
_COL_SUPPLIER   = 2
_COL_DATE       = 3
_COL_NUMBER     = 4
_COL_TOTAL      = 5
_COL_STATUS     = 6
_COL_CONFIDENCE = 7
_COL_DRIVE_ID   = 8   # hidden, used for lookups


class MainWindow(QMainWindow):

    def __init__(self, store: DocumentStore) -> None:
        super().__init__()
        self._store          = store
        self._active_filter  = _FILTER_ALL
        self._active_workers: list = []

        self.setWindowTitle("כלי חשבונאות — מסמכים מ-Google Drive")
        self.setMinimumSize(1100, 680)
        self.resize(1280, 760)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._build_ui()
        self._refresh_table()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(8, 4, 8, 4)
        vbox.setSpacing(4)

        # Toolbar
        self._build_toolbar()

        # Filter bar
        vbox.addWidget(self._build_filter_bar())

        # Document table
        vbox.addWidget(self._build_table(), stretch=1)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._progress_label = QLabel("")
        self._status_bar.addWidget(self._progress_label, 1)
        self._counts_label = QLabel("")
        self._status_bar.addPermanentWidget(self._counts_label)

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

    def _build_filter_bar(self) -> QWidget:
        row = QWidget()
        hbox = QHBoxLayout(row)
        hbox.setContentsMargins(0, 2, 0, 2)
        hbox.setSpacing(6)

        label = QLabel("סנן:")
        label.setFont(QFont("Arial", 10))
        hbox.addWidget(label)

        self._filter_btns: dict[str, QPushButton] = {}

        filters = [
            (_FILTER_ALL,    "הכל"),
            ("new",          "חדש"),
            ("processed",    "עובד"),
            ("needs_review", "לבדיקה"),
            ("failed",       "שגיאה"),
            ("approved",     "מאושר"),
            ("exported",     "יוצא"),
        ]

        for key, label_text in filters:
            btn = QPushButton(label_text)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setMinimumWidth(70)
            btn.clicked.connect(lambda _, k=key: self._set_filter(k))
            self._filter_btns[key] = btn
            hbox.addWidget(btn)

        self._filter_btns[_FILTER_ALL].setChecked(True)
        hbox.addStretch()
        return row

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
        tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setSortingEnabled(True)
        tbl.doubleClicked.connect(self._on_row_double_click)

        hh = tbl.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(False)

        # Column widths
        tbl.setColumnWidth(_COL_NAME,       220)
        tbl.setColumnWidth(_COL_FOLDER,     120)
        tbl.setColumnWidth(_COL_SUPPLIER,   160)
        tbl.setColumnWidth(_COL_DATE,        95)
        tbl.setColumnWidth(_COL_NUMBER,      95)
        tbl.setColumnWidth(_COL_TOTAL,       90)
        tbl.setColumnWidth(_COL_STATUS,      90)
        tbl.setColumnWidth(_COL_CONFIDENCE,  65)
        tbl.setColumnHidden(_COL_DRIVE_ID, True)

        self._table = tbl
        return tbl

    # ── Table population ───────────────────────────────────────────────────────

    def _refresh_table(self) -> None:
        docs = self._store.all()

        # Sort: newest first (by created_at desc)
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

        conf_pct = int(doc.confidence * 100)

        cells = [
            doc.file_name,
            doc.folder_path or "(root)",
            doc.effective("supplier_name") or "",
            doc.effective("invoice_date") or "",
            doc.effective("invoice_number") or "",
            total_str,
            _STATUS_LABELS.get(doc.status, doc.status),
            f"{conf_pct}%",
            doc.drive_file_id,   # hidden
        ]

        bg = QBrush(QColor(_STATUS_BG.get(doc.status, "#FFFFFF")))
        fg = QBrush(QColor(_STATUS_FG.get(doc.status, "#000000")))

        for col, value in enumerate(cells):
            item = QTableWidgetItem(value)
            item.setBackground(bg)
            if col == _COL_STATUS:
                item.setForeground(fg)
                item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            self._table.setItem(row, col, item)

    def _passes_filter(self, doc: Document) -> bool:
        if self._active_filter == _FILTER_ALL:
            return True
        return doc.status == self._active_filter

    def _selected_drive_id(self) -> Optional[str]:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, _COL_DRIVE_ID)
        return item.text() if item else None

    # ── Filter bar ─────────────────────────────────────────────────────────────

    def _set_filter(self, key: str) -> None:
        self._active_filter = key
        for k, btn in self._filter_btns.items():
            btn.setChecked(k == key)
        self._refresh_table()

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _update_counts(self) -> None:
        counts = self._store.count_by_status()
        total  = self._store.total()
        parts  = [f"סה\"כ: {total}"]
        for status in ("new", "processed", "needs_review", "failed", "approved", "exported"):
            n = counts.get(status, 0)
            if n:
                label = _STATUS_LABELS.get(status, status)
                parts.append(f"{label}: {n}")
        self._counts_label.setText("  |  ".join(parts))

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
        try:
            if sys.platform == "win32":
                import os
                os.startfile(path)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", path])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            QMessageBox.warning(self, "שגיאה", f"לא ניתן לפתוח קובץ:\n{exc}")


# ── Style helpers ──────────────────────────────────────────────────────────────

def _btn_style(color: str) -> str:
    return (
        f"QPushButton {{ background:{color}; color:white; font-weight:bold;"
        f" padding:4px 12px; border-radius:4px; }}"
        f"QPushButton:hover {{ opacity:0.85; }}"
        f"QPushButton:disabled {{ background:#BDBDBD; }}"
    )
