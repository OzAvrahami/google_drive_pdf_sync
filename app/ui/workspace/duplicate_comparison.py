"""Focused, read-only duplicate comparison inside Document Workspace."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.application.duplicate_comparison_service import DuplicateComparison
from app.ui.components import ButtonVariant, PandaButton
from app.ui.theme.direction import TextKind, apply_text_direction
from app.ui.theme.typography import TypographyRole, apply_typography


_FIELD_LABELS = {
    "supplier_name": "ספק",
    "invoice_number": "מספר מסמך",
    "invoice_date": "תאריך",
    "total": "סכום",
    "file_name": "קובץ",
    "folder_path": "מקור",
    "status": "מצב תהליך",
}


class DuplicateComparisonPanel(QFrame):
    """Slim suspicion strip with an optional expanded comparison."""

    openCandidateRequested = Signal(str)
    dismissRequested = Signal()
    confirmRequested = Signal(str)

    def __init__(
        self,
        comparisons: tuple[DuplicateComparison, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.comparisons = comparisons
        self._expanded = False
        self.setProperty("pandaComponent", "workspaceDuplicatePanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(7)

        strip = QHBoxLayout()
        self.summary = QLabel(self._summary_text())
        self.summary.setWordWrap(True)
        apply_typography(self.summary, TypographyRole.COMPACT_BODY)
        self.compare_button = PandaButton("השווה", variant=ButtonVariant.GHOST)
        self.compare_button.setAccessibleName("השוואת מסמכים בחשד לכפילות")
        self.compare_button.clicked.connect(self.toggle_expanded)
        strip.addWidget(self.summary, 1)
        strip.addWidget(self.compare_button)
        root.addLayout(strip)

        self.details = QFrame()
        self.details.setProperty("pandaComponent", "workspaceDuplicateDetails")
        details_layout = QVBoxLayout(self.details)
        details_layout.setContentsMargins(8, 8, 8, 8)
        details_layout.setSpacing(7)
        self.candidate_selector = QComboBox()
        self.candidate_selector.setAccessibleName("בחירת מסמך חשוד להשוואה")
        for index, comparison in enumerate(comparisons):
            candidate = comparison.candidate_document
            label = (
                candidate.file_name
                if candidate is not None and candidate.file_name
                else f"רשומה לא זמינה ({index + 1})"
            )
            self.candidate_selector.addItem(label, comparison.candidate_document_id)
        self.candidate_selector.setVisible(len(comparisons) > 1)
        self.candidate_selector.currentIndexChanged.connect(self._render_current)
        details_layout.addWidget(self.candidate_selector)

        self.reason = QLabel()
        self.reason.setWordWrap(True)
        apply_typography(self.reason, TypographyRole.HELPER)
        details_layout.addWidget(self.reason)
        self.comparison_body = QWidget()
        details_layout.addWidget(self.comparison_body)

        actions = QHBoxLayout()
        self.open_button = PandaButton("פתח מסמך קיים", variant=ButtonVariant.SECONDARY)
        self.dismiss_button = PandaButton("לא כפילות", variant=ButtonVariant.SECONDARY)
        self.confirm_button = PandaButton("אשר כפילות", variant=ButtonVariant.DESTRUCTIVE)
        self.open_button.clicked.connect(self._open_candidate)
        self.dismiss_button.clicked.connect(self.dismissRequested)
        self.confirm_button.clicked.connect(self._confirm_candidate)
        actions.addWidget(self.open_button)
        actions.addWidget(self.dismiss_button)
        actions.addWidget(self.confirm_button)
        details_layout.addLayout(actions)
        self.details.setVisible(False)
        root.addWidget(self.details)
        self._render_current()

    @property
    def current_comparison(self) -> DuplicateComparison | None:
        index = self.candidate_selector.currentIndex()
        return self.comparisons[index] if 0 <= index < len(self.comparisons) else None

    def toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self.details.setVisible(self._expanded)
        self.compare_button.setText("סגור השוואה" if self._expanded else "השווה")

    def _summary_text(self) -> str:
        confidence = next(
            (item.confidence for item in self.comparisons if item.confidence), None
        )
        confidence_text = {"exact": "התאמה מדויקת", "high": "התאמה גבוהה"}.get(
            confidence, ""
        )
        parts = ["חשד לכפילות"]
        if confidence_text:
            parts.append(confidence_text)
        if len(self.comparisons) > 1:
            parts.append(f"{len(self.comparisons)} מועמדים")
        return " · ".join(parts)

    def _render_current(self, _index: int = -1) -> None:
        old = self.comparison_body
        replacement = QWidget()
        grid = QGridLayout(replacement)
        grid.setContentsMargins(0, 0, 0, 0)
        comparison = self.current_comparison
        available = bool(comparison and comparison.candidate_available)
        self.open_button.setEnabled(available)
        self.confirm_button.setEnabled(available)
        missing_reason = "הרשומה התואמת אינה זמינה. ניתן לסמן כלא רלוונטי בנפרד."
        if not available:
            self.reason.setText(missing_reason)
        else:
            self.reason.setText(
                "Panda זיהה ספק, מספר מסמך ותאריך תואמים."
                if comparison.confidence == "exact"
                else "Panda זיהה ספק, תאריך וסכום תואמים."
            )
            current_heading = QLabel("המסמך הנוכחי — זהו המסמך שיסומן כלא רלוונטי")
            candidate_heading = QLabel("המסמך הקיים — יישאר ללא שינוי")
            apply_typography(current_heading, TypographyRole.LABEL)
            apply_typography(candidate_heading, TypographyRole.LABEL)
            grid.addWidget(QLabel(""), 0, 0)
            grid.addWidget(current_heading, 0, 1)
            grid.addWidget(candidate_heading, 0, 2)
            for row, field in enumerate(comparison.fields, start=1):
                label = QLabel(_FIELD_LABELS[field.field_name])
                current = QLabel(self._display(field.current_value))
                candidate = QLabel(self._display(field.candidate_value))
                if field.participates_in_rule and field.matches:
                    current.setProperty("duplicateMatch", True)
                    candidate.setProperty("duplicateMatch", True)
                if field.field_name in {
                    "invoice_number",
                    "invoice_date",
                    "total",
                    "file_name",
                    "folder_path",
                }:
                    apply_text_direction(current, TextKind.TECHNICAL)
                    apply_text_direction(candidate, TextKind.TECHNICAL)
                grid.addWidget(label, row, 0)
                grid.addWidget(current, row, 1)
                grid.addWidget(candidate, row, 2)
        layout = self.details.layout()
        layout.replaceWidget(old, replacement)
        old.deleteLater()
        self.comparison_body = replacement

    def _open_candidate(self) -> None:
        comparison = self.current_comparison
        if comparison and comparison.candidate_available:
            self.openCandidateRequested.emit(comparison.candidate_document_id)

    def _confirm_candidate(self) -> None:
        comparison = self.current_comparison
        if comparison and comparison.candidate_available:
            self.confirmRequested.emit(comparison.candidate_document_id)

    @staticmethod
    def _display(value: Any) -> str:
        return "—" if value in (None, "") else str(value)
