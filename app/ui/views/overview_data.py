"""Pure read-only projections for the Panda 2.0 operational Overview."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from app.domain.status_presentation import presentation_for
from app.models.document import Document
from app.ui.models.queue_policy import QueueCounts, calculate_queue_counts


@dataclass(frozen=True, slots=True)
class OverviewMetric:
    key: str
    label_he: str
    value: int
    description_he: str


@dataclass(frozen=True, slots=True)
class RecentDocumentChange:
    document_id: str
    file_name: str
    status: str
    status_label: str
    semantic: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OverviewSnapshot:
    counts: QueueCounts
    metrics: tuple[OverviewMetric, ...]
    recent_changes: tuple[RecentDocumentChange, ...]


def parse_document_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def build_overview_snapshot(
    documents: Iterable[Document],
    *,
    now: datetime | None = None,
    recent_limit: int = 5,
) -> OverviewSnapshot:
    """Build an honest current-state projection, not an audit event history."""
    docs = tuple(documents)
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_timezone = current.tzinfo

    timestamped: list[tuple[datetime, Document]] = []
    updated_today = 0
    updated_this_month = 0
    for document in docs:
        timestamp = parse_document_timestamp(document.updated_at)
        if timestamp is None:
            continue
        local_timestamp = timestamp.astimezone(local_timezone)
        timestamped.append((local_timestamp, document))
        if local_timestamp.date() == current.date():
            updated_today += 1
        if (local_timestamp.year, local_timestamp.month) == (current.year, current.month):
            updated_this_month += 1

    timestamped.sort(
        key=lambda item: (item[0], item[1].drive_file_id), reverse=True
    )
    recent: list[RecentDocumentChange] = []
    for timestamp, document in timestamped[: max(0, recent_limit)]:
        presentation = presentation_for(document.status)
        semantic = (
            "duplicate"
            if document.is_duplicate_suspected
            else presentation.semantic_category.value
        )
        recent.append(
            RecentDocumentChange(
                document_id=document.drive_file_id,
                file_name=document.file_name or "",
                status=document.status,
                status_label=presentation.label_he,
                semantic=semantic,
                updated_at=timestamp,
            )
        )

    metrics = (
        OverviewMetric(
            "updated_today",
            "עודכנו היום",
            updated_today,
            "מסמכים שהשדה updated_at האחרון שלהם חל היום",
        ),
        OverviewMetric(
            "updated_this_month",
            "עודכנו החודש",
            updated_this_month,
            "מסמכים שהשדה updated_at האחרון שלהם חל בחודש הנוכחי",
        ),
        OverviewMetric(
            "manually_corrected",
            "תוקנו ידנית",
            sum(bool(document.was_manually_corrected) for document in docs),
            "מסמכים עם דגל תיקון ידני שמור",
        ),
    )
    return OverviewSnapshot(
        counts=calculate_queue_counts(docs),
        metrics=metrics,
        recent_changes=tuple(recent),
    )


def format_recent_time(value: datetime, *, now: datetime | None = None) -> str:
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    localized = value.astimezone(current.tzinfo)
    if localized.date() == current.date():
        return localized.strftime("%H:%M")
    return localized.strftime("%d/%m/%Y")
