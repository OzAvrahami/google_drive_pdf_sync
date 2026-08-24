"""Central, UI-independent policy for Panda's persisted workflow statuses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class WorkflowAction(str, Enum):
    PROCESS = "process"
    OPEN_SOURCE = "open_source"
    MARK_IRRELEVANT = "mark_irrelevant"
    REVIEW_EDIT = "review_edit"
    SAVE_CORRECTIONS = "save_corrections"
    APPROVE = "approve"
    RETRY = "retry"
    RESOLVE_DUPLICATE = "resolve_duplicate"
    INSPECT_ERROR = "inspect_error"
    INSPECT = "inspect"
    OPEN_READ = "open_read"
    EXPORT = "export"


PERSISTED_STATUSES = frozenset(
    {
        "new",
        "processed",
        "needs_review",
        "failed",
        "skipped",
        "approved",
        "exported",
        "confirmed_irrelevant",
        "excluded",
    }
)


_STATUS_ACTIONS: dict[str, frozenset[WorkflowAction]] = {
    "new": frozenset(
        {
            WorkflowAction.PROCESS,
            WorkflowAction.OPEN_SOURCE,
            WorkflowAction.MARK_IRRELEVANT,
        }
    ),
    "processed": frozenset(
        {
            WorkflowAction.REVIEW_EDIT,
            WorkflowAction.SAVE_CORRECTIONS,
            WorkflowAction.APPROVE,
            WorkflowAction.RETRY,
            WorkflowAction.RESOLVE_DUPLICATE,
            WorkflowAction.MARK_IRRELEVANT,
        }
    ),
    "needs_review": frozenset(
        {
            WorkflowAction.REVIEW_EDIT,
            WorkflowAction.SAVE_CORRECTIONS,
            WorkflowAction.APPROVE,
            WorkflowAction.RETRY,
            WorkflowAction.RESOLVE_DUPLICATE,
            WorkflowAction.MARK_IRRELEVANT,
        }
    ),
    "failed": frozenset(
        {
            WorkflowAction.INSPECT_ERROR,
            WorkflowAction.RETRY,
            WorkflowAction.MARK_IRRELEVANT,
        }
    ),
    "skipped": frozenset(
        {
            WorkflowAction.INSPECT,
            WorkflowAction.RETRY,
            WorkflowAction.MARK_IRRELEVANT,
        }
    ),
    "approved": frozenset(
        {
            WorkflowAction.OPEN_READ,
            WorkflowAction.EXPORT,
        }
    ),
    "exported": frozenset(
        {
            WorkflowAction.OPEN_READ,
            WorkflowAction.OPEN_SOURCE,
        }
    ),
    "confirmed_irrelevant": frozenset(),
    "excluded": frozenset({WorkflowAction.OPEN_READ}),
}


_ACTION_TARGETS: dict[WorkflowAction, str] = {
    WorkflowAction.APPROVE: "approved",
    WorkflowAction.EXPORT: "exported",
    WorkflowAction.MARK_IRRELEVANT: "confirmed_irrelevant",
}


@dataclass(frozen=True)
class ActionAvailability:
    action: WorkflowAction
    allowed: bool
    reason_code: str | None = None
    target_status: str | None = None


def _status(subject: str | Any) -> str:
    return subject if isinstance(subject, str) else str(getattr(subject, "status", ""))


def available_actions(subject: str | Any) -> frozenset[WorkflowAction]:
    """Return actions available for a status or document.

    Document-specific secondary state narrows status-level capabilities; it
    never creates a persisted status.
    """
    actions = set(_STATUS_ACTIONS.get(_status(subject), frozenset()))
    if not isinstance(subject, str):
        if WorkflowAction.OPEN_SOURCE in actions and not getattr(subject, "local_path", ""):
            actions.remove(WorkflowAction.OPEN_SOURCE)
        if (
            WorkflowAction.RESOLVE_DUPLICATE in actions
            and not getattr(subject, "is_duplicate_suspected", False)
        ):
            actions.remove(WorkflowAction.RESOLVE_DUPLICATE)
    return frozenset(actions)


def action_availability(
    subject: str | Any, action: WorkflowAction
) -> ActionAvailability:
    status = _status(subject)
    target = _ACTION_TARGETS.get(action)
    if status not in PERSISTED_STATUSES:
        return ActionAvailability(action, False, "unknown_status", target)
    if action in available_actions(subject):
        return ActionAvailability(action, True, None, target)
    if action is WorkflowAction.APPROVE and status == "approved":
        reason = "already_approved"
    elif status in {"exported", "excluded"}:
        reason = "read_only_status"
    elif status == "confirmed_irrelevant":
        reason = "terminal_status"
    elif action is WorkflowAction.OPEN_SOURCE and not isinstance(subject, str):
        reason = "source_unavailable"
    elif action is WorkflowAction.RESOLVE_DUPLICATE and not isinstance(subject, str):
        reason = "duplicate_not_suspected"
    elif action is WorkflowAction.APPROVE:
        reason = "status_not_approvable"
    else:
        reason = "action_not_allowed_for_status"
    return ActionAvailability(action, False, reason, target)


def target_status_for(action: WorkflowAction) -> str | None:
    """Return a deterministic target status, or None for outcome-based actions."""
    return _ACTION_TARGETS.get(action)


def can_review_edit(subject: str | Any) -> bool:
    return WorkflowAction.REVIEW_EDIT in available_actions(subject)


def can_retry(subject: str | Any) -> bool:
    return WorkflowAction.RETRY in available_actions(subject)


def can_mark_irrelevant(subject: str | Any) -> bool:
    return WorkflowAction.MARK_IRRELEVANT in available_actions(subject)


def can_export(subject: str | Any) -> bool:
    return WorkflowAction.EXPORT in available_actions(subject)


def can_approve_structurally(subject: str | Any) -> bool:
    return WorkflowAction.APPROVE in available_actions(subject)
