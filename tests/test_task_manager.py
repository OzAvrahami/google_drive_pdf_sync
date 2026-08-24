from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.application.task_manager import (
    CancellationNotSupported,
    CancellationRejected,
    InvalidTaskTransition,
    TaskAccess,
    TaskError,
    TaskEventType,
    TaskManager,
    TaskResult,
    TaskState,
    TaskType,
)


class ManualRunner:
    def __init__(self, *, accept_cancel: bool = False, complete_on_cancel: bool = False) -> None:
        self.reporter = None
        self.starts = 0
        self.cancel_requests = 0
        self.accept_cancel = accept_cancel
        self.complete_on_cancel = complete_on_cancel

    def start(self, reporter) -> None:
        self.reporter = reporter
        self.starts += 1

    def request_cancel(self) -> bool:
        self.cancel_requests += 1
        if self.accept_cancel and self.complete_on_cancel:
            self.reporter.cancelled()
        return self.accept_cancel


class ImmediateRunner(ManualRunner):
    def __init__(self, outcome: str = "success") -> None:
        super().__init__()
        self.outcome = outcome

    def start(self, reporter) -> None:
        super().start(reporter)
        if self.outcome == "success":
            reporter.succeed(TaskResult("done", {"count": 3}))
        elif self.outcome == "failure":
            reporter.fail(TaskError("failed", "detail", "diagnostic"))
        else:
            raise RuntimeError("start exploded")


class TickClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        current = self.value
        self.value += timedelta(seconds=1)
        return current


def submit(manager: TaskManager, runner=None, **overrides) -> tuple[str, ManualRunner]:
    runner = runner or ManualRunner()
    values = {
        "task_type": TaskType.DEVELOPMENT,
        "title": "Synthetic task",
        "runner": runner,
        "access": TaskAccess.WRITE,
    }
    values.update(overrides)
    return manager.submit(**values), runner


def test_first_write_task_starts_with_stable_id_and_timestamps() -> None:
    manager = TaskManager(clock=TickClock())
    task_id, _ = submit(manager)

    record = manager.task(task_id)
    assert task_id == "task-000001"
    assert record.state is TaskState.RUNNING
    assert record.created_at < record.started_at
    assert record.completed_at is None


def test_second_write_task_is_created_queued() -> None:
    manager = TaskManager()
    submit(manager)
    task_id, runner = submit(manager)

    assert manager.task(task_id).state is TaskState.QUEUED
    assert runner.starts == 0


def test_progress_updates_current_total_message_and_item() -> None:
    manager = TaskManager()
    task_id, runner = submit(manager)
    runner.reporter.progress(current=4, total=10, message="working", current_item="one.pdf")

    record = manager.task(task_id)
    assert (record.progress_current, record.progress_total) == (4, 10)
    assert record.progress_fraction == pytest.approx(0.4)
    assert (record.message, record.current_item) == ("working", "one.pdf")


def test_success_sets_result_completion_timestamp_and_immutability() -> None:
    manager = TaskManager(clock=TickClock())
    task_id, runner = submit(manager)
    runner.reporter.succeed(TaskResult("3 completed", {"count": 3}))

    record = manager.task(task_id)
    assert record.state is TaskState.SUCCEEDED
    assert record.result.summary == "3 completed"
    assert record.result.metadata["count"] == 3
    assert record.completed_at > record.started_at
    with pytest.raises(InvalidTaskTransition):
        runner.reporter.progress(message="late")


def test_failure_preserves_bounded_ui_error_and_diagnostic() -> None:
    manager = TaskManager()
    task_id, runner = submit(manager)
    runner.reporter.fail(TaskError("Useful failure", "short detail", "traceback"))

    error = manager.task(task_id).error
    assert manager.task(task_id).state is TaskState.FAILED
    assert error.summary == "Useful failure"
    assert error.detail == "short detail"
    assert error.diagnostic == "traceback"


def test_invalid_backward_or_duplicate_transition_is_rejected() -> None:
    manager = TaskManager()
    task_id, runner = submit(manager)
    runner.reporter.succeed("done")
    with pytest.raises(InvalidTaskTransition):
        manager.succeed(task_id, TaskResult("again"))


def test_write_tasks_are_fifo_and_never_overlap() -> None:
    manager = TaskManager()
    first_id, first = submit(manager)
    second_id, second = submit(manager)
    third_id, third = submit(manager)

    assert first.starts == 1 and second.starts == third.starts == 0
    first.reporter.succeed("first")
    assert manager.task(second_id).state is TaskState.RUNNING
    assert second.starts == 1 and third.starts == 0
    second.reporter.succeed("second")
    assert manager.task(third_id).state is TaskState.RUNNING
    assert third.starts == 1
    assert manager.task(first_id).state is TaskState.SUCCEEDED


def test_failure_releases_next_queued_write() -> None:
    manager = TaskManager()
    _, first = submit(manager)
    second_id, second = submit(manager)
    first.reporter.fail("failed")
    assert second.starts == 1
    assert manager.task(second_id).state is TaskState.RUNNING


def test_queued_task_can_be_cancelled_without_starting() -> None:
    manager = TaskManager()
    submit(manager)
    queued_id, queued = submit(manager)

    assert manager.cancel(queued_id) is True
    assert manager.task(queued_id).state is TaskState.CANCELLED
    assert queued.starts == 0


def test_running_non_cancellable_task_rejects_cancel() -> None:
    manager = TaskManager()
    task_id, _ = submit(manager, cancellable=False)
    with pytest.raises(CancellationNotSupported):
        manager.cancel(task_id)
    assert manager.task(task_id).state is TaskState.RUNNING


def test_supported_running_cancellation_is_cooperative() -> None:
    manager = TaskManager()
    runner = ManualRunner(accept_cancel=True, complete_on_cancel=True)
    task_id, _ = submit(manager, runner, cancellable=True)

    assert manager.cancel(task_id) is True
    assert manager.task(task_id).state is TaskState.CANCELLED
    assert runner.cancel_requests == 1


def test_declared_cancellation_is_rejected_when_runner_refuses() -> None:
    manager = TaskManager()
    runner = ManualRunner(accept_cancel=False)
    task_id, _ = submit(manager, runner, cancellable=True)

    with pytest.raises(CancellationRejected):
        manager.cancel(task_id)
    assert manager.task(task_id).state is TaskState.RUNNING
    assert manager.task(task_id).cancel_requested is False


def test_read_only_task_runs_independently_of_write_task() -> None:
    manager = TaskManager()
    _, write = submit(manager)
    read_id, read = submit(manager, access=TaskAccess.READ_ONLY)

    assert write.starts == read.starts == 1
    assert manager.task(read_id).state is TaskState.RUNNING
    assert len(manager.active_tasks()) == 2


def test_primary_task_prefers_running_write_over_read() -> None:
    manager = TaskManager()
    write_id, _ = submit(manager)
    submit(manager, access=TaskAccess.READ_ONLY)
    assert manager.primary_task().task_id == write_id


def test_bounded_history_removes_oldest_completed_record() -> None:
    manager = TaskManager(history_limit=2)
    ids = [submit(manager, ImmediateRunner())[0] for _ in range(3)]

    assert [task.task_id for task in manager.completed_tasks()] == [ids[2], ids[1]]
    assert [task.task_id for task in manager.tasks()] == ids[1:]


def test_events_include_added_updates_completion_and_history_removal() -> None:
    manager = TaskManager(history_limit=0)
    events = []
    manager.subscribe(events.append)
    task_id, runner = submit(manager)
    runner.reporter.succeed("done")

    assert [(event.event_type, event.task_id) for event in events] == [
        (TaskEventType.ADDED, task_id),
        (TaskEventType.UPDATED, task_id),
        (TaskEventType.COMPLETED, task_id),
        (TaskEventType.REMOVED, task_id),
    ]


def test_runner_start_exception_becomes_failed_task_and_queue_continues() -> None:
    manager = TaskManager()
    failed_id, _ = submit(manager, ImmediateRunner("exception"))
    next_id, _ = submit(manager, ImmediateRunner())

    assert manager.task(failed_id).state is TaskState.FAILED
    assert manager.task(failed_id).error.summary == "start exploded"
    assert manager.task(next_id).state is TaskState.SUCCEEDED


def test_external_task_snapshots_cannot_mutate_manager_state() -> None:
    manager = TaskManager()
    task_id, _ = submit(manager)
    snapshot = manager.task(task_id)
    snapshot.title = "mutated outside"
    assert manager.task(task_id).title == "Synthetic task"
