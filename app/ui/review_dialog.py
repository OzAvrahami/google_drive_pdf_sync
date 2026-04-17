"""
Review / correction dialog.

Opens when the accountant double-clicks a document in the main table.
Shows extracted text on the right and editable fields on the left.

The accountant can:
  - Correct any extracted field
  - Change the document status
  - Approve the document in one click
  - Open the local PDF with the system viewer
"""
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.models.document import Document
from app.services.document_store import DocumentStore

logger = logging.getLogger(__name__)

_EDITABLE_STATUSES = [
    "new",
    "processed",
    "needs_review",
    "failed",
    "approved",
    "exported",
    "skipped",
    "excluded",
    "confirmed_irrelevant",
]

_STATUS_LABELS = {
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


class ReviewDialog(QDialog):

    def __init__(
        self,
        doc: Document,
        store: DocumentStore,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._doc   = doc
        self._store = store
        self._saved = False

        self.setWindowTitle(f"סקירה: {doc.file_name}")
        self.setMinimumSize(1000, 620)
        self.setModal(True)

        self._build_ui()
        self._populate()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 8)
        root.setSpacing(8)

        # Header
        header = QLabel(self._doc.file_name)
        header.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        header.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root.addWidget(header)

        # Splitter: fields (left) | raw text (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(splitter, stretch=1)

        splitter.addWidget(self._build_fields_panel())
        splitter.addWidget(self._build_text_panel())
        splitter.setSizes([420, 560])

        # Button row
        root.addWidget(self._build_buttons())

    def _build_fields_panel(self) -> QWidget:
        panel = QGroupBox("שדות מחולצים")
        panel.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        form  = QFormLayout(panel)
        form.setContentsMargins(12, 16, 12, 12)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _field(placeholder: str = "") -> QLineEdit:
            w = QLineEdit()
            w.setPlaceholderText(placeholder)
            w.setMinimumWidth(200)
            return w

        self._f_supplier = _field("שם ספק")
        self._f_number   = _field("מספר חשבונית")
        self._f_date     = _field("DD/MM/YYYY")
        self._f_total    = _field("סכום כולל")
        self._f_vat      = _field("מע\"מ")
        self._f_subtotal = _field("לפני מע\"מ")
        self._f_desc     = _field("תיאור")

        form.addRow("ספק:",         self._f_supplier)
        form.addRow("מספר מסמך:",   self._f_number)
        form.addRow("תאריך:",       self._f_date)
        form.addRow("סכום:",        self._f_total)
        form.addRow("מע\"מ:",       self._f_vat)
        form.addRow("לפני מע\"מ:", self._f_subtotal)
        form.addRow("תיאור:",       self._f_desc)

        # Status & confidence
        form.addRow(QLabel(""))  # spacer

        self._status_combo = QComboBox()
        for s in _EDITABLE_STATUSES:
            self._status_combo.addItem(_STATUS_LABELS.get(s, s), s)
        form.addRow("סטטוס:", self._status_combo)

        conf_pct = int(self._doc.confidence * 100)
        self._conf_label = QLabel(f"{conf_pct}%")
        self._conf_label.setStyleSheet(_confidence_color(self._doc.confidence))
        form.addRow("ביטחון:", self._conf_label)

        # Open PDF button
        open_btn = QPushButton("פתח PDF")
        open_btn.clicked.connect(self._open_pdf)
        form.addRow("", open_btn)

        return panel

    def _build_text_panel(self) -> QWidget:
        panel = QGroupBox("טקסט גולמי שחולץ")
        vbox  = QVBoxLayout(panel)
        vbox.setContentsMargins(8, 12, 8, 8)

        self._text_view = QTextEdit()
        self._text_view.setReadOnly(True)
        self._text_view.setFont(QFont("Courier New", 9))
        self._text_view.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        vbox.addWidget(self._text_view)

        return panel

    def _build_buttons(self) -> QWidget:
        row = QWidget()
        hbox = QHBoxLayout(row)
        hbox.setContentsMargins(0, 4, 0, 0)

        approve_btn = QPushButton("אשר מסמך ✓")
        approve_btn.setStyleSheet(
            "QPushButton { background:#4CAF50; color:white; font-weight:bold;"
            " padding:6px 18px; border-radius:4px; }"
            "QPushButton:hover { background:#43A047; }"
        )
        approve_btn.clicked.connect(self._approve)

        # Confirm irrelevant — destructive, disabled for already-excluded docs.
        self._exclude_btn = QPushButton("סמן כלא-רלוונטי ✕")
        self._exclude_btn.setToolTip(
            "מסמן את המסמך כלא-רלוונטי לצמיתות.\n"
            "הקובץ המקומי יימחק וסריקות Drive עתידיות לא ירשמו אותו מחדש."
        )
        self._exclude_btn.setStyleSheet(
            "QPushButton { background:#D32F2F; color:white; font-weight:bold;"
            " padding:6px 14px; border-radius:4px; }"
            "QPushButton:hover { background:#B71C1C; }"
            "QPushButton:disabled { background:#BDBDBD; color:#757575; }"
        )
        self._exclude_btn.clicked.connect(self._confirm_exclusion)
        if self._doc.status in ("excluded", "confirmed_irrelevant"):
            self._exclude_btn.setEnabled(False)

        save_btn = QPushButton("שמור תיקונים")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)

        cancel_btn = QPushButton("ביטול")
        cancel_btn.clicked.connect(self.reject)

        hbox.addWidget(approve_btn)
        hbox.addWidget(self._exclude_btn)
        hbox.addStretch()
        hbox.addWidget(save_btn)
        hbox.addWidget(cancel_btn)
        return row

    # ── Population ─────────────────────────────────────────────────────────────

    def _populate(self) -> None:
        doc = self._doc

        # Use effective values (corrected overrides extracted)
        self._f_supplier.setText(doc.effective("supplier_name") or "")
        self._f_number.setText(doc.effective("invoice_number") or "")
        self._f_date.setText(doc.effective("invoice_date") or "")
        total = doc.effective("total")
        self._f_total.setText(str(total) if total is not None else "")
        vat = doc.effective("vat")
        self._f_vat.setText(str(vat) if vat is not None else "")
        sub = doc.effective("subtotal")
        self._f_subtotal.setText(str(sub) if sub is not None else "")
        self._f_desc.setText(doc.effective("description") or "")

        # Status combo
        idx = self._status_combo.findData(doc.status)
        if idx >= 0:
            self._status_combo.setCurrentIndex(idx)

        # Raw text
        if doc.raw_text_path and Path(doc.raw_text_path).exists():
            try:
                text = Path(doc.raw_text_path).read_text(encoding="utf-8")
                self._text_view.setPlainText(text)
            except Exception as exc:
                self._text_view.setPlainText(f"[Could not read text file: {exc}]")
        else:
            self._text_view.setPlainText(
                "[No extracted text available yet.\nProcess the document first.]"
            )

    # ── Actions ────────────────────────────────────────────────────────────────

    def _collect_corrections(self) -> dict:
        def _float_or_none(s: str) -> Optional[float]:
            s = s.strip()
            if not s:
                return None
            try:
                return float(s.replace(",", "."))
            except ValueError:
                return None

        return {
            "supplier_name":  self._f_supplier.text().strip() or None,
            "invoice_number": self._f_number.text().strip() or None,
            "invoice_date":   self._f_date.text().strip() or None,
            "total":          _float_or_none(self._f_total.text()),
            "vat":            _float_or_none(self._f_vat.text()),
            "subtotal":       _float_or_none(self._f_subtotal.text()),
            "description":    self._f_desc.text().strip() or None,
        }

    def _save(self) -> None:
        corrections = self._collect_corrections()
        self._doc.corrected_data = {k: v for k, v in corrections.items() if v is not None}
        self._doc.status = self._status_combo.currentData()
        self._store.upsert(self._doc)
        self._record_corrections_for_learning(corrections)
        self._saved = True
        self.accept()

    def _approve(self) -> None:
        corrections = self._collect_corrections()
        self._doc.corrected_data = {k: v for k, v in corrections.items() if v is not None}
        self._doc.status = "approved"
        self._store.upsert(self._doc)
        self._record_corrections_for_learning(corrections)
        self._saved = True
        self.accept()

    def _confirm_exclusion(self) -> None:
        """
        Permanently exclude this document after explicit user confirmation.

        - Writes a registry entry to excluded_files.json.
        - Deletes the local PDF from disk.
        - Sets status to "excluded" and persists the document.
        - Future Drive scans will ignore this file permanently.
        """
        answer = QMessageBox.question(
            self,
            "אישור החרגה קבועה",
            f"האם להחריג את המסמך לצמיתות?\n\n"
            f"{self._doc.file_name}\n\n"
            "• הקובץ המקומי יימחק מהדיסק.\n"
            "• סריקות Drive עתידיות לא ירשמו אותו מחדש.\n"
            "• הפעולה אינה הפיכה.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        from datetime import datetime, timezone
        try:
            from app.services.exclusion_service import confirm_irrelevant
            confirm_irrelevant(self._doc)
        except Exception as exc:
            logger.error("confirm_irrelevant failed for %s: %s", self._doc.drive_file_id, exc)
            QMessageBox.critical(
                self,
                "שגיאה",
                f"לא ניתן היה לרשום את ההחרגה:\n{exc}",
            )
            return

        self._doc.status = "confirmed_irrelevant"
        self._doc.confirmed_irrelevant_at = datetime.now(timezone.utc).isoformat()
        self._doc.local_path = ""
        self._store.upsert(self._doc)
        self._exclude_btn.setEnabled(False)
        self._saved = True
        logger.info(
            "Document confirmed irrelevant by user: %s (id=%s)",
            self._doc.file_name, self._doc.drive_file_id,
        )
        self.accept()

    def _record_corrections_for_learning(self, corrections: dict) -> None:
        """
        For each corrected field that differs from the original extracted value,
        call record_and_learn() so the system can infer reusable rules over time.

        Mapping between review-dialog field names and parser extracted_data keys:
          supplier_name  → business_name
          invoice_date   → invoice_date
          invoice_number → invoice_number
          total          → amount
        """
        # Fields the parser actually extracts (others are manual-only additions).
        _PARSER_FIELD_MAP = {
            "supplier_name":  "business_name",
            "invoice_date":   "invoice_date",
            "invoice_number": "invoice_number",
            "total":          "amount",
        }

        try:
            from app.services.learning_service import record_and_learn
        except Exception as exc:
            logger.warning("Learning service unavailable: %s", exc)
            return

        extracted = self._doc.extracted_data

        for dialog_field, parser_key in _PARSER_FIELD_MAP.items():
            corrected = corrections.get(dialog_field)
            if corrected is None:
                continue

            original = extracted.get(parser_key)
            original_str  = str(original).strip() if original is not None else ""
            corrected_str = str(corrected).strip()

            if original_str == corrected_str:
                continue   # No actual change — nothing to learn.

            try:
                record_and_learn(
                    field_name      = dialog_field,
                    original_value  = original_str,
                    corrected_value = corrected_str,
                    drive_file_id   = self._doc.drive_file_id,
                    file_name       = self._doc.file_name,
                )
            except Exception as exc:
                logger.warning("record_and_learn failed for field %r: %s", dialog_field, exc)

    def _open_pdf(self) -> None:
        from app.ui.file_opener import open_local_file
        open_local_file(self._doc.local_path, parent=self)

    @property
    def was_saved(self) -> bool:
        return self._saved


# ── Helpers ────────────────────────────────────────────────────────────────────

def _confidence_color(confidence: float) -> str:
    if confidence >= 0.75:
        return "color: #2E7D32; font-weight: bold;"   # green
    if confidence >= 0.5:
        return "color: #E65100; font-weight: bold;"   # orange
    return "color: #B71C1C; font-weight: bold;"       # red
