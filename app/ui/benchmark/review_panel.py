"""Ground-truth fields and review actions for the benchmark workspace."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services.pdf_corpus_service import REVIEW_FIELDS, panda_field_text
from app.ui.components import ButtonVariant, InlineFeedback, PandaButton, PandaTextField
from app.ui.components.feedback import FeedbackVariant
from app.ui.theme.direction import TextKind, apply_text_direction
from app.ui.theme.stylesheet import set_dynamic_property
from app.ui.theme.tokens import SPACING
from app.ui.theme.typography import TypographyRole, apply_typography


_TEXT_KINDS = {
    "expected_supplier": TextKind.AUTO,
    "expected_invoice_number": TextKind.DOCUMENT_NUMBER,
    "expected_invoice_date": TextKind.DATE,
    "expected_amount": TextKind.AMOUNT,
}


class GroundTruthField(QFrame):
    changed = Signal()

    def __init__(
        self,
        expected_key: str,
        label: str,
        parser_key: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.expected_key = expected_key
        self.parser_key = parser_key
        self.setProperty("pandaComponent", "benchmarkReviewField")
        self.setProperty("comparisonState", "unreviewed")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(SPACING.tight)

        heading = QHBoxLayout()
        self.label = QLabel(label)
        apply_typography(self.label, TypographyRole.LABEL)
        self.state_label = QLabel("טרם נבדק")
        self.state_label.setProperty("pandaComponent", "benchmarkComparisonState")
        apply_typography(self.state_label, TypographyRole.HELPER)
        heading.addWidget(self.label)
        heading.addStretch()
        heading.addWidget(self.state_label)
        root.addLayout(heading)

        panda_row = QHBoxLayout()
        panda_caption = QLabel("Panda")
        panda_caption.setProperty("pandaRole", "muted")
        apply_typography(panda_caption, TypographyRole.HELPER)
        self.panda_value = QLabel("—")
        self.panda_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.panda_value.setWordWrap(True)
        apply_typography(self.panda_value, TypographyRole.COMPACT_BODY)
        apply_text_direction(self.panda_value, _TEXT_KINDS[expected_key])
        panda_row.addWidget(panda_caption)
        panda_row.addWidget(self.panda_value, 1)
        root.addLayout(panda_row)

        self.editor = PandaTextField(
            accessible_name=f"Expected {label}",
            text_kind=_TEXT_KINDS[expected_key],
        )
        self.editor.setPlaceholderText("ערך מאומת")
        root.addWidget(self.editor)

        self.intentional_blank = QCheckBox("לא חל / ריק במכוון")
        self.intentional_blank.setAccessibleDescription(
            "שמירת שדה ריק כבחירה מפורשת של הסוקר"
        )
        apply_typography(self.intentional_blank, TypographyRole.HELPER)
        root.addWidget(self.intentional_blank)

        self.editor.textChanged.connect(lambda _text: self.changed.emit())
        self.intentional_blank.toggled.connect(self._blank_toggled)

    def set_record(self, record: Mapping[str, object]) -> None:
        parser = record.get("parser_result") or {}
        panda = panda_field_text(
            self.parser_key,
            parser.get(self.parser_key) if isinstance(parser, Mapping) else None,
        )
        reviewed = record.get("reviewed") is True
        expected = str(record.get(self.expected_key) or "") if reviewed else panda
        self.panda_value.setText(panda or "—")
        self.editor.blockSignals(True)
        self.intentional_blank.blockSignals(True)
        self.editor.setText(expected)
        self.intentional_blank.setChecked(bool(reviewed and expected == ""))
        self.editor.setEnabled(not self.intentional_blank.isChecked())
        self.editor.blockSignals(False)
        self.intentional_blank.blockSignals(False)
        correctness = record.get(self._correctness_key)
        if not reviewed:
            state, label = "unreviewed", "טרם נבדק"
        elif expected == "":
            state = "correct" if correctness is True else "mismatch"
            label = "ריק במכוון" if correctness is True else "אי התאמה"
        elif correctness is True:
            state, label = "correct", "תואם"
        else:
            state, label = "mismatch", "אי התאמה"
        self.state_label.setText(label)
        set_dynamic_property(self, "comparisonState", state)
        set_dynamic_property(self.state_label, "comparisonState", state)

    @property
    def value(self) -> str:
        return "" if self.intentional_blank.isChecked() else self.editor.text().strip()

    @property
    def draft_state(self) -> tuple[str, bool]:
        return self.editor.text(), self.intentional_blank.isChecked()

    @property
    def _correctness_key(self) -> str:
        return {
            "expected_supplier": "supplier_correct",
            "expected_invoice_number": "invoice_number_correct",
            "expected_invoice_date": "invoice_date_correct",
            "expected_amount": "amount_correct",
        }[self.expected_key]

    def _blank_toggled(self, checked: bool) -> None:
        self.editor.setEnabled(not checked)
        self.changed.emit()


class BenchmarkReviewPanel(QFrame):
    everythingCorrectRequested = Signal()
    saveNextRequested = Signal()
    refreshRequested = Signal()
    draftChanged = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "benchmarkReviewPanel")
        self.setMinimumWidth(300)
        self.setMaximumWidth(390)
        self._record: Mapping[str, object] | None = None
        self._baseline: dict[str, tuple[str, bool]] = {}
        self._feedback: InlineFeedback | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        summary = QFrame()
        summary.setProperty("pandaComponent", "benchmarkReviewSummary")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(16, 14, 16, 12)
        summary_layout.setSpacing(SPACING.tight)
        title_row = QHBoxLayout()
        self.title = QLabel("סקירת אמת מידה")
        apply_typography(self.title, TypographyRole.SECTION_TITLE)
        self.dirty_label = QLabel("שינויים לא נשמרו")
        self.dirty_label.setProperty("pandaComponent", "workspaceDirtyIndicator")
        self.dirty_label.setVisible(False)
        apply_typography(self.dirty_label, TypographyRole.BADGE)
        title_row.addWidget(self.title)
        title_row.addStretch()
        title_row.addWidget(self.dirty_label)
        summary_layout.addLayout(title_row)
        self.metadata = QLabel()
        self.metadata.setWordWrap(True)
        self.metadata.setProperty("pandaRole", "muted")
        apply_typography(self.metadata, TypographyRole.HELPER)
        summary_layout.addWidget(self.metadata)
        root.addWidget(summary)

        self.scroll = QScrollArea()
        self.scroll.setProperty("pandaComponent", "benchmarkReviewScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setProperty("pandaComponent", "benchmarkReviewBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 12, 16, 16)
        body_layout.setSpacing(SPACING.standard)

        self.state_feedback = QLabel()
        self.state_feedback.setProperty("pandaComponent", "benchmarkDocumentState")
        self.state_feedback.setWordWrap(True)
        self.state_feedback.setVisible(False)
        apply_typography(self.state_feedback, TypographyRole.COMPACT_BODY)
        body_layout.addWidget(self.state_feedback)

        self.fields: dict[str, GroundTruthField] = {}
        for expected, label, parser_key in REVIEW_FIELDS:
            field = GroundTruthField(expected, label, parser_key)
            field.changed.connect(self._draft_changed)
            self.fields[expected] = field
            body_layout.addWidget(field)

        self.feedback_host = QVBoxLayout()
        self.feedback_host.setContentsMargins(0, 0, 0, 0)
        body_layout.addLayout(self.feedback_host)
        body_layout.addStretch()
        self.scroll.setWidget(body)
        root.addWidget(self.scroll, 1)

        actions = QFrame()
        actions.setProperty("pandaComponent", "benchmarkReviewActions")
        action_layout = QVBoxLayout(actions)
        action_layout.setContentsMargins(16, 12, 16, 14)
        action_layout.setSpacing(SPACING.adjacent)
        self.everything_correct_button = PandaButton(
            "הכול נכון",
            variant=ButtonVariant.PRIMARY,
        )
        self.everything_correct_button.setToolTip("אישור כל ערכי Panda ומעבר למסמך הבא (Alt+A)")
        self.save_next_button = PandaButton(
            "שמירה והבא",
            variant=ButtonVariant.SECONDARY,
        )
        self.save_next_button.setToolTip("שמירת ערכי האמת ומעבר למסמך הבא (Ctrl+Enter)")
        self.refresh_button = PandaButton("רענון ניתוח", variant=ButtonVariant.GHOST)
        self.refresh_button.setToolTip("הרצת החילוץ והפענוח הנוכחיים מחדש למסמך זה")
        action_layout.addWidget(self.everything_correct_button)
        action_layout.addWidget(self.save_next_button)
        action_layout.addWidget(self.refresh_button)
        root.addWidget(actions)

        self.everything_correct_button.clicked.connect(self.everythingCorrectRequested)
        self.save_next_button.clicked.connect(self.saveNextRequested)
        self.refresh_button.clicked.connect(self.refreshRequested)
        self.set_enabled(False)

    @property
    def is_dirty(self) -> bool:
        return bool(self._record) and self._current_draft() != self._baseline

    def expected_values(self) -> dict[str, str]:
        return {key: field.value for key, field in self.fields.items()}

    def set_record(self, record: Mapping[str, object]) -> None:
        self._record = record
        self.title.setText(str(record.get("filename") or "סקירת אמת מידה"))
        source = record.get("source_detection") or {}
        source_name = source.get("source_system", "Unknown") if isinstance(source, Mapping) else "Unknown"
        source_confidence = source.get("source_confidence", "unknown") if isinstance(source, Mapping) else "unknown"
        native = bool((record.get("extraction_metrics") or {}).get("native_text"))
        self.metadata.setText(
            f"Panda: {record.get('status') or 'unanalyzed'} · "
            f"ביטחון {float(record.get('confidence') or 0) * 100:.0f}%\n"
            f"מקור: {source_name} ({source_confidence}) · "
            f"{'טקסט דיגיטלי' if native else 'ללא טקסט דיגיטלי משמעותי'}"
        )
        if not native:
            self.state_feedback.setText(
                "PDF לא-דיגיטלי / מבוסס תמונה. חילוץ טקסט מקורי אינו זמין; OCR אינו מיושם."
            )
            set_dynamic_property(self.state_feedback, "state", "warning")
            self.state_feedback.setVisible(True)
        elif record.get("status") == "skipped":
            self.state_feedback.setText("המסמך דולג לפי מדיניות המסמכים; זו אינה שגיאת פענוח.")
            set_dynamic_property(self.state_feedback, "state", "info")
            self.state_feedback.setVisible(True)
        else:
            self.state_feedback.setVisible(False)
        for field in self.fields.values():
            field.set_record(record)
        self._baseline = self._current_draft()
        self._set_dirty(False)
        self.set_enabled(True)

    def set_loading(self, filename: str) -> None:
        self.title.setText(filename or "סקירת אמת מידה")
        self.metadata.setText("מריץ את צינור החילוץ והפענוח הנוכחי…")
        self.set_enabled(False)

    def clear(self) -> None:
        self._record = None
        self._baseline = {}
        self.title.setText("סקירת אמת מידה")
        self.metadata.clear()
        self.state_feedback.setVisible(False)
        self.clear_feedback()
        self.set_enabled(False)
        self._set_dirty(False)

    def mark_saved(self, record: Mapping[str, object]) -> None:
        self.set_record(record)

    def show_feedback(self, text: str, variant: FeedbackVariant) -> None:
        self.clear_feedback()
        self._feedback = InlineFeedback(text, variant=variant)
        self.feedback_host.addWidget(self._feedback)

    def clear_feedback(self) -> None:
        if self._feedback is not None:
            self.feedback_host.removeWidget(self._feedback)
            self._feedback.deleteLater()
            self._feedback = None

    def set_enabled(self, enabled: bool) -> None:
        for field in self.fields.values():
            field.setEnabled(enabled)
        self.everything_correct_button.setEnabled(enabled)
        self.save_next_button.setEnabled(enabled)
        self.refresh_button.setEnabled(enabled)

    def _current_draft(self) -> dict[str, tuple[str, bool]]:
        return {key: field.draft_state for key, field in self.fields.items()}

    def _draft_changed(self) -> None:
        dirty = self.is_dirty
        self._set_dirty(dirty)
        self.draftChanged.emit(dirty)

    def _set_dirty(self, dirty: bool) -> None:
        self.dirty_label.setVisible(dirty)
