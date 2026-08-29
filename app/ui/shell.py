"""Panda 2.0 application shell, selected with the explicit startup flag."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.application.task_manager import TaskManager, TaskType
from app.application.approval_service import ApprovalService
from app.application.export_service import ExportService
from app.application.document_review_service import DocumentReviewService
from app.application.duplicate_comparison_service import DuplicateComparisonService
from app.application.duplicate_resolution_service import DuplicateResolutionService
from app.application.irrelevant_service import IrrelevantService
from app.application.workspace_approval_service import WorkspaceApprovalService
from app.config import BASE_DIR, EXCEL_OUTPUT_PATH
from app.models.document import Document
from app.services.pdf_corpus_service import PdfCorpusService
from app.ui.benchmark import PdfBenchmarkPage
from app.ui.components import ButtonVariant, NavigationRail, PandaButton
from app.ui.models.document_table_model import DocumentTableModel
from app.ui.models.queue_policy import QueueRoute, calculate_queue_counts
from app.ui.models.task_list_model import TaskListModel
from app.ui.routes import AppRoute, ROUTES, RouteViewKind, route_definition
from app.ui.theme import apply_panda_theme
from app.ui.theme.icons import IconName
from app.ui.theme.tokens import LAYOUT, SPACING
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.tasks.task_center import TaskCenter
from app.ui.tasks.export_tasks import ExportTaskController
from app.ui.tasks.operational_tasks import OperationalTaskController
from app.ui.views import DocumentQueueView, OverviewView, ReadyView
from app.ui.workspace import WorkspaceView


class ReadOnlyDocumentSource(Protocol):
    def all(self) -> list[Document]: ...


_UNAVAILABLE_ACTION_REASON = (
    "הפעולה זמינה רק כאשר Panda 2.0 מחובר למאגר המסמכים התפעולי."
)


class PandaMainWindow(QMainWindow):
    """Panda 2.0 shell; legacy MainWindow remains independent."""

    routeChanged = Signal(str)

    def __init__(
        self,
        document_source: ReadOnlyDocumentSource,
        *,
        task_manager: TaskManager | None = None,
        operational_controller: OperationalTaskController | None = None,
        operational_enabled: bool | None = None,
        document_review_service: DocumentReviewService | None = None,
        approval_service: ApprovalService | None = None,
        workspace_approval_service: WorkspaceApprovalService | None = None,
        irrelevant_service: IrrelevantService | None = None,
        duplicate_comparison_service: DuplicateComparisonService | None = None,
        duplicate_resolution_service: DuplicateResolutionService | None = None,
        export_service: ExportService | None = None,
        export_controller: ExportTaskController | None = None,
        export_enabled: bool = False,
        pdf_corpus_service: PdfCorpusService | None = None,
        pdf_corpus_root: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._document_source = document_source
        if operational_controller is not None:
            if task_manager is not None and task_manager is not operational_controller.task_manager:
                raise ValueError("Operational controller and shell must share one TaskManager")
            self.task_manager = operational_controller.task_manager
        else:
            self.task_manager = task_manager or TaskManager()
        if operational_enabled is None:
            operational_enabled = all(
                hasattr(document_source, attribute)
                for attribute in ("get_by_drive_id", "get_by_status", "upsert")
            )
        self.operational_controller = operational_controller
        if self.operational_controller is None and operational_enabled:
            self.operational_controller = OperationalTaskController(
                document_source, self.task_manager, parent=self
            )
        repository_capable = all(
            hasattr(document_source, attribute)
            for attribute in ("get_by_drive_id", "upsert")
        )
        self.document_review_service = document_review_service
        if self.document_review_service is None and repository_capable:
            self.document_review_service = DocumentReviewService(document_source)
        self.approval_service = approval_service
        if self.approval_service is None and repository_capable:
            self.approval_service = ApprovalService(document_source)
        self.workspace_approval_service = workspace_approval_service
        if (
            self.workspace_approval_service is None
            and repository_capable
            and self.document_review_service is not None
            and self.approval_service is not None
        ):
            self.workspace_approval_service = WorkspaceApprovalService(
                document_source,
                self.document_review_service,
                self.approval_service,
            )
        self.irrelevant_service = irrelevant_service
        if self.irrelevant_service is None and repository_capable:
            self.irrelevant_service = IrrelevantService(document_source)
        self.duplicate_comparison_service = duplicate_comparison_service
        if self.duplicate_comparison_service is None and repository_capable:
            self.duplicate_comparison_service = DuplicateComparisonService(document_source)
        self.duplicate_resolution_service = duplicate_resolution_service
        if (
            self.duplicate_resolution_service is None
            and repository_capable
            and self.irrelevant_service is not None
        ):
            self.duplicate_resolution_service = DuplicateResolutionService(
                document_source, self.irrelevant_service
            )
        self.export_service = export_service
        if self.export_service is None and repository_capable:
            self.export_service = ExportService(document_source, EXCEL_OUTPUT_PATH)
        self.export_controller = export_controller
        if (
            self.export_controller is None
            and self.export_service is not None
            and export_enabled
        ):
            self.export_controller = ExportTaskController(
                self.export_service, self.task_manager, parent=self
            )
        self.task_model = TaskListModel(self.task_manager, self)
        self.pdf_corpus_service = pdf_corpus_service or PdfCorpusService(
            pdf_corpus_root or (BASE_DIR / "tests" / "fixtures" / "pdf")
        )
        self.document_model = DocumentTableModel(parent=self)
        self._documents: tuple[Document, ...] = ()
        self._documents_by_id: dict[str, Document] = {}
        self._current_route = AppRoute.OVERVIEW
        self._workspace_origin_selection: tuple[str, ...] = ()
        self._views: dict[AppRoute, QWidget] = {}
        self.setWindowTitle("Panda 2.0")
        self.setMinimumSize(LAYOUT.minimum_width, LAYOUT.minimum_height)
        self.resize(LAYOUT.target_width, LAYOUT.target_height)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._build_ui()
        self._connect_operational_tasks()
        self._connect_export_tasks()
        self.refresh()
        self.navigate(AppRoute.OVERVIEW)

    @property
    def current_route(self) -> AppRoute:
        return self._current_route

    @property
    def documents(self) -> tuple[Document, ...]:
        return self._documents

    @property
    def workspace_active(self) -> bool:
        return self.mode_stack.currentWidget() is self.workspace

    @property
    def benchmark_active(self) -> bool:
        return self.mode_stack.currentWidget() is self.benchmark_page

    def view_for(self, route: AppRoute | str) -> QWidget:
        return self._views[AppRoute(route)]

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("panda2ShellRoot")
        root.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        apply_panda_theme(root)
        self.setCentralWidget(root)
        shell_layout = QHBoxLayout(root)
        # Keep the physical split deterministic: flexible content on the left,
        # fixed work rail on the right. Child widgets remain Hebrew-first RTL.
        shell_layout.setDirection(QBoxLayout.Direction.LeftToRight)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        content = QWidget()
        content.setProperty("pandaComponent", "shellContent")
        content.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        shell_layout.addWidget(content, 1)

        self.navigation = NavigationRail(self.task_model)
        self.navigation.routeRequested.connect(self.navigate)
        self.navigation.benchmarkRequested.connect(self.open_benchmark)
        shell_layout.addWidget(self.navigation)

        self.header = QFrame()
        self.header.setProperty("pandaComponent", "screenHeader")
        self.header.setFixedHeight(LAYOUT.screen_header_height)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(24, 0, 24, 0)
        header_layout.setSpacing(SPACING.adjacent)
        title_block = QWidget()
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 7, 0, 7)
        title_layout.setSpacing(1)
        self.header_title = QLabel()
        apply_typography(self.header_title, TypographyRole.PAGE_TITLE)
        self.header_subtitle = QLabel()
        self.header_subtitle.setProperty("pandaRole", "muted")
        apply_typography(self.header_subtitle, TypographyRole.HELPER)
        title_layout.addWidget(self.header_title)
        title_layout.addWidget(self.header_subtitle)
        header_layout.addWidget(title_block)
        header_layout.addStretch()

        self.scan_button = PandaButton(
            "סריקת Drive", variant=ButtonVariant.SECONDARY, icon_name=IconName.SCAN
        )
        self.process_button = PandaButton(
            "עיבוד מסמכים", variant=ButtonVariant.PRIMARY, icon_name=IconName.PROCESS
        )
        self.scan_button.clicked.connect(self._submit_scan)
        self.process_button.clicked.connect(self._submit_process)
        header_layout.addWidget(self.scan_button)
        header_layout.addWidget(self.process_button)
        self.route_mode = QWidget()
        route_layout = QVBoxLayout(self.route_mode)
        route_layout.setContentsMargins(0, 0, 0, 0)
        route_layout.setSpacing(0)
        route_layout.addWidget(self.header)

        self.stack = QStackedWidget()
        route_layout.addWidget(self.stack, 1)
        for definition in ROUTES:
            if definition.view_kind is RouteViewKind.OVERVIEW:
                view = OverviewView(task_model=self.task_model)
                view.routeRequested.connect(self.navigate)
                self.overview = view
            elif definition.view_kind is RouteViewKind.DOCUMENT_QUEUE:
                assert definition.queue_route is not None
                view = DocumentQueueView(self.document_model, definition.queue_route)
                view.scanRequested.connect(self._submit_scan)
                view.processRequested.connect(self._submit_process)
                view.openDocumentRequested.connect(self.open_workspace)
                if definition.queue_route is QueueRoute.INBOX:
                    self.inbox = view
                elif definition.queue_route is QueueRoute.ATTENTION:
                    self.attention = view
                elif definition.queue_route is QueueRoute.IRRELEVANT:
                    self.irrelevant = view
                elif definition.queue_route is QueueRoute.HISTORY:
                    self.history = view
            elif definition.view_kind is RouteViewKind.READY:
                view = ReadyView(
                    self.document_model,
                    self.approval_service,
                    workbook_path=(
                        self.export_service.output_path
                        if self.export_service is not None
                        else str(EXCEL_OUTPUT_PATH)
                    ),
                )
                view.openDocumentRequested.connect(self.open_workspace)
                view.batchApproved.connect(self._on_ready_batch_approved)
                view.exportRequested.connect(self._submit_export)
                self.ready = view
            else:
                raise AssertionError(f"Unhandled Panda route view: {definition.view_kind}")
            self._views[definition.route] = view
            self.stack.addWidget(view)

        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self.route_mode)
        self.workspace = WorkspaceView(
            self._document_by_id,
            review_service=self.document_review_service,
            approval_executor=(
                self.workspace_approval_service.approve_draft
                if self.workspace_approval_service is not None
                else None
            ),
            duplicate_comparison_service=self.duplicate_comparison_service,
            duplicate_resolution_service=self.duplicate_resolution_service,
            irrelevant_service=self.irrelevant_service,
            document_change_notifier=self.refresh_document,
        )
        self.workspace.backRequested.connect(self._return_from_workspace)
        self.workspace.documentSaved.connect(self.refresh_document)
        self.workspace.documentApproved.connect(self.refresh_document)
        self.mode_stack.addWidget(self.workspace)
        self.benchmark_page = PdfBenchmarkPage(self.pdf_corpus_service)
        self.benchmark_page.backRequested.connect(self._return_from_benchmark)
        self.mode_stack.addWidget(self.benchmark_page)
        content_layout.addWidget(self.mode_stack, 1)

        self.task_center = TaskCenter(self.task_model, self.task_manager, root)
        self.navigation.taskCenterRequested.connect(self.task_center.toggle)
        self.overview.task_summary.taskCenterRequested.connect(self.task_center.open_panel)
        self._position_task_center()
        self._refresh_action_availability()

    def navigate(self, route: AppRoute | str) -> bool:
        destination = AppRoute(route)
        if (
            hasattr(self, "workspace")
            and self.workspace_active
            and not self.workspace.confirm_discard_changes("route")
        ):
            return False
        if (
            hasattr(self, "benchmark_page")
            and self.benchmark_active
            and not self.benchmark_page.confirm_discard_changes("route")
        ):
            return False
        definition = route_definition(destination)
        changed = destination is not self._current_route
        self._current_route = destination
        self.mode_stack.setCurrentWidget(self.route_mode)
        self.stack.setCurrentWidget(self._views[destination])
        self.header.setVisible(destination is AppRoute.OVERVIEW)
        self.navigation.set_active_route(destination)
        self.header_title.setText(definition.label_he)
        if destination is AppRoute.OVERVIEW:
            self.header_subtitle.setText("תמונת מצב עדכנית של המסמכים המקומיים")
        else:
            count = (
                self._counts.for_route(definition.queue_route)
                if definition.queue_route is not None
                else 0
            )
            self.header_subtitle.setText(
                f"{count} מסמכים"
            )
        if changed:
            self.routeChanged.emit(destination.value)
        return True

    def open_benchmark(self) -> bool:
        if (
            hasattr(self, "workspace")
            and self.workspace_active
            and not self.workspace.confirm_discard_changes("benchmark")
        ):
            return False
        self.mode_stack.setCurrentWidget(self.benchmark_page)
        self.navigation.set_benchmark_active(True)
        self.benchmark_page.open_page()
        self.benchmark_page.setFocus()
        return True

    def open_workspace(
        self,
        document_id: str,
        ordered_visible_ids: object,
        origin_route: str,
    ) -> bool:
        try:
            route = AppRoute(origin_route)
        except ValueError:
            return False
        view = self._views.get(route)
        if not isinstance(view, (DocumentQueueView, ReadyView)):
            return False
        ids = tuple(str(value) for value in ordered_visible_ids)
        if document_id not in ids or self._document_by_id(document_id) is None:
            return False
        self._current_route = route
        self.navigation.set_active_route(route)
        selection = view.selected_document_ids
        self._workspace_origin_selection = selection or (document_id,)
        view.focus_document(document_id, preserve_selection=True)
        self.workspace.open_session(
            origin_route=route.value,
            origin_label=route_definition(route).label_he,
            ordered_document_ids=ids,
            current_document_id=document_id,
        )
        self.mode_stack.setCurrentWidget(self.workspace)
        self.workspace.setFocus()
        return True

    def refresh(self) -> None:
        """Reconcile the shared presentation model from the current store."""
        selections = self._queue_selections()
        self._documents = tuple(self._document_source.all())
        self._documents_by_id = {
            document.drive_file_id: document for document in self._documents
        }
        self.document_model.replace_documents(self._documents)
        self._restore_queue_selections(selections)
        self._refresh_shared_summaries()
        self._reconcile_workspace()

    def refresh_document(self, document_id: str) -> None:
        """Refresh one changed row by stable Drive ID, then reconcile shared counts."""
        getter = getattr(self._document_source, "get_by_drive_id", None)
        if getter is None:
            self.refresh()
            return
        selections = self._queue_selections()
        document = getter(document_id)
        if document is None:
            self._documents_by_id.pop(document_id, None)
            self.document_model.remove_document(document_id)
        else:
            self._documents_by_id[document_id] = document
            if not self.document_model.update_document(document):
                self.document_model.insert_document(document)
        self._documents = tuple(self._documents_by_id.values())
        self._restore_queue_selections(selections)
        self._refresh_shared_summaries()
        self._reconcile_workspace(changed_document_id=document_id)

    def _document_by_id(self, document_id: str) -> Document | None:
        return self._documents_by_id.get(document_id)

    def _return_from_workspace(self, origin_route: str, document_id: str) -> None:
        self.navigate(origin_route)
        view = self._views.get(AppRoute(origin_route))
        if isinstance(view, (DocumentQueueView, ReadyView)) and document_id:
            view.restore_selected_document_ids(self._workspace_origin_selection)
            view.focus_document(document_id, preserve_selection=True)

    def _return_from_benchmark(self) -> None:
        self.benchmark_page.release_source()
        self.navigate(self._current_route)

    def _reconcile_workspace(self, *, changed_document_id: str | None = None) -> None:
        if not hasattr(self, "workspace") or not self.workspace_active:
            return
        try:
            route = AppRoute(self.workspace.origin_route)
        except ValueError:
            return
        view = self._views.get(route)
        if isinstance(view, (DocumentQueueView, ReadyView)):
            self.workspace.reconcile_queue(
                view.ordered_visible_document_ids,
                self._documents_by_id,
                changed_document_id=changed_document_id,
            )

    def _refresh_shared_summaries(self) -> None:
        self._counts = calculate_queue_counts(self._documents)
        self.navigation.set_counts(self._counts)
        self.overview.refresh(self._documents)
        if (
            hasattr(self, "header_title")
            and not self.workspace_active
            and not self.benchmark_active
        ):
            self.navigate(self._current_route)

    def _connect_operational_tasks(self) -> None:
        if self.operational_controller is None:
            return
        self.operational_controller.documentUpdated.connect(self.refresh_document)
        self.operational_controller.reconciliationRequested.connect(self.refresh)
        self.operational_controller.availabilityChanged.connect(
            self._refresh_action_availability
        )

    def _connect_export_tasks(self) -> None:
        if self.export_controller is None:
            return
        self.export_controller.exportCompleted.connect(self._export_completed)
        self.export_controller.exportFailed.connect(self._export_failed)
        self.export_controller.availabilityChanged.connect(
            self._refresh_export_availability
        )

    def _submit_export(self, document_ids: object) -> None:
        if self.export_controller is None:
            return
        task_id = self.export_controller.submit_export(tuple(document_ids))
        if task_id is not None:
            self._refresh_export_availability()

    def _on_ready_batch_approved(self, _document_ids: object) -> None:
        self.refresh()

    def _export_completed(self, result: dict) -> None:
        if hasattr(self, "ready"):
            self.ready.show_export_result(result)
        self.refresh()

    def _export_failed(self, message: str) -> None:
        if hasattr(self, "ready"):
            self.ready.show_export_error(message)

    def _refresh_export_availability(self) -> None:
        if hasattr(self, "ready"):
            self.ready.set_export_pending(
                self.export_controller is not None
                and self.export_controller.has_pending_export
            )

    def _submit_scan(self) -> None:
        if self.operational_controller is not None:
            self.operational_controller.submit_scan()

    def _submit_process(self) -> None:
        if self.operational_controller is not None:
            self.operational_controller.submit_process()

    def _refresh_action_availability(self) -> None:
        if self.operational_controller is None:
            for button in (self.scan_button, self.process_button):
                button.setEnabled(False)
                button.setToolTip(_UNAVAILABLE_ACTION_REASON)
                button.setAccessibleDescription(_UNAVAILABLE_ACTION_REASON)
            if hasattr(self, "inbox") and self.inbox.process_button is not None:
                self.inbox.process_button.setEnabled(False)
            if hasattr(self, "inbox") and self.inbox.scan_button is not None:
                self.inbox.scan_button.setEnabled(False)
            if hasattr(self, "inbox") and self.inbox.empty_state.action_button is not None:
                self.inbox.empty_state.action_button.setEnabled(False)
            return

        scan_pending = self.operational_controller.has_pending_type(TaskType.DRIVE_SCAN)
        process_pending = self.operational_controller.has_pending_type(
            TaskType.DOCUMENT_PROCESSING
        )
        self._set_action_state(
            self.scan_button,
            not scan_pending,
            "הסריקה כבר פועלת או ממתינה בתור"
            if scan_pending
            else "סריקת Drive; הפעולה תמתין בתור אם משימת כתיבה אחרת פועלת",
        )
        self._set_action_state(
            self.process_button,
            not process_pending,
            "עיבוד המסמכים כבר פועל או ממתין בתור"
            if process_pending
            else "עיבוד מסמכים חדשים; הפעולה תמתין בתור אם משימת כתיבה אחרת פועלת",
        )
        if hasattr(self, "inbox") and self.inbox.process_button is not None:
            self._set_action_state(
                self.inbox.process_button,
                not process_pending,
                self.process_button.toolTip(),
            )
        if hasattr(self, "inbox") and self.inbox.empty_state.action_button is not None:
            self._set_action_state(
                self.inbox.empty_state.action_button,
                not scan_pending,
                self.scan_button.toolTip(),
            )
        if hasattr(self, "inbox") and self.inbox.scan_button is not None:
            self._set_action_state(
                self.inbox.scan_button,
                not scan_pending,
                self.scan_button.toolTip(),
            )

    @staticmethod
    def _set_action_state(button: PandaButton, enabled: bool, description: str) -> None:
        button.setEnabled(enabled)
        button.setToolTip(description)
        button.setAccessibleDescription(description)

    def _queue_selections(self) -> dict[AppRoute, tuple[str, ...]]:
        return {
            route: view.selected_document_ids
            for route, view in self._views.items()
            if isinstance(view, (DocumentQueueView, ReadyView))
        }

    def _restore_queue_selections(
        self, selections: dict[AppRoute, tuple[str, ...]]
    ) -> None:
        for route, document_ids in selections.items():
            view = self._views.get(route)
            if isinstance(view, (DocumentQueueView, ReadyView)):
                view.restore_selected_document_ids(document_ids)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "task_center"):
            self._position_task_center()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.task_manager.has_running_tasks:
            self.task_center.open_panel()
            QMessageBox.warning(
                self,
                "משימות עדיין פועלות",
                "לא ניתן לסגור את Panda בזמן שמשימת רקע פועלת. "
                "המתן לסיום המשימה או בטל אותה דרך מרכז המשימות אם הביטול נתמך.",
            )
            event.ignore()
            return
        if (
            hasattr(self, "workspace")
            and self.workspace_active
            and not self.workspace.confirm_discard_changes("close")
        ):
            event.ignore()
            return
        if (
            hasattr(self, "benchmark_page")
            and self.benchmark_active
            and not self.benchmark_page.confirm_discard_changes("close")
        ):
            event.ignore()
            return
        if hasattr(self, "benchmark_page"):
            self.benchmark_page.release_source()
        if self.operational_controller is not None:
            self.operational_controller.close()
        if self.export_controller is not None:
            self.export_controller.close()
        self.task_model.close()
        super().closeEvent(event)

    def _position_task_center(self) -> None:
        root = self.centralWidget()
        if root is None:
            return
        height = min(560, max(360, root.height() - 32))
        self.task_center.resize(360, height)
        x = max(16, root.width() - LAYOUT.navigation_width - 360 - 16)
        self.task_center.move(x, max(16, root.height() - height - 16))
