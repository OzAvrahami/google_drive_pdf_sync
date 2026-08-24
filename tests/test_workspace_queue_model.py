"""Stable-ID navigation tests for the future Panda 2.0 Workspace."""

from __future__ import annotations

from PySide6.QtTest import QSignalSpy

from app.ui.models.workspace_queue_model import WorkspaceQueueModel, WorkspaceQueueRoles


def test_initial_current_position_and_total() -> None:
    model = WorkspaceQueueModel(["one", "two", "three"])

    assert model.document_ids == ("one", "two", "three")
    assert model.current_document_id == "one"
    assert model.current_index == 0
    assert model.position == 1
    assert model.total == 3


def test_next_previous_and_boundaries_are_safe() -> None:
    model = WorkspaceQueueModel(["one", "two"])

    assert model.previous() == "one"
    assert model.next() == "two"
    assert model.next() == "two"
    assert model.previous() == "one"
    assert model.can_go_previous is False
    assert model.can_go_next is True


def test_set_current_by_id_and_roles() -> None:
    model = WorkspaceQueueModel(["one", "two"])
    changed = QSignalSpy(model.currentChanged)

    assert model.set_current_by_id("two") is True
    assert model.set_current_by_id("missing") is False
    assert model.current_document_id == "two"
    assert model.position == 2
    assert model.data(model.index(1, 0), WorkspaceQueueRoles.DOCUMENT_ID) == "two"
    assert model.data(model.index(1, 0), WorkspaceQueueRoles.IS_CURRENT) is True
    assert changed.count() == 1


def test_remove_current_selects_next_then_previous_at_end() -> None:
    model = WorkspaceQueueModel(["one", "two", "three"])
    model.set_current_by_id("two")

    assert model.remove_document_id("two") is True
    assert model.current_document_id == "three"
    assert model.position == 2
    assert model.remove_document_id("three") is True
    assert model.current_document_id == "one"
    assert model.remove_document_id("missing") is False


def test_remove_only_current_leaves_empty_queue() -> None:
    model = WorkspaceQueueModel(["one"])

    model.remove_document_id("one")

    assert model.current_document_id is None
    assert model.current_index == -1
    assert model.position == 0
    assert model.total == 0
    assert model.next() is None
    assert model.previous() is None


def test_refresh_preserves_current_id_and_updates_position() -> None:
    model = WorkspaceQueueModel(["one", "two", "three"])
    model.set_current_by_id("two")

    model.refresh(["three", "two", "four"])

    assert model.document_ids == ("three", "two", "four")
    assert model.current_document_id == "two"
    assert model.position == 2


def test_refresh_without_current_uses_first_available_id() -> None:
    model = WorkspaceQueueModel(["one", "two"])
    model.set_current_by_id("two")

    model.refresh(["three", "four"])

    assert model.current_document_id == "three"
    assert model.position == 1


def test_refresh_deduplicates_ids_while_preserving_order() -> None:
    model = WorkspaceQueueModel(["one", "one", "two", "one"])

    assert model.document_ids == ("one", "two")
    assert model.rowCount() == 2
