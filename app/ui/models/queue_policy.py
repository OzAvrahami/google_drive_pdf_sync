"""Shared route membership, queue segments, and count calculations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Protocol

from app.domain.status_presentation import presentation_for


class QueueRoute(str, Enum):
    INBOX = "inbox"
    ATTENTION = "attention"
    READY = "ready"
    IRRELEVANT = "irrelevant"
    HISTORY = "history"


class ReadySegment(str, Enum):
    ALL = "all"
    READY_TO_APPROVE = "ready_to_approve"
    READY_TO_EXPORT = "ready_to_export"


class AttentionSegment(str, Enum):
    ALL = "all"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    SKIPPED = "skipped"
    SUSPECTED_DUPLICATE = "suspected_duplicate"


class QueueSubject(Protocol):
    status: str
    is_duplicate_suspected: bool
    was_manually_corrected: bool


def route_for(subject: QueueSubject) -> QueueRoute:
    """Return one primary queue route; duplicate suspicion overrides status."""
    if bool(getattr(subject, "is_duplicate_suspected", False)):
        return QueueRoute.ATTENTION
    return QueueRoute(presentation_for(subject.status).navigation.value)


def belongs_to_route(subject: QueueSubject, route: QueueRoute) -> bool:
    return route_for(subject) is route


def matches_ready_segment(subject: QueueSubject, segment: ReadySegment) -> bool:
    if route_for(subject) is not QueueRoute.READY:
        return False
    if segment is ReadySegment.ALL:
        return True
    if segment is ReadySegment.READY_TO_APPROVE:
        return subject.status == "processed"
    return subject.status == "approved"


def matches_attention_segment(subject: QueueSubject, segment: AttentionSegment) -> bool:
    if route_for(subject) is not QueueRoute.ATTENTION:
        return False
    if segment is AttentionSegment.ALL:
        return True
    if segment is AttentionSegment.SUSPECTED_DUPLICATE:
        return bool(getattr(subject, "is_duplicate_suspected", False))
    return subject.status == segment.value


@dataclass(frozen=True, slots=True)
class ReadyCounts:
    all: int = 0
    ready_to_approve: int = 0
    ready_to_export: int = 0
    manually_corrected: int = 0


@dataclass(frozen=True, slots=True)
class AttentionCounts:
    all: int = 0
    needs_review: int = 0
    failed: int = 0
    skipped: int = 0
    suspected_duplicate: int = 0


@dataclass(frozen=True, slots=True)
class QueueCounts:
    inbox: int
    attention: int
    ready: int
    irrelevant: int
    history: int
    ready_breakdown: ReadyCounts
    attention_breakdown: AttentionCounts

    def for_route(self, route: QueueRoute) -> int:
        return {
            QueueRoute.INBOX: self.inbox,
            QueueRoute.ATTENTION: self.attention,
            QueueRoute.READY: self.ready,
            QueueRoute.IRRELEVANT: self.irrelevant,
            QueueRoute.HISTORY: self.history,
        }[route]


def calculate_queue_counts(subjects: Iterable[QueueSubject]) -> QueueCounts:
    route_counts = {route: 0 for route in QueueRoute}
    ready = {segment: 0 for segment in ReadySegment}
    attention = {segment: 0 for segment in AttentionSegment}
    manually_corrected = 0

    for subject in subjects:
        route = route_for(subject)
        route_counts[route] += 1
        if route is QueueRoute.READY:
            ready[ReadySegment.ALL] += 1
            if subject.status == "processed":
                ready[ReadySegment.READY_TO_APPROVE] += 1
            elif subject.status == "approved":
                ready[ReadySegment.READY_TO_EXPORT] += 1
            if bool(getattr(subject, "was_manually_corrected", False)):
                manually_corrected += 1
        elif route is QueueRoute.ATTENTION:
            attention[AttentionSegment.ALL] += 1
            if subject.status == "needs_review":
                attention[AttentionSegment.NEEDS_REVIEW] += 1
            elif subject.status == "failed":
                attention[AttentionSegment.FAILED] += 1
            elif subject.status == "skipped":
                attention[AttentionSegment.SKIPPED] += 1
            if bool(getattr(subject, "is_duplicate_suspected", False)):
                attention[AttentionSegment.SUSPECTED_DUPLICATE] += 1

    return QueueCounts(
        inbox=route_counts[QueueRoute.INBOX],
        attention=route_counts[QueueRoute.ATTENTION],
        ready=route_counts[QueueRoute.READY],
        irrelevant=route_counts[QueueRoute.IRRELEVANT],
        history=route_counts[QueueRoute.HISTORY],
        ready_breakdown=ReadyCounts(
            all=ready[ReadySegment.ALL],
            ready_to_approve=ready[ReadySegment.READY_TO_APPROVE],
            ready_to_export=ready[ReadySegment.READY_TO_EXPORT],
            manually_corrected=manually_corrected,
        ),
        attention_breakdown=AttentionCounts(
            all=attention[AttentionSegment.ALL],
            needs_review=attention[AttentionSegment.NEEDS_REVIEW],
            failed=attention[AttentionSegment.FAILED],
            skipped=attention[AttentionSegment.SKIPPED],
            suspected_duplicate=attention[AttentionSegment.SUSPECTED_DUPLICATE],
        ),
    )
