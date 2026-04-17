"""
Confirmation dialog for marking one or more documents as irrelevant.

Shown before any irrelevant-confirmation action so the user understands
the consequences (PDF deletion, exclusion registry entry, no future re-download).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from app.models.document import Document


class ConfirmIrrelevantDialog(QDialog):
    """
    Displays a warning and a list of documents to be marked irrelevant.

    Call ``exec()`` and check the return value:
      - ``QDialog.DialogCode.Accepted``  → user confirmed
      - ``QDialog.DialogCode.Rejected``  → user cancelled
    """

    def __init__(self, docs: list["Document"], parent=None) -> None:
        super().__init__(parent)
        self._docs = docs
        n = len(docs)
        self.setWindowTitle("אישור — סמן כלא-רלוונטי")
        self.setMinimumWidth(460)
        self.setModal(True)
        self._build_ui(n)

    def _build_ui(self, n: int) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(18, 16, 18, 12)
        vbox.setSpacing(12)
        vbox.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Title
        title_text = f"סמן {n} מסמך{'ים' if n != 1 else ''} כלא-רלוונטי?"
        title = QLabel(title_text)
        title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        title.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        vbox.addWidget(title)

        # Warning text
        warning = QLabel(
            "ביצוע הפעולה יגרום ל:\n"
            "  • מחיקת קבצי ה-PDF המקומיים מהדיסק\n"
            "  • מניעת הורדה מחודשת בסריקות Google Drive עתידיות\n"
            "  • העברת המסמכים לתצוגת היסטוריה (לא-רלוונטי מאושר)\n\n"
            "⚠️  לא ניתן לבטל פעולה זו בקלות."
        )
        warning.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #555555;")
        vbox.addWidget(warning)

        # Document list
        if self._docs:
            doc_list = QListWidget()
            doc_list.setMaximumHeight(130)
            doc_list.setFont(QFont("Arial", 9))
            doc_list.setStyleSheet(
                "QListWidget { border: 1px solid #E0E0E0; border-radius: 4px; }"
                "QListWidget::item { padding: 3px 8px; }"
            )
            for doc in self._docs:
                doc_list.addItem(doc.file_name)
            vbox.addWidget(doc_list)

        # Buttons
        btns = QDialogButtonBox()
        confirm_btn = btns.addButton(
            "אשר — סמן כלא-רלוונטי",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        confirm_btn.setStyleSheet(
            "QPushButton { background:#D32F2F; color:white; font-weight:bold;"
            " padding:6px 14px; border-radius:4px; }"
            "QPushButton:hover { background:#B71C1C; }"
        )
        cancel_btn = btns.addButton("ביטול", QDialogButtonBox.ButtonRole.RejectRole)
        cancel_btn.setStyleSheet(
            "QPushButton { padding:6px 14px; border-radius:4px; }"
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        vbox.addWidget(btns)
