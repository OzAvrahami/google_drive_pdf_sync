"""In-memory task lifecycle and scheduling for Panda 2.0.

This module deliberately has no Qt dependency.  UI and worker integrations observe
the manager through small callbacks and execution runners report through a scoped
``TaskReporter``.  Task history lasts only for the current application session.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol


class TaskType(str, Enum):
    DRIVE_SCAN = "drive_scan"
    DOCUMENT_PROCESSING = "document_processing"
    RETRY = "retry"
    BULK_PROCESSING = "bulk_processing"
    EXCEL_EXPORT = "excel_export"
    DEVELOPMENT = "development"
    OTHER = "other"


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskAccess(str, Enum):
    """Scheduling capability declared by the application submitting a task."""

    READ_ONLY = "read_only"
    WRITE = "write"


class TaskEventType(str, Enum):
    ADDED = "added"
    UPDATED = "updated"
    COMPLETED = "completed"
    REMOVED = "removed"


TERMINAL_STATES = frozenset(
    {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED}
)

_ALLOWED_TRANSITIONS = {
    TaskState.QUEUED: frozenset({TaskState.RUNNING, TaskState.CANCELLED}),
    TaskState.RUNNING: frozenset(
        {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.SUCCEEDED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


class TaskManagerError(RuntimeError):
    """Base error for invalid task-manager operations."""


class UnknownTaskError(TaskManagerError):
    pass


class InvalidTaskTransition(TaskManagerError):
    pass


class CancellationNotSupported(TaskManagerError):
    pass


class CancellationRejected(TaskManagerError):
    pass


@dataclass(frozen=True, slots=True)
class TaskResult:
    summary: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class TaskError:
    summary: str
    detail: str = ""
    diagnostic: str = field(default="", repr=False)


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    task_type: TaskType
    title: str
    description: str = ""
    access: TaskAccess = TaskAccess.WRITE
    state: TaskState = TaskState.QUEUED
    progress_current: int | None = None
    progress_total: int | None = None
    message: str = ""
    current_item: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancellable: bool = False
    cancel_requested: bool = False
    result: TaskResult | None = None
    error: TaskError | None = None

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def progress_fraction(self) -> float | None:
        if self.progress_current is None or not self.progress_total:
            return None
        return min(1.0, max(0.0, self.progress_current / self.progress_total))


@dataclass(frozen=True, slots=True)
class TaskEvent:
    event_type: TaskEventType
    task_id: str


class TaskRunner(Protocol):
    """Execution boundary owned by the manager until a task reaches a terminal state."""

    def start(self, reporter: "TaskReporter") -> None: ...

    def request_cancel(self) -> bool: ...


TaskObserver = Callable[[TaskEvent], None]
Clock = Callable[[], datetime]


class TaskReporter:
    """Task-scoped capability passed to one runner by ``TaskManager``."""

    def __init__(self, manager: "TaskManager", task_id: str) -> None:
        self._manager = manager
        self.task_id = task_id

    def progress(
        self,
        *,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
        current_item: str | None = None,
    ) -> None:
        self._manager.update_progress(
            self.task_id,
            current=current,
            total=total,
            message=message,
            current_item=current_item,
        )

    def succeed(self, result: TaskResult | str | None = None) -> None:
        if result is None:
            result = TaskResult("המשימה הושלמה")
        elif isinstance(result, str):
            result = TaskResult(result)
        self._manager.succeed(self.task_id, result)

    def fail(self, error: TaskError | str) -> None:
        if isinstance(error, str):
            error = task_error_from_message(error)
        self._manager.fail(self.task_id, error)

    def cancelled(self, summary: str = "המשימה בוטלה") -> None:
        self._manager.mark_cancelled(self.task_id, summary=summary)


def task_error_from_message(message: str) -> TaskError:
    """Build a bounded UI error while retaining the original text diagnostically."""

    original = str(message or "שגיאה לא ידועה")
    first_line = next((line.strip() for line in original.splitlines() if line.strip()), "שגיאה לא ידועה")
    summary = first_line[:240]
    detail = original[:2000] if original != summary else ""
    return TaskError(summary=summary, detail=detail, diagnostic=original)


class TaskManager:
    """Own task state, runner lifetimes, bounded history, and Panda scheduling."""

    def __init__(
        self,
        *,
        history_limit: int = 50,
        clock: Clock | None = None,
    ) -> None:
        if history_limit < 0:
            raise ValueError("history_limit must be non-negative")
        self._history_limit = history_limit
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._tasks: dict[str, TaskRecord] = {}
        self._order: list[str] = []
        self._completed: deque[str] = deque()
        self._write_queue: deque[str] = deque()
        self._running_write_id: str | None = None
        self._runners: dict[str, TaskRunner] = {}
        self._observers: list[TaskObserver] = []
        self._next_id = 1

    @property
    def history_limit(self) -> int:
        return self._history_limit

    @property
    def has_running_tasks(self) -> bool:
        return any(task.state is TaskState.RUNNING for task in self._tasks.values())

    @property
    def has_pending_tasks(self) -> bool:
        return any(
            task.state in {TaskState.QUEUED, TaskState.RUNNING}
            for task in self._tasks.values()
        )

    def subscribe(self, observer: TaskObserver) -> Callable[[], None]:
        self._observers.append(observer)

        def unsubscribe() -> None:
            try:
                self._observers.remove(observer)
            except ValueError:
                pass

        return unsubscribe

    def tasks(self) -> tuple[TaskRecord, ...]:
        return tuple(self._snapshot(self._tasks[task_id]) for task_id in self._order)

    def task(self, task_id: str) -> TaskRecord:
        return self._snapshot(self._get(task_id))

    def active_tasks(self) -> tuple[TaskRecord, ...]:
        return tuple(task for task in self.tasks() if task.state is TaskState.RUNNING)

    def queued_tasks(self) -> tuple[TaskRecord, ...]:
        return tuple(task for task in self.tasks() if task.state is TaskState.QUEUED)

    def completed_tasks(self) -> tuple[TaskRecord, ...]:
        return tuple(
            self._snapshot(self._tasks[task_id])
            for task_id in reversed(self._completed)
            if task_id in self._tasks
        )

    def primary_task(self) -> TaskRecord | None:
        running = self.active_tasks()
        if running:
            write = next((task for task in running if task.access is TaskAccess.WRITE), None)
            return write or running[0]
        queued = self.queued_tasks()
        if queued:
            return queued[0]
        completed = self.completed_tasks()
        return completed[0] if completed else None

    def submit(
        self,
        *,
        task_type: TaskType,
        title: str,
        runner: TaskRunner,
        description: str = "",
        access: TaskAccess = TaskAccess.WRITE,
        cancellable: bool = False,
    ) -> str:
        if not title.strip():
            raise ValueError("task title is required")
        task_id = f"task-{self._next_id:06d}"
        self._next_id += 1
        record = TaskRecord(
            task_id=task_id,
            task_type=TaskType(task_type),
            title=title.strip(),
            description=description.strip(),
            access=TaskAccess(access),
            created_at=self._now(),
            cancellable=bool(cancellable),
        )
        self._tasks[task_id] = record
        self._order.append(task_id)
        self._runners[task_id] = runner
        self._emit(TaskEventType.ADDED, task_id)

        if record.access is TaskAccess.WRITE:
            self._write_queue.append(task_id)
            self._start_next_write()
        else:
            # Read-only concurrency is opt-in through the explicit access flag.
            self._start(task_id)
        return task_id

    def update_progress(
        self,
        task_id: str,
        *,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
        current_item: str | None = None,
    ) -> None:
        record = self._get(task_id)
        self._require_state(record, TaskState.RUNNING)
        if total is not None and total <= 0:
            raise ValueError("progress total must be positive")
        if current is not None and current < 0:
            raise ValueError("progress current must be non-negative")
        if current is not None:
            record.progress_current = current
        if total is not None:
            record.progress_total = total
        if record.progress_current is not None and record.progress_total is not None:
            record.progress_current = min(record.progress_current, record.progress_total)
        if message is not None:
            record.message = str(message)
        if current_item is not None:
            record.current_item = str(current_item)
        self._emit(TaskEventType.UPDATED, task_id)

    def succeed(self, task_id: str, result: TaskResult) -> None:
        record = self._get(task_id)
        self._transition(record, TaskState.SUCCEEDED)
        record.result = result
        self._complete(record)

    def fail(self, task_id: str, error: TaskError) -> None:
        record = self._get(task_id)
        self._transition(record, TaskState.FAILED)
        record.error = error
        self._complete(record)

    def mark_cancelled(self, task_id: str, *, summary: str = "המשימה בוטלה") -> None:
        record = self._get(task_id)
        self._transition(record, TaskState.CANCELLED)
        record.result = TaskResult(summary)
        self._complete(record)

    def cancel(self, task_id: str) -> bool:
        record = self._get(task_id)
        if record.is_terminal:
            raise InvalidTaskTransition(f"completed task {task_id} is immutable")
        if record.state is TaskState.QUEUED:
            try:
                self._write_queue.remove(task_id)
            except ValueError:
                pass
            self._transition(record, TaskState.CANCELLED)
            record.result = TaskResult("המשימה הוסרה מהתור")
            self._complete(record)
            return True
        if not record.cancellable:
            raise CancellationNotSupported(f"task {task_id} does not support cancellation")
        runner = self._runners.get(task_id)
        if runner is None:
            raise CancellationRejected(f"task {task_id} has no active runner")
        record.cancel_requested = True
        self._emit(TaskEventType.UPDATED, task_id)
        if not runner.request_cancel():
            record.cancel_requested = False
            self._emit(TaskEventType.UPDATED, task_id)
            raise CancellationRejected(f"task {task_id} rejected cancellation")
        return True

    def _start_next_write(self) -> None:
        if self._running_write_id is not None:
            return
        while self._write_queue:
            task_id = self._write_queue.popleft()
            record = self._tasks.get(task_id)
            if record is not None and record.state is TaskState.QUEUED:
                self._running_write_id = task_id
                self._start(task_id)
                return

    def _start(self, task_id: str) -> None:
        record = self._get(task_id)
        self._transition(record, TaskState.RUNNING)
        self._emit(TaskEventType.UPDATED, task_id)
        reporter = TaskReporter(self, task_id)
        try:
            self._runners[task_id].start(reporter)
        except Exception as exc:
            if self._tasks[task_id].state is TaskState.RUNNING:
                self.fail(task_id, task_error_from_message(str(exc)))

    def _complete(self, record: TaskRecord) -> None:
        record.completed_at = self._now()
        record.cancel_requested = False
        task_id = record.task_id
        self._runners.pop(task_id, None)
        if self._running_write_id == task_id:
            self._running_write_id = None
        self._completed.append(task_id)
        self._emit(TaskEventType.COMPLETED, task_id)
        self._trim_history()
        self._start_next_write()

    def _trim_history(self) -> None:
        while len(self._completed) > self._history_limit:
            task_id = self._completed.popleft()
            if task_id not in self._tasks:
                continue
            self._tasks.pop(task_id)
            try:
                self._order.remove(task_id)
            except ValueError:
                pass
            self._emit(TaskEventType.REMOVED, task_id)

    def _transition(self, record: TaskRecord, target: TaskState) -> None:
        if target not in _ALLOWED_TRANSITIONS[record.state]:
            raise InvalidTaskTransition(
                f"invalid task transition: {record.state.value} -> {target.value}"
            )
        record.state = target
        if target is TaskState.RUNNING:
            record.started_at = self._now()

    @staticmethod
    def _require_state(record: TaskRecord, expected: TaskState) -> None:
        if record.state is not expected:
            raise InvalidTaskTransition(
                f"task {record.task_id} is {record.state.value}, expected {expected.value}"
            )

    def _get(self, task_id: str) -> TaskRecord:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise UnknownTaskError(f"unknown task: {task_id}") from exc

    def _emit(self, event_type: TaskEventType, task_id: str) -> None:
        event = TaskEvent(event_type, task_id)
        for observer in tuple(self._observers):
            observer(event)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _snapshot(record: TaskRecord) -> TaskRecord:
        return replace(record)

