"""Shared presentation semantics for in-memory Panda tasks."""

from __future__ import annotations

from datetime import datetime

from app.application.task_manager import TaskRecord, TaskState


TASK_STATE_LABELS: dict[TaskState, str] = {
    TaskState.QUEUED: "בתור",
    TaskState.RUNNING: "פועלת",
    TaskState.SUCCEEDED: "הושלמה",
    TaskState.FAILED: "נכשלה",
    TaskState.CANCELLED: "בוטלה",
}

TASK_STATE_SEMANTICS: dict[TaskState, str] = {
    TaskState.QUEUED: "queued",
    TaskState.RUNNING: "running",
    TaskState.SUCCEEDED: "succeeded",
    TaskState.FAILED: "failed",
    TaskState.CANCELLED: "cancelled",
}


def task_detail(record: TaskRecord) -> str:
    if record.state is TaskState.FAILED and record.error is not None:
        return record.error.summary
    if record.is_terminal and record.result is not None:
        return record.result.summary
    return record.current_item or record.message or record.description


def progress_text(record: TaskRecord) -> str:
    if record.progress_current is None or record.progress_total is None:
        return TASK_STATE_LABELS[record.state]
    return f"{record.progress_current} / {record.progress_total}"


def completion_time(value: datetime | None) -> str:
    return value.astimezone().strftime("%H:%M") if value is not None else ""

