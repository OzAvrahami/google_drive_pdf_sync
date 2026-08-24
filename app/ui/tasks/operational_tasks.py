"""Panda 2.0 orchestration for the existing operational QThread workers.

This module deliberately adapts the legacy workers rather than introducing a
second Drive or processing implementation.  The controller owns only task
submission and UI refresh signals; services remain responsible for the work.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal

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
from app.ui.workers import ProcessWorker, ScanWorker


WorkerFactory = Callable[[Any], Any]


class OperationalTaskController(QObject):
    """Submit current Panda workers through one session TaskManager."""

    documentUpdated = Signal(str)
    reconciliationRequested = Signal()
    availabilityChanged = Signal()

    def __init__(
        self,
        store: Any,
        task_manager: TaskManager,
        *,
        scan_worker_factory: WorkerFactory = ScanWorker,
        process_worker_factory: WorkerFactory = ProcessWorker,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.task_manager = task_manager
        self._scan_worker_factory = scan_worker_factory
        self._process_worker_factory = process_worker_factory
        self._unsubscribe = task_manager.subscribe(self._on_task_event)

    def submit_scan(self) -> str | None:
        """Submit one scan, or reject an already pending duplicate click."""
        if self.has_pending_type(TaskType.DRIVE_SCAN):
            return None
        worker = self._scan_worker_factory(self.store)
        adapter = adapt_existing_worker(worker, TaskType.DRIVE_SCAN)
        return self.task_manager.submit(
            task_type=TaskType.DRIVE_SCAN,
            title="סריקת Drive",
            description="איתור מסמכי PDF חדשים או מעודכנים ב-Drive",
            runner=adapter,
            access=TaskAccess.WRITE,
            cancellable=False,
        )

    def submit_process(self) -> str | None:
        """Submit one process-new run, serialized with other write tasks."""
        if self.has_pending_type(TaskType.DOCUMENT_PROCESSING):
            return None
        worker = self._process_worker_factory(self.store)
        adapter = adapt_existing_worker(
            worker,
            TaskType.DOCUMENT_PROCESSING,
            document_updated=self.documentUpdated.emit,
        )
        return self.task_manager.submit(
            task_type=TaskType.DOCUMENT_PROCESSING,
            title="עיבוד מסמכים חדשים",
            description="הורדה, חילוץ וניתוח של מסמכים במצב חדש",
            runner=adapter,
            access=TaskAccess.WRITE,
            cancellable=False,
        )

    def has_pending_type(self, task_type: TaskType) -> bool:
        return any(
            task.task_type is task_type and task.state not in TERMINAL_STATES
            for task in self.task_manager.tasks()
        )

    def close(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def _on_task_event(self, event: TaskEvent) -> None:
        self.availabilityChanged.emit()
        if event.event_type is not TaskEventType.COMPLETED:
            return
        task = self.task_manager.task(event.task_id)
        if (
            task.state is TaskState.SUCCEEDED
            and task.task_type in {TaskType.DRIVE_SCAN, TaskType.DOCUMENT_PROCESSING}
        ):
            self.reconciliationRequested.emit()

