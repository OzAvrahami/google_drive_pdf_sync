"""Normalize legacy QThread worker signals into the Panda 2.0 task contract."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from PySide6.QtCore import QObject, Slot

from app.application.task_manager import (
    TaskError,
    TaskReporter,
    TaskResult,
    TaskType,
    task_error_from_message,
)


ResultSummaryBuilder = Callable[[Mapping[str, Any]], str]


def _summary_for(task_type: TaskType, result: Mapping[str, Any]) -> str:
    if task_type is TaskType.DRIVE_SCAN:
        new = result.get("new", result.get("new_files"))
        updated = result.get("updated", result.get("updated_files"))
        if new is not None or updated is not None:
            return f"סריקת Drive הושלמה: {int(new or 0)} חדשים, {int(updated or 0)} עודכנו"
        return "סריקת Drive הושלמה"
    if task_type in {TaskType.DOCUMENT_PROCESSING, TaskType.BULK_PROCESSING}:
        processed = result.get("success", result.get("processed"))
        failed = result.get("failed")
        if processed is not None or failed is not None:
            return f"העיבוד הושלם: {int(processed or 0)} הצליחו, {int(failed or 0)} נכשלו"
        return "עיבוד המסמכים הושלם"
    if task_type is TaskType.RETRY:
        return "העיבוד מחדש הושלם"
    if task_type is TaskType.EXCEL_EXPORT:
        return f"הייצוא הושלם: {int(result.get('exported', 0))} רשומות"
    return "המשימה הושלמה"


class ExistingWorkerAdapter(QObject):
    """Own one existing worker and translate its heterogeneous signal set.

    Legacy workers all expose ``progress``, ``finished`` and ``error``.  Only
    Process/Retry/Bulk workers expose ``step`` and only ProcessWorker exposes
    ``doc_updated``.  The adapter treats those signals as optional and does not
    advertise cancellation because none of the current workers supports a safe
    cooperative stop boundary.
    """

    def __init__(
        self,
        worker: Any,
        task_type: TaskType,
        *,
        result_summary: ResultSummaryBuilder | None = None,
        document_updated: Callable[[str], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._worker = worker
        self._task_type = TaskType(task_type)
        self._result_summary = result_summary
        self._document_updated = document_updated
        self._reporter: TaskReporter | None = None
        self._completed = False
        self._connections_made = False

    @property
    def worker(self) -> Any | None:
        return self._worker

    @property
    def completed(self) -> bool:
        return self._completed

    def start(self, reporter: TaskReporter) -> None:
        if self._connections_made:
            raise RuntimeError("worker adapter can only be started once")
        if self._worker is None:
            raise RuntimeError("worker is no longer available")
        self._reporter = reporter
        self._connect("progress", self._on_progress)
        self._connect("step", self._on_step)
        self._connect("doc_updated", self._on_document_updated)
        self._connect("finished", self._on_finished, required=True)
        self._connect("error", self._on_error, required=True)
        self._connections_made = True
        self._worker.start()

    def request_cancel(self) -> bool:
        # None of Panda's existing operational workers exposes cooperative cancel.
        return False

    def _connect(self, name: str, callback: Callable[..., None], *, required: bool = False) -> None:
        signal = getattr(self._worker, name, None)
        if signal is None or not hasattr(signal, "connect"):
            if required:
                raise TypeError(f"worker is missing required signal: {name}")
            return
        signal.connect(callback)

    @Slot(str)
    def _on_progress(self, message: str) -> None:
        if self._can_report:
            self._reporter.progress(message=str(message))

    @Slot(int, int, str)
    def _on_step(self, current: int, total: int, item: str) -> None:
        if self._can_report:
            self._reporter.progress(
                current=max(0, int(current)),
                total=max(1, int(total)),
                current_item=str(item),
            )

    @Slot(str)
    def _on_document_updated(self, document_id: str) -> None:
        if not self._completed and self._document_updated is not None:
            self._document_updated(str(document_id))

    @Slot(dict)
    def _on_finished(self, result: Mapping[str, Any] | None = None) -> None:
        if not self._finish_once():
            return
        data = dict(result or {})
        summary = (
            self._result_summary(data)
            if self._result_summary is not None
            else _summary_for(self._task_type, data)
        )
        assert self._reporter is not None
        self._reporter.succeed(TaskResult(summary=summary, metadata=data))
        self._release_worker()

    @Slot(str)
    def _on_error(self, message: str) -> None:
        if not self._finish_once():
            return
        error = task_error_from_message(str(message))
        assert self._reporter is not None
        self._reporter.fail(
            TaskError(
                summary=error.summary,
                detail=error.detail,
                diagnostic=error.diagnostic,
            )
        )
        self._release_worker()

    @property
    def _can_report(self) -> bool:
        return not self._completed and self._reporter is not None

    def _finish_once(self) -> bool:
        if self._completed or self._reporter is None:
            return False
        self._completed = True
        return True

    def _release_worker(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None and hasattr(worker, "deleteLater"):
            worker.deleteLater()


def adapt_existing_worker(
    worker: Any,
    task_type: TaskType,
    *,
    result_summary: ResultSummaryBuilder | None = None,
    document_updated: Callable[[str], None] | None = None,
) -> ExistingWorkerAdapter:
    """Return a non-cancellable adapter for any current Panda worker class."""

    return ExistingWorkerAdapter(
        worker,
        task_type,
        result_summary=result_summary,
        document_updated=document_updated,
    )

