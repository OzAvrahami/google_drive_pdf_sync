"""Pure tests for Panda 2.0 queue membership and shared counts."""

from __future__ import annotations

import pytest

from app.models.document import Document
from app.ui.models.queue_policy import (
    AttentionSegment,
    QueueRoute,
    ReadySegment,
    calculate_queue_counts,
    matches_attention_segment,
    matches_ready_segment,
    route_for,
)


def _document(document_id: str, status: str, **overrides) -> Document:
    values = {
        "drive_file_id": document_id,
        "file_name": f"{document_id}.pdf",
        "folder_path": "2026",
        "status": status,
    }
    values.update(overrides)
    return Document(**values)


@pytest.mark.parametrize(
    "status, expected",
    [
        ("new", QueueRoute.INBOX),
        ("needs_review", QueueRoute.ATTENTION),
        ("failed", QueueRoute.ATTENTION),
        ("skipped", QueueRoute.ATTENTION),
        ("processed", QueueRoute.READY),
        ("approved", QueueRoute.READY),
        ("confirmed_irrelevant", QueueRoute.IRRELEVANT),
        ("excluded", QueueRoute.IRRELEVANT),
        ("exported", QueueRoute.HISTORY),
    ],
)
def test_every_persisted_status_maps_through_status_presentation(
    status: str, expected: QueueRoute
) -> None:
    assert route_for(_document(status, status)) is expected


@pytest.mark.parametrize("status", ["new", "processed", "approved", "exported", "excluded"])
def test_suspected_duplicate_overrides_otherwise_normal_route(status: str) -> None:
    document = _document("duplicate", status, is_duplicate_suspected=True)

    assert route_for(document) is QueueRoute.ATTENTION


@pytest.mark.parametrize(
    "status, segment, expected",
    [
        ("processed", ReadySegment.ALL, True),
        ("approved", ReadySegment.ALL, True),
        ("processed", ReadySegment.READY_TO_APPROVE, True),
        ("approved", ReadySegment.READY_TO_APPROVE, False),
        ("approved", ReadySegment.READY_TO_EXPORT, True),
        ("processed", ReadySegment.READY_TO_EXPORT, False),
    ],
)
def test_ready_segments_are_derived_without_new_statuses(
    status: str, segment: ReadySegment, expected: bool
) -> None:
    assert matches_ready_segment(_document(status, status), segment) is expected


def test_duplicate_processed_document_is_not_in_ready_segment() -> None:
    document = _document("duplicate", "processed", is_duplicate_suspected=True)

    assert matches_ready_segment(document, ReadySegment.ALL) is False


@pytest.mark.parametrize(
    "status, duplicate, segment, expected",
    [
        ("needs_review", False, AttentionSegment.NEEDS_REVIEW, True),
        ("failed", False, AttentionSegment.FAILED, True),
        ("skipped", False, AttentionSegment.SKIPPED, True),
        ("processed", True, AttentionSegment.SUSPECTED_DUPLICATE, True),
        ("processed", False, AttentionSegment.ALL, False),
    ],
)
def test_attention_segments_match_status_or_duplicate_flag(
    status: str,
    duplicate: bool,
    segment: AttentionSegment,
    expected: bool,
) -> None:
    document = _document("subject", status, is_duplicate_suspected=duplicate)

    assert matches_attention_segment(document, segment) is expected


def test_needs_review_duplicate_is_visible_in_both_overlapping_segments() -> None:
    document = _document("overlap", "needs_review", is_duplicate_suspected=True)

    assert matches_attention_segment(document, AttentionSegment.NEEDS_REVIEW)
    assert matches_attention_segment(document, AttentionSegment.SUSPECTED_DUPLICATE)


def test_queue_counts_and_breakdowns_share_route_policy() -> None:
    documents = [
        _document("new", "new"),
        _document("review", "needs_review"),
        _document("failed", "failed"),
        _document("skipped", "skipped"),
        _document("duplicate", "processed", is_duplicate_suspected=True),
        _document("processed", "processed", was_manually_corrected=True),
        _document("approved", "approved"),
        _document("irrelevant", "confirmed_irrelevant"),
        _document("excluded", "excluded"),
        _document("history", "exported"),
    ]

    counts = calculate_queue_counts(documents)

    assert [counts.for_route(route) for route in QueueRoute] == [1, 4, 2, 2, 1]
    assert counts.ready_breakdown.all == 2
    assert counts.ready_breakdown.ready_to_approve == 1
    assert counts.ready_breakdown.ready_to_export == 1
    assert counts.ready_breakdown.manually_corrected == 1
    assert counts.attention_breakdown.all == 4
    assert counts.attention_breakdown.needs_review == 1
    assert counts.attention_breakdown.failed == 1
    assert counts.attention_breakdown.skipped == 1
    assert counts.attention_breakdown.suspected_duplicate == 1
