"""
Reusable progress dialog for long-running background tasks.

Usage
-----
    dlg = ProgressDialog("עיבוד מסמכים", parent=self)

    # Connect worker signals before starting:
    worker.progress.connect(dlg.set_status)
    worker.progress.connect(dlg.append_log)
    worker.step.connect(dlg.set_step)          # optional — switches to determinate
    worker.finished.connect(dlg.on_success)
    worker.error.connect(dlg.on_error)

    worker.start()
    dlg.exec()   # modal — keeps event loop alive while worker runs

    # After exec() returns:
    if dlg.error_message:
        handle_error(dlg.error_message)
    elif dlg.outcome_summary:
        handle_success(dlg.outcome_summary)

The dialog:
  - Starts in indeterminate (animated) mode.
  - Switches to determinate when set_step() is called.
  - Captures Python log records from the "app" namespace and displays them
    in the live log area (thread-safe via Qt signal bridge).
  - Blocks closing while the task is running.
  - Enables the Close button on completion or error.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollBar,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# ── Log routing ───────────────────────────────────────────────────────────────

class _LogBridge(QObject):
    """
    Thread-safe bridge between Python's logging system and a Qt slot.

    Worker threads emit log records; Qt's queued-connection mechanism
    ensures the signal is delivered on the main thread where the UI lives.
    """
    new_record: Signal = Signal(str)


class _UILogHandler(logging.Handler):
    """Logging handler that emits formatted records through a _LogBridge."""

    def __init__(self, bridge: _LogBridge) -> None:
        super().__init__()
        self._bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if record.levelno >= logging.WARNING:
                msg = f"[{record.levelname}] {msg}"
            self._bridge.new_record.emit(msg)
        except Exception:
            self.handleError(record)


# ── Dialog ────────────────────────────────────────────────────────────────────

class ProgressDialog(QDialog):
    """
    Modal progress dialog with indeterminate/determinate progress bar,
    status text, per-file label, and a live log area.
    """

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(540, 420)
        self.setModal(True)

        self._is_running      = True
        self._outcome_summary: Optional[dict] = None
        self._error_message:   Optional[str]  = None
        self._handler_removed = False

        self._build_ui(title)
        self._install_log_handler()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self, title: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        title_lbl.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root.addWidget(title_lbl)

        # Progress bar (indeterminate until set_step() is called)
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)          # animated indeterminate
        self._bar.setFixedHeight(20)
        self._bar.setTextVisible(False)
        root.addWidget(self._bar)

        # Step counters  "12 מתוך 47 | 35 נותרו"
        self._step_lbl = QLabel("")
        self._step_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._step_lbl.setStyleSheet("color: #555; font-size: 10pt;")
        self._step_lbl.hide()
        root.addWidget(self._step_lbl)

        # Status message  (changes often)
        self._status_lbl = QLabel("מאתחל…")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._status_lbl.setStyleSheet("color: #444;")
        root.addWidget(self._status_lbl)

        # Current file name  (shown when processing individual files)
        self._file_lbl = QLabel("")
        self._file_lbl.setWordWrap(True)
        self._file_lbl.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._file_lbl.setStyleSheet("color: #777; font-style: italic;")
        self._file_lbl.hide()
        root.addWidget(self._file_lbl)

        # Live log area
        log_box = QGroupBox("פעילות")
        log_box.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        log_inner = QVBoxLayout(log_box)
        log_inner.setContentsMargins(4, 6, 4, 4)

        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(300)
        self._log_view.setFixedHeight(160)
        self._log_view.setFont(QFont("Courier New", 8))
        self._log_view.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._log_view.setStyleSheet(
            "QPlainTextEdit { background:#1E1E1E; color:#D4D4D4; border:none; }"
        )
        log_inner.addWidget(self._log_view)
        root.addWidget(log_box, stretch=1)

        # Close button (disabled while running)
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.addStretch()

        self._close_btn = QPushButton("סגור")
        self._close_btn.setEnabled(False)
        self._close_btn.setFixedWidth(110)
        self._close_btn.setFixedHeight(30)
        self._close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self._close_btn)
        root.addWidget(btn_row)

    # ── Log handler lifecycle ─────────────────────────────────────────────────

    def _install_log_handler(self) -> None:
        self._bridge  = _LogBridge()
        self._bridge.new_record.connect(self.append_log)
        self._handler = _UILogHandler(self._bridge)
        self._handler.setLevel(logging.INFO)
        logging.getLogger("app").addHandler(self._handler)

    def _remove_log_handler(self) -> None:
        if not self._handler_removed:
            logging.getLogger("app").removeHandler(self._handler)
            self._handler_removed = True

    # ── Qt event overrides ────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        if self._is_running:
            event.ignore()    # X button / Alt-F4 ignored while task is live
            return
        self._remove_log_handler()
        super().closeEvent(event)

    def accept(self) -> None:
        self._remove_log_handler()
        super().accept()

    def reject(self) -> None:
        if self._is_running:
            return            # Ignore Escape while task is live
        self._remove_log_handler()
        super().reject()

    # ── Slots (connected to worker signals) ───────────────────────────────────

    def set_status(self, msg: str) -> None:
        """Update the status text. Called on every worker progress() emission."""
        self._status_lbl.setText(msg)

    def set_step(self, current: int, total: int, filename: str) -> None:
        """
        Switch to determinate mode and update counters + current file.
        Connect worker.step to this slot (only ProcessWorker emits step).
        """
        self._bar.setRange(0, total)
        self._bar.setValue(current)
        remaining = total - current
        self._step_lbl.setText(f"{current} מתוך {total}  |  {remaining} נותרו")
        self._step_lbl.show()
        if filename:
            self._file_lbl.setText(f"קובץ נוכחי:  {filename}")
            self._file_lbl.show()

    def append_log(self, msg: str) -> None:
        """Append one line to the live log area and auto-scroll to bottom."""
        if not msg.strip():
            return
        self._log_view.appendPlainText(msg)
        sb: QScrollBar = self._log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def on_success(self, summary: dict) -> None:
        """Call when the worker emits finished(dict)."""
        self._outcome_summary = summary
        self._is_running      = False
        self._bar.setRange(0, 100)
        self._bar.setValue(100)
        self._status_lbl.setText("הסתיים בהצלחה ✓")
        self._status_lbl.setStyleSheet("color: #2E7D32; font-weight: bold;")
        self._close_btn.setEnabled(True)
        self._close_btn.setFocus()

    def on_error(self, message: str) -> None:
        """Call when the worker emits error(str)."""
        self._error_message = message
        self._is_running    = False
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._status_lbl.setText(f"שגיאה: {message}")
        self._status_lbl.setStyleSheet("color: #B71C1C; font-weight: bold;")
        self.append_log(f"ERROR: {message}")
        self._close_btn.setEnabled(True)
        self._close_btn.setFocus()

    # ── Result accessors (read after exec() returns) ──────────────────────────

    @property
    def outcome_summary(self) -> Optional[dict]:
        """The summary dict from the worker, or None on error."""
        return self._outcome_summary

    @property
    def error_message(self) -> Optional[str]:
        """The error string from the worker, or None on success."""
        return self._error_message
