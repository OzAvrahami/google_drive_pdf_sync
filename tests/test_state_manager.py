"""
Unit tests for app.state.state_manager.

Run from the project root:
    pytest tests/test_state_manager.py -v
"""

import json
import os
import pytest
from app.state.state_manager import StateManager


@pytest.fixture
def state_path(tmp_path):
    return str(tmp_path / "sync_state.json")


@pytest.fixture
def sm(state_path):
    return StateManager(state_path)


_DRIVE_RECORD = {
    "id":           "file_abc123",
    "name":         "invoice.pdf",
    "folder_path":  "ינואר 2026/חשבוניות מס",
    "modifiedTime": "2026-01-31T10:00:00.000Z",
}


class TestFilterNew:

    def test_new_file_is_included(self, sm):
        assert sm.filter_new([_DRIVE_RECORD]) == [_DRIVE_RECORD]

    def test_already_processed_file_is_excluded(self, sm):
        sm.mark_processed(_DRIVE_RECORD)
        assert sm.filter_new([_DRIVE_RECORD]) == []

    def test_changed_file_is_included(self, sm):
        sm.mark_processed(_DRIVE_RECORD)
        changed = {**_DRIVE_RECORD, "modifiedTime": "2026-02-15T08:00:00.000Z"}
        assert sm.filter_new([changed]) == [changed]

    def test_mixed_returns_only_new(self, sm):
        other = {**_DRIVE_RECORD, "id": "file_xyz", "name": "other.pdf"}
        sm.mark_processed(_DRIVE_RECORD)
        result = sm.filter_new([_DRIVE_RECORD, other])
        assert result == [other]

    def test_record_without_id_is_skipped(self, sm):
        bad = {"name": "no_id.pdf", "folder_path": "", "modifiedTime": ""}
        assert sm.filter_new([bad]) == []


class TestMarkProcessed:

    def test_marks_as_processed(self, sm):
        sm.mark_processed(_DRIVE_RECORD)
        assert sm.is_processed("file_abc123")

    def test_marks_with_custom_status(self, sm):
        sm.mark_processed(_DRIVE_RECORD, status="failed", error="timeout")
        entry = sm._data["files"]["file_abc123"]
        assert entry["status"] == "failed"
        assert entry["error"]  == "timeout"

    def test_stores_modified_time(self, sm):
        sm.mark_processed(_DRIVE_RECORD)
        entry = sm._data["files"]["file_abc123"]
        assert entry["modified_time"] == _DRIVE_RECORD["modifiedTime"]


class TestPersistence:

    def test_save_and_reload(self, state_path):
        sm1 = StateManager(state_path)
        sm1.mark_processed(_DRIVE_RECORD)
        sm1.save()

        sm2 = StateManager(state_path)
        assert sm2.is_processed("file_abc123")
        assert sm2.filter_new([_DRIVE_RECORD]) == []

    def test_corrupt_file_starts_fresh(self, state_path):
        with open(state_path, "w") as f:
            f.write("not valid json{{{{")
        sm = StateManager(state_path)
        assert sm.filter_new([_DRIVE_RECORD]) == [_DRIVE_RECORD]

    def test_missing_file_starts_fresh(self, state_path):
        assert not os.path.exists(state_path)
        sm = StateManager(state_path)
        assert sm.filter_new([_DRIVE_RECORD]) == [_DRIVE_RECORD]

    def test_save_creates_parent_dirs(self, tmp_path):
        deep_path = str(tmp_path / "a" / "b" / "state.json")
        sm = StateManager(deep_path)
        sm.mark_processed(_DRIVE_RECORD)
        sm.save()
        assert os.path.exists(deep_path)
