"""Pure tests for the read-only Panda 2.0 Overview projection."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.document import Document
from app.ui.views.overview_data import (
    build_overview_snapshot,
    format_recent_time,
    parse_document_timestamp,
)


def _document(document_id: str, status: str = "processed", **overrides) -> Document:
    values = {
        "drive_file_id": document_id,
        "id": f"record-{document_id}",
        "file_name": f"{document_id}.pdf",
        "folder_path": "2026",
        "status": status,
        "updated_at": "2026-08-24T06:00:00+00:00",
    }
    values.update(overrides)
    return Document(**values)


def test_overview_counts_use_shared_queue_policy_and_duplicate_override() -> None:
    snapshot = build_overview_snapshot(
        [
            _document("new", "new"),
            _document("review", "needs_review"),
            _document("failed", "failed"),
            _document("skipped", "skipped"),
            _document("duplicate", "processed", is_duplicate_suspected=True),
            _document("processed", "processed"),
            _document("approved", "approved"),
            _document("irrelevant", "confirmed_irrelevant"),
            _document("excluded", "excluded"),
            _document("history", "exported"),
        ],
        now=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
    )

    assert snapshot.counts.inbox == 1
    assert snapshot.counts.attention == 4
    assert snapshot.counts.ready == 2
    assert snapshot.counts.irrelevant == 2
    assert snapshot.counts.history == 1
    assert snapshot.counts.ready_breakdown.ready_to_approve == 1
    assert snapshot.counts.ready_breakdown.ready_to_export == 1


def test_attention_breakdown_preserves_overlap() -> None:
    snapshot = build_overview_snapshot(
        [
            _document("overlap", "needs_review", is_duplicate_suspected=True),
            _document("failed", "failed"),
            _document("skipped", "skipped"),
        ]
    )

    breakdown = snapshot.counts.attention_breakdown
    assert breakdown.all == 3
    assert breakdown.needs_review == 1
    assert breakdown.failed == 1
    assert breakdown.skipped == 1
    assert breakdown.suspected_duplicate == 1


def test_zero_document_snapshot_is_explicit() -> None:
    snapshot = build_overview_snapshot(
        [], now=datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    )

    assert snapshot.counts.inbox == 0
    assert snapshot.counts.attention == 0
    assert snapshot.counts.ready == 0
    assert [metric.value for metric in snapshot.metrics] == [0, 0, 0]
    assert snapshot.recent_changes == ()


def test_metrics_use_last_update_date_and_manual_flag_only() -> None:
    snapshot = build_overview_snapshot(
        [
            _document("today", updated_at="2026-08-24T08:00:00+00:00"),
            _document(
                "month",
                updated_at="2026-08-02T08:00:00+00:00",
                was_manually_corrected=True,
            ),
            _document("previous", updated_at="2026-07-31T22:00:00+00:00"),
            _document(
                "invalid",
                updated_at="not-a-timestamp",
                was_manually_corrected=True,
            ),
        ],
        now=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
    )

    metrics = {metric.key: metric for metric in snapshot.metrics}
    assert metrics["updated_today"].value == 1
    assert metrics["updated_this_month"].value == 2
    assert metrics["manually_corrected"].value == 2
    assert "updated_at" in metrics["updated_today"].description_he


def test_metrics_respect_the_supplied_local_timezone() -> None:
    israel = timezone.utc
    snapshot = build_overview_snapshot(
        [_document("boundary", updated_at="2026-08-23T23:30:00+00:00")],
        now=datetime(2026, 8, 24, 1, tzinfo=israel),
    )

    assert snapshot.metrics[0].value == 0


def test_recent_changes_are_bounded_and_sorted_by_updated_at() -> None:
    snapshot = build_overview_snapshot(
        [
            _document("old", updated_at="2026-08-20T08:00:00+00:00"),
            _document("newest", "approved", updated_at="2026-08-24T10:00:00+00:00"),
            _document("middle", "failed", updated_at="2026-08-23T10:00:00+00:00"),
        ],
        recent_limit=2,
    )

    assert [item.document_id for item in snapshot.recent_changes] == ["newest", "middle"]
    assert snapshot.recent_changes[0].status_label
    assert snapshot.recent_changes[1].semantic == "error"


def test_duplicate_recent_change_uses_auxiliary_semantic_without_status_change() -> None:
    snapshot = build_overview_snapshot(
        [_document("duplicate", "processed", is_duplicate_suspected=True)]
    )

    change = snapshot.recent_changes[0]
    assert change.status == "processed"
    assert change.semantic == "duplicate"


def test_invalid_timestamps_are_not_presented_as_recent_activity() -> None:
    snapshot = build_overview_snapshot([_document("invalid", updated_at="invalid")])

    assert snapshot.recent_changes == ()


def test_timestamp_parser_handles_current_iso_shape_and_rejects_bad_input() -> None:
    assert parse_document_timestamp("2026-08-24T06:00:00+00:00") is not None
    assert parse_document_timestamp("2026-08-24T06:00:00Z") is not None
    assert parse_document_timestamp("bad") is None
    assert parse_document_timestamp(None) is None


def test_recent_time_format_is_honest_and_compact() -> None:
    now = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)

    assert format_recent_time(datetime(2026, 8, 24, 8, tzinfo=timezone.utc), now=now) == "08:00"
    assert format_recent_time(datetime(2026, 8, 23, 8, tzinfo=timezone.utc), now=now) == "23/08/2026"
