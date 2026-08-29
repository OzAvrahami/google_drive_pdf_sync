"""Developer-only Panda 2.0 PDF corpus ground-truth review page."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.pdf_corpus_service import ManifestWriteError, PdfCorpusService
from app.ui.benchmark.corpus_list import CorpusList
from app.ui.benchmark.review_panel import BenchmarkReviewPanel
from app.ui.components import ButtonVariant, EmptyState, PandaButton
from app.ui.components.dialogs import ConfirmationDialog
from app.ui.components.feedback import FeedbackVariant
from app.ui.theme.icons import IconName
from app.ui.theme.tokens import LAYOUT, SPACING
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.workspace.presentation import WorkspaceDocumentPresentation
from app.ui.workspace.source_preview import SourcePreview


DiscardConfirmer = Callable[[str], bool]


class _AnalysisSignals(QObject):
    completed = Signal(str, object)
    failed = Signal(str, str)


class _AnalysisRunnable(QRunnable):
    def __init__(self, service: PdfCorpusService, sha256: str, force: bool) -> None:
        super().__init__()
        self.service = service
        self.sha256 = sha256
        self.force = force
        self.signals = _AnalysisSignals()

    def run(self) -> None:
        try:
            record = self.service.analyze(self.sha256, force=self.force)
        except Exception as exc:
            self.signals.failed.emit(self.sha256, f"{type(exc).__name__}: {exc}")
        else:
            self.signals.completed.emit(self.sha256, record)


class PdfBenchmarkPage(QWidget):
    backRequested = Signal()

    def __init__(
        self,
        service: PdfCorpusService,
        *,
        source_preview: SourcePreview | None = None,
        asynchronous_analysis: bool = True,
        discard_confirmer: DiscardConfirmer | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "benchmarkPage")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.service = service
        self.source_preview = source_preview or SourcePreview()
        self._asynchronous_analysis = asynchronous_analysis
        self._discard_confirmer = discard_confirmer
        self._current_sha: str | None = None
        self._visible_records: list[dict[str, Any]] = []
        self._workers: set[_AnalysisRunnable] = set()
        self._build_ui()
        self._connect_shortcuts()

    @property
    def current_sha(self) -> str | None:
        return self._current_sha

    @property
    def is_dirty(self) -> bool:
        return self.review_panel.is_dirty

    @property
    def visible_records(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._visible_records)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setProperty("pandaComponent", "benchmarkHeader")
        header.setFixedHeight(70)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 8, 20, 8)
        header_layout.setSpacing(SPACING.standard)
        self.back_button = PandaButton(
            "חזרה", variant=ButtonVariant.GHOST, icon_name=IconName.BACK
        )
        self.back_button.setToolTip("חזרה למסך העבודה הקודם (Esc)")
        header_layout.addWidget(self.back_button)
        title_block = QVBoxLayout()
        title_block.setSpacing(1)
        title = QLabel("PDF Benchmark")
        apply_typography(title, TypographyRole.PAGE_TITLE)
        subtitle = QLabel("סקירה מקומית של תוצאות Panda מול אמת אנושית")
        subtitle.setProperty("pandaRole", "muted")
        apply_typography(subtitle, TypographyRole.HELPER)
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header_layout.addLayout(title_block)
        header_layout.addStretch()
        self.progress_label = QLabel("נבדקו 0 / 0")
        self.progress_label.setProperty("pandaComponent", "benchmarkMetric")
        apply_typography(self.progress_label, TypographyRole.LABEL)
        self.accuracy_label = QLabel("דיוק מאומת: —")
        self.accuracy_label.setProperty("pandaComponent", "benchmarkMetric")
        apply_typography(self.accuracy_label, TypographyRole.LABEL)
        metrics = QVBoxLayout()
        metrics.setSpacing(2)
        metric_row = QHBoxLayout()
        metric_row.setSpacing(SPACING.adjacent)
        metric_row.addWidget(self.progress_label)
        metric_row.addWidget(self.accuracy_label)
        self.field_accuracy_label = QLabel("ספק — · תאריך — · מספר — · סכום —")
        self.field_accuracy_label.setProperty("pandaRole", "muted")
        apply_typography(self.field_accuracy_label, TypographyRole.HELPER)
        metrics.addLayout(metric_row)
        metrics.addWidget(self.field_accuracy_label)
        header_layout.addLayout(metrics)
        root.addWidget(header)

        filters = QFrame()
        filters.setProperty("pandaComponent", "benchmarkFilters")
        filter_layout = QHBoxLayout(filters)
        filter_layout.setContentsMargins(16, 8, 16, 8)
        filter_layout.setSpacing(SPACING.adjacent)
        self.review_filter = self._combo(
            "מצב סקירה",
            (("טרם נבדקו", "unreviewed"), ("נבדקו", "reviewed"), ("אי התאמות", "mismatches"), ("הכול", "all")),
        )
        self.status_filter = self._combo(
            "מצב Panda",
            (("כל המצבים", "all"), ("Processed", "processed"), ("Needs review", "needs_review"), ("Skipped", "skipped"), ("Failed", "failed")),
        )
        self.source_filter = self._combo("מערכת מקור", (("כל המקורות", "all"),))
        self.native_filter = self._combo(
            "סוג PDF",
            (("טקסט דיגיטלי", "native"), ("ללא טקסט דיגיטלי", "non_native"), ("הכול", "all")),
        )
        self.sort_combo = self._combo(
            "מיון",
            (("עדיפות סקירה", "priority"), ("ביטחון נמוך", "confidence"), ("שם קובץ", "filename"), ("מערכת מקור", "source"), ("מצב Panda", "status")),
        )
        self.low_confidence = QCheckBox("ביטחון נמוך")
        self.include_skipped = QCheckBox("כולל מסמכים שדולגו")
        for widget in (
            self.review_filter,
            self.status_filter,
            self.source_filter,
            self.native_filter,
            self.sort_combo,
            self.low_confidence,
            self.include_skipped,
        ):
            filter_layout.addWidget(widget)
        filter_layout.addStretch()
        self.refresh_corpus_button = PandaButton("רענון קורפוס", variant=ButtonVariant.GHOST)
        filter_layout.addWidget(self.refresh_corpus_button)
        root.addWidget(filters)

        self.notice = QLabel()
        self.notice.setProperty("pandaComponent", "benchmarkNotice")
        self.notice.setVisible(False)
        self.notice.setWordWrap(True)
        self.notice_timer = QTimer(self)
        self.notice_timer.setSingleShot(True)
        self.notice_timer.timeout.connect(lambda: self.notice.setVisible(False))
        root.addWidget(self.notice)

        self.content_stack = QStackedWidget()
        self.review_content = QWidget()
        content_layout = QHBoxLayout(self.review_content)
        content_layout.setDirection(QHBoxLayout.Direction.LeftToRight)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(SPACING.standard)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setProperty("pandaComponent", "benchmarkSplitter")
        # Preserve the review workflow's physical desktop order independently
        # of the surrounding Hebrew-first application direction.
        self.splitter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.corpus_list = CorpusList()
        self.review_panel = BenchmarkReviewPanel()
        self.splitter.addWidget(self.corpus_list)
        self.splitter.addWidget(self.source_preview)
        self.splitter.addWidget(self.review_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([230, 700, 350])
        content_layout.addWidget(self.splitter)
        self.content_stack.addWidget(self.review_content)

        self.empty_state = EmptyState(
            "לא נמצא קורפוס PDF מקומי",
            "הוסיפו קובצי PDF פרטיים אל tests/fixtures/pdf/_incoming/ "
            "והריצו את תהליך הקליטה וה-Benchmark המקומי.",
            icon_name=IconName.DOCUMENT,
        )
        self.content_stack.addWidget(self.empty_state)
        root.addWidget(self.content_stack, 1)

        self.back_button.clicked.connect(self._request_back)
        self.corpus_list.documentRequested.connect(self._request_document)
        self.review_panel.everythingCorrectRequested.connect(self.everything_correct)
        self.review_panel.saveNextRequested.connect(self.save_and_next)
        self.review_panel.refreshRequested.connect(lambda: self._analyze_current(force=True))
        self.refresh_corpus_button.clicked.connect(self.open_page)
        for combo in (
            self.review_filter,
            self.status_filter,
            self.source_filter,
            self.native_filter,
            self.sort_combo,
        ):
            combo.currentIndexChanged.connect(self._apply_filters)
        self.low_confidence.toggled.connect(self._apply_filters)
        self.include_skipped.toggled.connect(self._apply_filters)

    def _connect_shortcuts(self) -> None:
        self.save_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.save_shortcut.activated.connect(self.save_and_next)
        self.everything_shortcut = QShortcut(QKeySequence("Alt+A"), self)
        self.everything_shortcut.activated.connect(self.everything_correct)
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.activated.connect(self._request_back)

    @staticmethod
    def _combo(accessible_name: str, items: tuple[tuple[str, str], ...]) -> QComboBox:
        combo = QComboBox()
        combo.setProperty("pandaComponent", "benchmarkFilter")
        combo.setAccessibleName(accessible_name)
        for label, value in items:
            combo.addItem(label, value)
        return combo

    def open_page(self) -> None:
        if self.is_dirty and not self.confirm_discard_changes("refresh"):
            return
        records = self.service.reload()
        self._populate_sources(records)
        self._refresh_summary()
        self.content_stack.setCurrentWidget(
            self.review_content if records else self.empty_state
        )
        if records:
            self._apply_filters()
        else:
            self._current_sha = None
            self.review_panel.clear()
            self.source_preview.release_source()

    def confirm_discard_changes(self, reason: str = "navigation") -> bool:
        if not self.is_dirty:
            return True
        if self._discard_confirmer is not None:
            return bool(self._discard_confirmer(reason))
        dialog = ConfirmationDialog(
            title="שינויים שלא נשמרו",
            explanation="ערכי האמת במסמך הנוכחי נערכו אך טרם נשמרו.",
            consequence="המשך הפעולה יבטל את השינויים במסמך זה בלבד.",
            primary_action="ביטול שינויים",
            cancel_text="המשך עריכה",
            parent=self,
        )
        return dialog.exec() == dialog.DialogCode.Accepted

    def everything_correct(self) -> None:
        if self._current_sha is None:
            return
        self._persist_and_advance(everything_correct=True)

    def save_and_next(self) -> None:
        if self._current_sha is None:
            return
        self._persist_and_advance(everything_correct=False)

    def release_source(self) -> None:
        self.source_preview.release_source()

    def _request_back(self) -> None:
        if self.confirm_discard_changes("back"):
            self.backRequested.emit()

    def _request_document(self, sha256: str) -> None:
        if sha256 == self._current_sha:
            return
        if self.is_dirty and not self.confirm_discard_changes("document"):
            if self._current_sha:
                self.corpus_list.select_sha(self._current_sha)
            return
        self._current_sha = sha256
        snapshot = self.service.record_by_sha(sha256)
        if snapshot is None:
            return
        self.source_preview.load_presentation(self._source_presentation(snapshot))
        self.review_panel.set_loading(str(snapshot.get("filename") or ""))
        self._analyze_current()

    def _analyze_current(self, *, force: bool = False) -> None:
        sha256 = self._current_sha
        if sha256 is None:
            return
        if not self._asynchronous_analysis:
            try:
                record = self.service.analyze(sha256, force=force)
            except Exception as exc:
                self._analysis_failed(sha256, f"{type(exc).__name__}: {exc}")
            else:
                self._analysis_completed(sha256, record)
            return
        worker = _AnalysisRunnable(self.service, sha256, force)
        self._workers.add(worker)
        worker.signals.completed.connect(self._analysis_completed)
        worker.signals.failed.connect(self._analysis_failed)
        worker.signals.completed.connect(lambda _sha, _record, item=worker: self._workers.discard(item))
        worker.signals.failed.connect(lambda _sha, _error, item=worker: self._workers.discard(item))
        QThreadPool.globalInstance().start(worker)

    def _analysis_completed(self, sha256: str, record: object) -> None:
        if sha256 != self._current_sha or not isinstance(record, Mapping):
            return
        self.review_panel.set_record(record)
        self._refresh_summary()
        self._apply_filters(preferred_sha=sha256)

    def _analysis_failed(self, sha256: str, _technical_error: str) -> None:
        if sha256 != self._current_sha:
            return
        self.review_panel.set_enabled(False)
        self.review_panel.show_feedback(
            "לא ניתן לנתח את המסמך המקומי. הקובץ נשאר ללא שינוי.",
            FeedbackVariant.ERROR,
        )

    def _persist_and_advance(self, *, everything_correct: bool) -> None:
        assert self._current_sha is not None
        old_shas = self.corpus_list.ordered_shas
        old_index = self.corpus_list.current_index()
        next_sha = old_shas[old_index + 1] if 0 <= old_index < len(old_shas) - 1 else None
        try:
            if everything_correct:
                saved = self.service.everything_correct(self._current_sha)
            else:
                saved = self.service.save_review(
                    self._current_sha,
                    self.review_panel.expected_values(),
                )
        except ManifestWriteError:
            self.review_panel.show_feedback(
                "לא ניתן לשמור את סקירת ה-PDF משום ש-pdf_manifest.csv פתוח בתוכנה אחרת. "
                "סגרו את הקובץ ונסו שוב. לא נכתב מידע חלקי.",
                FeedbackVariant.ERROR,
            )
            return
        except Exception:
            self.review_panel.show_feedback(
                "שמירת אמת המידה נכשלה. לא נכתב מידע חלקי.",
                FeedbackVariant.ERROR,
            )
            return
        self.review_panel.mark_saved(saved)
        self._show_notice("אמת המידה נשמרה", "success")
        self._refresh_summary()
        self._apply_filters(preferred_sha=next_sha, preferred_index=old_index)

    def _apply_filters(
        self,
        _value: object = None,
        *,
        preferred_sha: str | None = None,
        preferred_index: int | None = None,
    ) -> None:
        records = self.service.filtered_records(
            review_state=str(self.review_filter.currentData()),
            status=str(self.status_filter.currentData()),
            source=str(self.source_filter.currentData()),
            native=str(self.native_filter.currentData()),
            low_confidence=self.low_confidence.isChecked(),
            include_skipped=self.include_skipped.isChecked(),
            sort_by=str(self.sort_combo.currentData()),
        )
        self._visible_records = records
        self.corpus_list.set_records(
            records,
            total=len(self.service.records),
            preferred_sha=preferred_sha or self._current_sha,
            preferred_index=preferred_index,
        )
        if not records:
            self._current_sha = None
            self.review_panel.clear()
            self.source_preview.release_source()
            self._show_notice("אין מסמכים התואמים למסננים הנוכחיים", "info", timeout=0)
        elif self.notice.property("state") == "info" and not self.notice_timer.isActive():
            self.notice.setVisible(False)

    def _populate_sources(self, records: tuple[dict[str, Any], ...]) -> None:
        current = self.source_filter.currentData()
        sources = sorted(
            {
                str((record.get("source_detection") or {}).get("source_system") or "Unknown")
                for record in records
            },
            key=str.casefold,
        )
        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem("כל המקורות", "all")
        for source in sources:
            self.source_filter.addItem(source, source)
        index = self.source_filter.findData(current)
        self.source_filter.setCurrentIndex(max(0, index))
        self.source_filter.blockSignals(False)

    def _refresh_summary(self) -> None:
        accuracy = self.service.accuracy()
        reviewed = accuracy["reviewed"]
        total = accuracy["total"]
        self.progress_label.setText(f"נבדקו {reviewed} / {total} · נותרו {total - reviewed}")
        self.accuracy_label.setText(
            f"מסמכים מדויקים {accuracy['fully_correct']} / {reviewed}"
            if reviewed
            else "דיוק מאומת: טרם נבדק"
        )
        fields = accuracy["fields"]
        self.accuracy_label.setToolTip(
            " · ".join(
                (
                    f"ספק {fields['supplier_correct']['correct']}/{reviewed}",
                    f"תאריך {fields['invoice_date_correct']['correct']}/{reviewed}",
                    f"מספר {fields['invoice_number_correct']['correct']}/{reviewed}",
                    f"סכום {fields['amount_correct']['correct']}/{reviewed}",
                )
            )
        )
        self.field_accuracy_label.setText(
            " · ".join(
                (
                    f"ספק {fields['supplier_correct']['correct']}/{reviewed}",
                    f"תאריך {fields['invoice_date_correct']['correct']}/{reviewed}",
                    f"מספר {fields['invoice_number_correct']['correct']}/{reviewed}",
                    f"סכום {fields['amount_correct']['correct']}/{reviewed}",
                )
            )
            if reviewed
            else "ספק — · תאריך — · מספר — · סכום —"
        )

    def _show_notice(self, text: str, state: str, *, timeout: int = 2400) -> None:
        self.notice.setText(text)
        self.notice.setProperty("state", state)
        self.notice.setVisible(True)
        if timeout:
            self.notice_timer.start(timeout)
        else:
            self.notice_timer.stop()

    @staticmethod
    def _source_presentation(record: Mapping[str, Any]) -> WorkspaceDocumentPresentation:
        return WorkspaceDocumentPresentation(
            document_id=str(record.get("sha256") or ""),
            file_name=str(record.get("filename") or ""),
            folder_path=str(Path(str(record.get("relative_path") or "")).parent),
            local_path=str(record.get("_absolute_path") or ""),
            raw_text_path="",
            status=str(record.get("status") or "unanalyzed"),
            status_label=str(record.get("status") or "unanalyzed"),
            confidence=float(record.get("confidence") or 0),
            attention_text="",
            error_message="",
            is_duplicate_suspected=False,
            duplicate_candidate_count=0,
            was_manually_corrected=False,
            fields=(),
        )

    def resizeEvent(self, event) -> None:
        width = event.size().width()
        if width < 960:
            self.corpus_list.setMaximumWidth(210)
            self.review_panel.setMaximumWidth(330)
            self.splitter.setSizes([190, max(300, width - 520), 310])
        else:
            self.corpus_list.setMaximumWidth(280)
            self.review_panel.setMaximumWidth(390)
        super().resizeEvent(event)
