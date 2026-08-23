"""Pure-domain tests for workflow capabilities and Panda 2.0 status metadata."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domain.status_presentation import (
    NavigationDestination,
    STATUS_PRESENTATION,
    presentation_for,
)
from app.domain.workflow_policy import (
    PERSISTED_STATUSES,
    WorkflowAction,
    action_availability,
    available_actions,
    can_approve_structurally,
    target_status_for,
)


EXPECTED_ACTIONS = {
    "new": {"process", "open_source", "mark_irrelevant"},
    "processed": {
        "review_edit",
        "approve",
        "retry",
        "resolve_duplicate",
        "mark_irrelevant",
    },
    "needs_review": {
        "review_edit",
        "save_corrections",
        "approve",
        "retry",
        "resolve_duplicate",
        "mark_irrelevant",
    },
    "failed": {"inspect_error", "retry", "mark_irrelevant"},
    "skipped": {"inspect", "retry", "mark_irrelevant"},
    "approved": {"open_read", "export"},
    "exported": {"open_read", "open_source"},
    "confirmed_irrelevant": set(),
    "excluded": {"open_read"},
}


@pytest.mark.parametrize("status", sorted(PERSISTED_STATUSES))
def test_every_persisted_status_has_explicit_actions(status: str) -> None:
    assert {action.value for action in available_actions(status)} == EXPECTED_ACTIONS[status]


@pytest.mark.parametrize("status", ["processed", "needs_review"])
def test_processed_and_needs_review_are_structurally_approvable(status: str) -> None:
    assert can_approve_structurally(status) is True


@pytest.mark.parametrize(
    "status",
    ["new", "failed", "skipped", "approved", "exported", "confirmed_irrelevant", "excluded"],
)
def test_other_statuses_are_not_structurally_approvable(status: str) -> None:
    assert can_approve_structurally(status) is False


def test_document_secondary_state_only_narrows_duplicate_and_source_actions() -> None:
    doc = SimpleNamespace(
        status="processed", local_path="", is_duplicate_suspected=False
    )

    assert WorkflowAction.RESOLVE_DUPLICATE not in available_actions(doc)
    assert action_availability(doc, WorkflowAction.RESOLVE_DUPLICATE).reason_code == (
        "duplicate_not_suspected"
    )


def test_action_targets_preserve_existing_persisted_status_values() -> None:
    assert target_status_for(WorkflowAction.APPROVE) == "approved"
    assert target_status_for(WorkflowAction.EXPORT) == "exported"
    assert target_status_for(WorkflowAction.MARK_IRRELEVANT) == "confirmed_irrelevant"
    assert target_status_for(WorkflowAction.RETRY) is None
    assert target_status_for(WorkflowAction.PROCESS) is None


def test_unavailable_action_has_stable_reason_code() -> None:
    decision = action_availability("failed", WorkflowAction.APPROVE)

    assert decision.allowed is False
    assert decision.reason_code == "status_not_approvable"


EXPECTED_PRESENTATION = {
    "new": ("חדש", "נכנסו", NavigationDestination.INBOX),
    "processed": ("מוכן לאישור", "מוכן", NavigationDestination.READY),
    "needs_review": ("לבדיקה", "דורש טיפול", NavigationDestination.ATTENTION),
    "failed": ("נכשל", "דורש טיפול", NavigationDestination.ATTENTION),
    "skipped": ("דולג", "דורש טיפול", NavigationDestination.ATTENTION),
    "approved": ("מוכן לייצוא", "מוכן", NavigationDestination.READY),
    "exported": ("יוצא", "היסטוריה", NavigationDestination.HISTORY),
    "confirmed_irrelevant": (
        "לא רלוונטי",
        "לא רלוונטי",
        NavigationDestination.IRRELEVANT,
    ),
    "excluded": (
        "לא רלוונטי",
        "לא רלוונטי",
        NavigationDestination.IRRELEVANT,
    ),
}


@pytest.mark.parametrize("status", sorted(PERSISTED_STATUSES))
def test_status_presentation_matches_approved_labels_and_routes(status: str) -> None:
    presentation = presentation_for(status)
    label, route_label, route = EXPECTED_PRESENTATION[status]

    assert presentation.label_he == label
    assert presentation.navigation_label_he == route_label
    assert presentation.navigation is route


def test_status_presentation_covers_exact_persisted_status_set() -> None:
    assert frozenset(STATUS_PRESENTATION) == PERSISTED_STATUSES


def test_unknown_presentation_status_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown persisted workflow status"):
        presentation_for("ready")
