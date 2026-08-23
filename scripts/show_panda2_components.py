"""Offline development gallery for Panda 2.0 QWidget primitives.

Run from the repository root:
    python -B scripts/show_panda2_components.py

Create a headless verification image:
    python -B scripts/show_panda2_components.py --snapshot path/to/gallery.png
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontInfo
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.domain.workflow_policy import PERSISTED_STATUSES
from app.ui.components import (
    AuxiliaryBadgeVariant,
    ButtonVariant,
    ConfirmationPanel,
    EmptyState,
    FeedbackVariant,
    FieldEditor,
    FieldPresentationState,
    InlineFeedback,
    PandaButton,
    PandaIconButton,
    PandaTextField,
    SearchField,
    StatusBadge,
)
from app.ui.theme import apply_panda_theme
from app.ui.theme.direction import TextKind, isolate_ltr
from app.ui.theme.icons import IconName
from app.ui.theme.tokens import LAYOUT, SPACING
from app.ui.theme.typography import (
    TYPOGRAPHY,
    TypographyRole,
    apply_typography,
    font_for,
    register_bundled_fonts,
)


_STATUS_ORDER = (
    "new",
    "processed",
    "needs_review",
    "failed",
    "skipped",
    "approved",
    "exported",
    "confirmed_irrelevant",
    "excluded",
)
assert frozenset(_STATUS_ORDER) == PERSISTED_STATUSES


def _section(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setProperty("pandaRole", "surface")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 16)
    layout.setSpacing(SPACING.standard)
    label = QLabel(title)
    apply_typography(label, TypographyRole.SECTION_TITLE)
    layout.addWidget(label)
    return frame, layout


class PandaComponentGallery(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Panda 2.0 — Component Gallery")
        self.setMinimumSize(LAYOUT.minimum_width, LAYOUT.minimum_height)
        self.resize(1200, 820)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        registration = register_bundled_fonts()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root_widget = QWidget()
        apply_panda_theme(root_widget)
        scroll.setWidget(root_widget)
        self.setCentralWidget(scroll)

        root = QVBoxLayout(root_widget)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(SPACING.section)

        heading = QLabel("Panda 2.0 — גלריית רכיבים")
        apply_typography(heading, TypographyRole.APPLICATION_TITLE)
        root.addWidget(heading)
        runtime_font = QFontInfo(font_for(TypographyRole.BODY)).family()
        runtime_mono = QFontInfo(font_for(TypographyRole.TECHNICAL)).family()
        font_note = QLabel(
            f"גופן פעיל: {isolate_ltr(runtime_font)} · "
            f"mono: {isolate_ltr(runtime_mono)} · "
            f"קובצי גופן נטענו: {len(registration.loaded_families)} · "
            "Tab מציג פוקוס מקלדת"
        )
        font_note.setProperty("pandaRole", "muted")
        apply_typography(font_note, TypographyRole.HELPER)
        root.addWidget(font_note)

        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACING.section)
        grid.setVerticalSpacing(SPACING.section)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid)

        typography, typography_layout = _section("טיפוגרפיה")
        for role in TypographyRole:
            sample = QLabel(f"{role.value} · חשבונית INV-2026-104 · ₪1,248.50")
            apply_typography(sample, role)
            typography_layout.addWidget(sample)
        grid.addWidget(typography, 0, 0)

        buttons, buttons_layout = _section("כפתורים ומצבים")
        buttons_row = QHBoxLayout()
        self.focus_target = PandaButton(
            "פעולה ראשית", variant=ButtonVariant.PRIMARY, icon_name=IconName.CHECK
        )
        buttons_row.addWidget(self.focus_target)
        buttons_row.addWidget(PandaButton("אישור", variant=ButtonVariant.APPROVAL))
        buttons_row.addWidget(PandaButton("משני", variant=ButtonVariant.SECONDARY))
        buttons_row.addWidget(PandaButton("שקוף", variant=ButtonVariant.GHOST))
        buttons_row.addWidget(
            PandaButton(
                "מחיקה", variant=ButtonVariant.DESTRUCTIVE, icon_name=IconName.TRASH
            )
        )
        buttons_layout.addLayout(buttons_row)
        state_row = QHBoxLayout()
        disabled = PandaButton("מושבת", variant=ButtonVariant.PRIMARY)
        disabled.setEnabled(False)
        state_row.addWidget(disabled)
        state_row.addWidget(
            PandaIconButton(IconName.SEARCH, accessible_text="חיפוש מסמכים")
        )
        state_row.addWidget(
            PandaIconButton(
                IconName.TRASH,
                accessible_text="מחיקת מסמך",
                destructive=True,
            )
        )
        state_row.addStretch()
        buttons_layout.addLayout(state_row)
        grid.addWidget(buttons, 0, 1)

        badges, badges_layout = _section("תגי סטטוס")
        badge_grid = QGridLayout()
        for index, status in enumerate(_STATUS_ORDER):
            badge_grid.addWidget(StatusBadge(status), index // 3, index % 3)
        badge_grid.addWidget(
            StatusBadge.auxiliary(
                "תוקן ידנית", AuxiliaryBadgeVariant.MANUAL_CORRECTION
            ),
            3,
            0,
        )
        badge_grid.addWidget(
            StatusBadge.auxiliary("חשד לכפילות", AuxiliaryBadgeVariant.DUPLICATE),
            3,
            1,
        )
        badges_layout.addLayout(badge_grid)
        grid.addWidget(badges, 1, 0)

        inputs, inputs_layout = _section("שדות וחיפוש")
        inputs_layout.addWidget(SearchField())
        inputs_layout.addWidget(
            PandaTextField(
                "חשבונית שירות חודשית",
                accessible_name="תיאור",
                text_kind=TextKind.HEBREW,
            )
        )
        selected_field = PandaTextField(
            "INV-2026-00184",
            accessible_name="מספר מסמך",
            text_kind=TextKind.DOCUMENT_NUMBER,
        )
        selected_field.selectAll()
        inputs_layout.addWidget(selected_field)
        error_field = PandaTextField(
            "12..50", accessible_name="סכום לא תקין", text_kind=TextKind.AMOUNT
        )
        error_field.set_error(True)
        inputs_layout.addWidget(error_field)
        disabled_field = PandaTextField(
            "C:/Panda/invoices/example.pdf",
            accessible_name="נתיב לקריאה בלבד",
            text_kind=TextKind.PATH,
        )
        disabled_field.setReadOnly(True)
        inputs_layout.addWidget(disabled_field)
        grid.addWidget(inputs, 1, 1)

        field_states, field_layout = _section("מצבי שדה ב־Workspace")
        field_examples = (
            ("ספק", "חברת החשמל לישראל", FieldPresentationState.NORMAL, TextKind.HEBREW),
            ("מספר מסמך", "530-4471902", FieldPresentationState.CORRECTED, TextKind.DOCUMENT_NUMBER),
            ("תאריך", "12/07/2026", FieldPresentationState.LOW_CONFIDENCE, TextKind.DATE),
            ("מע״מ", "", FieldPresentationState.MISSING, TextKind.AMOUNT),
            ("סה״כ", "12..50", FieldPresentationState.INVALID, TextKind.AMOUNT),
            ("מזהה Drive", "drive-file-184", FieldPresentationState.DISABLED, TextKind.TECHNICAL),
        )
        field_grid = QGridLayout()
        field_grid.setHorizontalSpacing(SPACING.standard)
        field_grid.setVerticalSpacing(SPACING.standard)
        for index, (label, value, state, kind) in enumerate(field_examples):
            editor = FieldEditor(label, value=value, state=state, text_kind=kind)
            field_grid.addWidget(editor, index // 2, index % 2)
        field_layout.addLayout(field_grid)
        grid.addWidget(field_states, 2, 0, 1, 2)

        feedback, feedback_layout = _section("משוב בתוך המסך")
        for variant, text in (
            (FeedbackVariant.INFO, "המסמך מוכן לבדיקה מול המקור."),
            (FeedbackVariant.WARNING, "שדה אחד זוהה בביטחון נמוך."),
            (FeedbackVariant.ERROR, "לא ניתן לאשר עד לתיקון השדה החסר."),
            (FeedbackVariant.SUCCESS, "התיקונים נשמרו בהצלחה."),
        ):
            feedback_layout.addWidget(InlineFeedback(text, variant=variant))
        grid.addWidget(feedback, 3, 0)

        empty, empty_layout = _section("מצב ריק")
        empty_layout.addWidget(
            EmptyState(
                "אין מסמכים בתור",
                "סריקת Drive תציג כאן מסמכים חדשים לעיבוד.",
                action_text="סריקת Drive",
            )
        )
        grid.addWidget(empty, 3, 1)

        confirmation, confirmation_layout = _section("דוגמת אישור הרסני")
        confirmation_layout.addWidget(
            ConfirmationPanel(
                title="סימון כלא רלוונטי",
                explanation="המסמך יסומן כלא רלוונטי ולא יופיע בתורי העבודה.",
                consequence="קובץ ה־PDF המקומי יימחק ולא ניתן יהיה לשחזר אותו מתוך Panda.",
                primary_action="סמן כלא רלוונטי",
                destructive=True,
            )
        )
        grid.addWidget(confirmation, 4, 0)

        bidi, bidi_layout = _section("RTL / LTR מעורב")
        mixed = QLabel(
            f"הקובץ {isolate_ltr('invoice_2026_08_01.pdf')} · "
            f"מספר {isolate_ltr('INV-2026-00184')} · "
            f"סכום {isolate_ltr('₪1,248.50')}"
        )
        mixed.setWordWrap(True)
        apply_typography(mixed, TypographyRole.BODY)
        bidi_layout.addWidget(mixed)
        bidi_layout.addWidget(
            PandaTextField(
                "D:/Panda/invoices/2026/invoice_00184.pdf",
                accessible_name="נתיב קובץ",
                text_kind=TextKind.PATH,
            )
        )
        grid.addWidget(bidi, 4, 1)

        root.addStretch()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Render one offline PNG and exit (uses Qt's offscreen platform)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.snapshot:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("Panda 2.0 Component Gallery")
    window = PandaComponentGallery()
    if args.snapshot:
        window.resize(LAYOUT.minimum_width, LAYOUT.minimum_height)
    window.show()
    window.focus_target.setFocus(Qt.FocusReason.OtherFocusReason)
    if args.snapshot:
        app.processEvents()
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.snapshot), "PNG"):
            return 1
        window.close()
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
