"""Operational Overview for the Panda 2.0 development shell."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.models.document import Document
from app.ui.components import ButtonVariant, PandaButton
from app.ui.routes import AppRoute
from app.ui.theme.direction import isolate_ltr
from app.ui.theme.tokens import SPACING
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.views.overview_data import (
    OverviewSnapshot,
    RecentDocumentChange,
    build_overview_snapshot,
    format_recent_time,
)


class _BreakdownChip(QFrame):
    def __init__(self, label: str, semantic: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "breakdownChip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(6)
        dot = QLabel()
        dot.setProperty("pandaComponent", "breakdownDot")
        dot.setProperty("semantic", semantic)
        dot.setFixedSize(6, 6)
        self._label = QLabel(label)
        apply_typography(self._label, TypographyRole.HELPER)
        self._value = QLabel("0")
        self._value.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        apply_typography(self._value, TypographyRole.BADGE)
        layout.addWidget(dot)
        layout.addWidget(self._label)
        layout.addWidget(self._value)

    @property
    def value(self) -> int:
        return int(self._value.text())

    def set_value(self, value: int) -> None:
        self._value.setText(str(value))


class _ActionCard(QFrame):
    activated = Signal(str)

    def __init__(
        self,
        *,
        key: str,
        title: str,
        unit: str,
        subtitle: str,
        semantic: str,
        action_text: str,
        action_route: AppRoute,
        button_variant: ButtonVariant,
        note: str = "",
        breakdown: tuple[tuple[str, str, str], ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self.action_route = action_route
        self.setProperty("pandaComponent", "overviewCard")
        self.setProperty("semantic", semantic)
        self.setMinimumHeight(184)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        accent = QFrame()
        accent.setProperty("pandaComponent", "cardAccent")
        accent.setProperty("semantic", semantic)
        accent.setFixedWidth(4)
        outer.addWidget(accent)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 15, 18, 14)
        layout.setSpacing(8)
        title_row = QHBoxLayout()
        title_label = QLabel(title)
        apply_typography(title_label, TypographyRole.LABEL)
        unit_label = QLabel(unit)
        unit_label.setProperty("pandaRole", "muted")
        apply_typography(unit_label, TypographyRole.HELPER)
        title_row.addWidget(title_label)
        title_row.addStretch()
        title_row.addWidget(unit_label)
        layout.addLayout(title_row)

        count_row = QHBoxLayout()
        count_row.setSpacing(10)
        self._count = QLabel("0")
        self._count.setProperty("pandaComponent", "metricValue")
        self._count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._count.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        apply_typography(self._count, TypographyRole.METRIC)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setProperty("pandaRole", "helper")
        apply_typography(subtitle_label, TypographyRole.COMPACT_BODY)
        count_row.addWidget(self._count)
        count_row.addWidget(subtitle_label)
        count_row.addStretch()
        layout.addLayout(count_row)

        self.breakdown: dict[str, _BreakdownChip] = {}
        if breakdown:
            breakdown_grid = QGridLayout()
            breakdown_grid.setHorizontalSpacing(6)
            breakdown_grid.setVerticalSpacing(4)
            for index, (breakdown_key, label, breakdown_semantic) in enumerate(breakdown):
                chip = _BreakdownChip(label, breakdown_semantic)
                self.breakdown[breakdown_key] = chip
                breakdown_grid.addWidget(chip, index // 2, index % 2)
            breakdown_grid.setColumnStretch(2, 1)
            layout.addLayout(breakdown_grid)
        elif note:
            note_label = QLabel(note)
            note_label.setProperty("pandaRole", "muted")
            note_label.setWordWrap(True)
            apply_typography(note_label, TypographyRole.HELPER)
            layout.addWidget(note_label)

        layout.addStretch()
        self.action_button = PandaButton(action_text, variant=button_variant)
        self.action_button.clicked.connect(lambda: self.activated.emit(action_route.value))
        layout.addWidget(self.action_button)
        outer.addWidget(body, 1)

    @property
    def count(self) -> int:
        return int(self._count.text())

    def set_count(self, count: int) -> None:
        self._count.setText(str(max(0, int(count))))
        self.setAccessibleName(f"{self.key}: {count}")


class _MetricCell(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "metricCell")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(SPACING.adjacent)
        self._label = QLabel()
        self._label.setProperty("pandaComponent", "metricLabel")
        apply_typography(self._label, TypographyRole.COMPACT_BODY)
        self._value = QLabel()
        self._value.setProperty("pandaComponent", "metricValue")
        self._value.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        apply_typography(self._value, TypographyRole.SECTION_TITLE)
        layout.addWidget(self._label)
        layout.addStretch()
        layout.addWidget(self._value)

    @property
    def value(self) -> int:
        return int(self._value.text())

    def set_metric(self, label: str, value: int, description: str) -> None:
        self._label.setText(label)
        self._value.setText(str(value))
        self.setToolTip(description)
        self.setAccessibleName(f"{label}: {value}")


class OverviewView(QWidget):
    routeRequested = Signal(str)

    def __init__(
        self,
        documents: Iterable[Document] = (),
        *,
        now: datetime | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAccessibleName("סקירה")
        self._now = now
        self._snapshot = build_overview_snapshot((), now=now)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setProperty("pandaComponent", "overviewScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        canvas = QWidget()
        canvas.setProperty("pandaComponent", "overviewCanvas")
        scroll.setWidget(canvas)
        root.addWidget(scroll)

        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(24, 20, 24, 22)
        layout.setSpacing(0)

        question_row = QHBoxLayout()
        question_row.setSpacing(10)
        self.question_label = QLabel("מה דורש טיפול עכשיו")
        apply_typography(self.question_label, TypographyRole.SECTION_TITLE)
        question_note = QLabel("שלושת מצבי העבודה הפעילים — לפי סדר עדיפות")
        question_note.setProperty("pandaRole", "muted")
        apply_typography(question_note, TypographyRole.COMPACT_BODY)
        question_row.addWidget(self.question_label)
        question_row.addWidget(question_note)
        question_row.addStretch()
        layout.addLayout(question_row)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(SPACING.section)
        self.cards = {
            "attention": _ActionCard(
                key="attention",
                title="דורש טיפול",
                unit="מסמכים",
                subtitle="ממתינים לפעולה",
                semantic="attention",
                action_text="טפל עכשיו",
                action_route=AppRoute.ATTENTION,
                button_variant=ButtonVariant.DARK,
                breakdown=(
                    ("needs_review", "לבדיקה", "attention"),
                    ("failed", "נכשל", "error"),
                    ("suspected_duplicate", "כפילויות", "duplicate"),
                ),
            ),
            "ready_to_approve": _ActionCard(
                key="ready_to_approve",
                title="מוכן לאישור",
                unit="מסמכים",
                subtitle="עובדו אוטומטית",
                semantic="approval",
                action_text="עבור לאישור",
                action_route=AppRoute.READY,
                button_variant=ButtonVariant.APPROVAL,
                note="זוהו וממתינים לאישור אנושי לפני ייצוא.",
            ),
            "ready_to_export": _ActionCard(
                key="ready_to_export",
                title="מוכן לייצוא",
                unit="רשומות",
                subtitle="אושרו",
                semantic="export",
                action_text="הצג מוכנים לייצוא",
                action_route=AppRoute.READY,
                button_variant=ButtonVariant.PRIMARY,
                note="אושרו וממתינים לייצוא לאקסל.",
            ),
        }
        for card in self.cards.values():
            card.activated.connect(self.routeRequested)
            cards_row.addWidget(card, 1)
        layout.addSpacing(14)
        layout.addLayout(cards_row)

        metrics_heading = QHBoxLayout()
        metrics_heading.setContentsMargins(0, 18, 0, 10)
        metric_title = QLabel("מדדים")
        metric_title.setProperty("pandaRole", "muted")
        apply_typography(metric_title, TypographyRole.BADGE)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        metrics_heading.addWidget(metric_title)
        metrics_heading.addWidget(divider, 1)
        layout.addLayout(metrics_heading)

        metrics_strip = QFrame()
        metrics_strip.setProperty("pandaComponent", "metricsStrip")
        metric_layout = QHBoxLayout(metrics_strip)
        metric_layout.setContentsMargins(0, 0, 0, 0)
        metric_layout.setSpacing(0)
        self.metrics: dict[str, _MetricCell] = {}
        for key in ("updated_today", "updated_this_month", "manually_corrected"):
            cell = _MetricCell()
            self.metrics[key] = cell
            metric_layout.addWidget(cell, 1)
        layout.addWidget(metrics_strip)

        lower_row = QHBoxLayout()
        lower_row.setContentsMargins(0, 20, 0, 0)
        lower_row.setSpacing(SPACING.section)
        recent_panel = QFrame()
        recent_panel.setProperty("pandaComponent", "overviewPanel")
        recent_layout = QVBoxLayout(recent_panel)
        recent_layout.setContentsMargins(4, 6, 4, 6)
        recent_layout.setSpacing(0)
        recent_header = QLabel("שינויים אחרונים במסמכים")
        recent_header.setToolTip("נגזר מ-updated_at; זו אינה היסטוריית אירועים מלאה")
        apply_typography(recent_header, TypographyRole.LABEL)
        recent_layout.addWidget(recent_header)
        self._recent_layout = recent_layout
        self._recent_rows: list[QWidget] = []
        lower_row.addWidget(recent_panel, 3)

        task_panel = QFrame()
        task_panel.setProperty("pandaComponent", "overviewPanel")
        task_layout = QVBoxLayout(task_panel)
        task_layout.setContentsMargins(16, 14, 16, 14)
        task_layout.setSpacing(10)
        task_title = QLabel("משימות רקע")
        apply_typography(task_title, TypographyRole.LABEL)
        task_layout.addWidget(task_title)
        idle = QFrame()
        idle.setProperty("pandaComponent", "idleTaskCard")
        idle_layout = QVBoxLayout(idle)
        idle_layout.setContentsMargins(12, 12, 12, 12)
        idle_title = QLabel("אין משימות פעילות")
        apply_typography(idle_title, TypographyRole.COMPACT_BODY)
        idle_detail = QLabel("סריקה ועיבוד יחוברו למרכז המשימות בשלב הבא.")
        idle_detail.setProperty("pandaRole", "muted")
        idle_detail.setWordWrap(True)
        apply_typography(idle_detail, TypographyRole.HELPER)
        idle_layout.addWidget(idle_title)
        idle_layout.addWidget(idle_detail)
        task_layout.addWidget(idle)
        task_layout.addStretch()
        lower_row.addWidget(task_panel, 2)
        layout.addLayout(lower_row)
        layout.addStretch()
        self.refresh(documents, now=now)

    @property
    def snapshot(self) -> OverviewSnapshot:
        return self._snapshot

    def refresh(
        self, documents: Iterable[Document], *, now: datetime | None = None
    ) -> None:
        self.set_snapshot(build_overview_snapshot(documents, now=now or self._now))

    def set_snapshot(self, snapshot: OverviewSnapshot) -> None:
        self._snapshot = snapshot
        counts = snapshot.counts
        self.cards["attention"].set_count(counts.attention)
        self.cards["ready_to_approve"].set_count(
            counts.ready_breakdown.ready_to_approve
        )
        self.cards["ready_to_export"].set_count(
            counts.ready_breakdown.ready_to_export
        )
        attention = counts.attention_breakdown
        self.cards["attention"].breakdown["needs_review"].set_value(
            attention.needs_review
        )
        self.cards["attention"].breakdown["failed"].set_value(attention.failed)
        self.cards["attention"].breakdown["suspected_duplicate"].set_value(
            attention.suspected_duplicate
        )
        for metric in snapshot.metrics:
            self.metrics[metric.key].set_metric(
                metric.label_he, metric.value, metric.description_he
            )
        self._replace_recent(snapshot.recent_changes)

    def _replace_recent(self, changes: tuple[RecentDocumentChange, ...]) -> None:
        for row in self._recent_rows:
            self._recent_layout.removeWidget(row)
            row.deleteLater()
        self._recent_rows = []
        if not changes:
            label = QLabel("אין שינויים מתוארכים להצגה")
            label.setProperty("pandaRole", "muted")
            apply_typography(label, TypographyRole.COMPACT_BODY)
            label.setContentsMargins(16, 16, 16, 16)
            self._recent_layout.addWidget(label)
            self._recent_rows.append(label)
            return
        for change in changes:
            row = QFrame()
            row.setProperty("pandaComponent", "recentRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(16, 8, 16, 8)
            row_layout.setSpacing(10)
            dot = QLabel()
            dot.setProperty("pandaComponent", "recentDot")
            dot.setProperty("semantic", change.semantic)
            dot.setFixedSize(7, 7)
            text = QLabel(f"{isolate_ltr(change.file_name)} · {change.status_label}")
            text.setTextFormat(Qt.TextFormat.PlainText)
            text.setToolTip(change.file_name)
            apply_typography(text, TypographyRole.COMPACT_BODY)
            time = QLabel(format_recent_time(change.updated_at, now=self._now))
            time.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            time.setProperty("pandaRole", "muted")
            apply_typography(time, TypographyRole.TECHNICAL)
            row_layout.addWidget(dot)
            row_layout.addWidget(text, 1)
            row_layout.addWidget(time)
            self._recent_layout.addWidget(row)
            self._recent_rows.append(row)
