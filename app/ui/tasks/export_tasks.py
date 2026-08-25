"""Panda 2.0 selected Excel-export task boundary."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any
from weakref import ref

from PySide6.QtCore import QObject, QThread, Signal

from app.application.export_service import ExportOutcome, ExportService
from app.application.task_manager import (
    TERMINAL_STATES,
    TaskAccess,
    TaskEvent,
    TaskEventType,
    TaskManager,
    TaskState,
    TaskType,
)
from app.ui.tasks.worker_adapters import adapt_existing_worker


class SelectedExportWorker(QThread):
    """Run one selected-ID ExportService call away from the UI thread."""

    progress = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, service: ExportService, document_ids: Sequence[str]) -> None:
        super().__init__()
        self._service = service
        self._document_ids = tuple(document_ids)

    def run(self) -> None:
        try:
            self.progress.emit(f"מייצא {len(self._document_ids)} מסמכים נבחרים…")
            result = self._service.export_selected(self._document_ids)
            self.finished.emit(
                {
                    "requested_ids": result.requested_ids,
                    "eligible_ids": result.eligible_ids,
                    "written_ids": result.written_ids,
                    "already_present_ids": result.already_present_ids,
                    "transitioned_ids": result.transitioned_ids,
                    "missing_ids": result.missing_ids,
                    "ineligible_ids": result.ineligible_ids,
                    "status_persistence_error": result.status_persistence_error,
                    "outcome": result.outcome.value,
                    "exported": result.exported_count,
                    "path": result.workbook_path,
                }
            )
        except Exception as exc:
            self.error.emit(str(exc))


ExportWorkerFactory = Callable[[ExportService, Sequence[str]], Any]


class ExportTaskController(QObject):
    """Submit selected exports through Panda's serialized WRITE task lane."""

    exportCompleted = Signal(dict)
    exportFailed = Signal(str)
    reconciliationRequested = Signal()
    availabilityChanged = Signal()

    def __init__(
        self,
        export_service: ExportService,
        task_manager: TaskManager,
        *,
        worker_factory: ExportWorkerFactory = SelectedExportWorker,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.export_service = export_service
        self.task_manager = task_manager
        self._worker_factory = worker_factory
        controller_ref = ref(self)

        def observe(event: TaskEvent) -> None:
            controller = controller_ref()
            if controller is not None:
                controller._on_task_event(event)

        self._observer = observe
        self._unsubscribe = task_manager.subscribe(observe)

    def submit_export(self, document_ids: Sequence[str]) -> str | None:
        ids = tuple(dict.fromkeys(str(value) for value in document_ids))
        if not ids or self.has_pending_export:
            return None
        worker = self._worker_factory(self.export_service, ids)
        worker.finished.connect(self.exportCompleted)
        worker.error.connect(self.exportFailed)
        adapter = adapt_existing_worker(
            worker,
            TaskType.EXCEL_EXPORT,
            result_summary=self._summary,
        )
        return self.task_manager.submit(
            task_type=TaskType.EXCEL_EXPORT,
            title="ייצוא לאקסל",
            description=f"ייצוא {len(ids)} מסמכים נבחרים",
            runner=adapter,
            access=TaskAccess.WRITE,
            cancellable=False,
        )

    @property
    def has_pending_export(self) -> bool:
        return any(
            task.task_type is TaskType.EXCEL_EXPORT
            and task.state not in TERMINAL_STATES
            for task in self.task_manager.tasks()
        )

    def close(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @staticmethod
    def _summary(result: dict) -> str:
        outcome = result.get("outcome")
        count = int(result.get("exported", 0))
        if outcome == ExportOutcome.PARTIAL.value:
            return f"הייצוא הושלם חלקית: {count} מסמכים"
        return f"הייצוא הושלם: {count} מסמכים"

    def _on_task_event(self, event: TaskEvent) -> None:
        self.availabilityChanged.emit()
        if event.event_type is not TaskEventType.COMPLETED:
            return
        task = self.task_manager.task(event.task_id)
        if task.task_type is not TaskType.EXCEL_EXPORT:
            return
        if task.state is TaskState.SUCCEEDED:
            self.reconciliationRequested.emit()
