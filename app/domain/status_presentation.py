"""Panda 2.0 presentation metadata for persisted workflow statuses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NavigationDestination(str, Enum):
    INBOX = "inbox"
    ATTENTION = "attention"
    READY = "ready"
    HISTORY = "history"
    IRRELEVANT = "irrelevant"


class SemanticCategory(str, Enum):
    NEW = "new"
    READY = "ready"
    WARNING = "warning"
    ERROR = "error"
    NEUTRAL = "neutral"
    EXPORTED = "exported"
    IRRELEVANT = "irrelevant"


@dataclass(frozen=True)
class StatusPresentation:
    status: str
    label_he: str
    navigation: NavigationDestination
    navigation_label_he: str
    semantic_category: SemanticCategory


STATUS_PRESENTATION: dict[str, StatusPresentation] = {
    "new": StatusPresentation(
        "new", "חדש", NavigationDestination.INBOX, "נכנסו", SemanticCategory.NEW
    ),
    "processed": StatusPresentation(
        "processed",
        "מוכן לאישור",
        NavigationDestination.READY,
        "מוכן",
        SemanticCategory.READY,
    ),
    "needs_review": StatusPresentation(
        "needs_review",
        "לבדיקה",
        NavigationDestination.ATTENTION,
        "דורש טיפול",
        SemanticCategory.WARNING,
    ),
    "failed": StatusPresentation(
        "failed",
        "נכשל",
        NavigationDestination.ATTENTION,
        "דורש טיפול",
        SemanticCategory.ERROR,
    ),
    "skipped": StatusPresentation(
        "skipped",
        "דולג",
        NavigationDestination.ATTENTION,
        "דורש טיפול",
        SemanticCategory.NEUTRAL,
    ),
    "approved": StatusPresentation(
        "approved",
        "מוכן לייצוא",
        NavigationDestination.READY,
        "מוכן",
        SemanticCategory.READY,
    ),
    "exported": StatusPresentation(
        "exported",
        "יוצא",
        NavigationDestination.HISTORY,
        "היסטוריה",
        SemanticCategory.EXPORTED,
    ),
    "confirmed_irrelevant": StatusPresentation(
        "confirmed_irrelevant",
        "לא רלוונטי",
        NavigationDestination.IRRELEVANT,
        "לא רלוונטי",
        SemanticCategory.IRRELEVANT,
    ),
    "excluded": StatusPresentation(
        "excluded",
        "לא רלוונטי",
        NavigationDestination.IRRELEVANT,
        "לא רלוונטי",
        SemanticCategory.IRRELEVANT,
    ),
}


def presentation_for(status: str) -> StatusPresentation:
    try:
        return STATUS_PRESENTATION[status]
    except KeyError as exc:
        raise ValueError(f"Unknown persisted workflow status: {status!r}") from exc
