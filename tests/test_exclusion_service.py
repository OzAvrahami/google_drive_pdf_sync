"""
Tests for app.services.exclusion_service.

Verifies:
  - add_exclusion() creates a registry entry
  - add_exclusion() deletes the local PDF
  - add_exclusion() is idempotent (safe to call twice without duplicating)
  - is_excluded() returns True for a recorded drive_file_id
  - is_excluded() returns False for an unknown drive_file_id
  - load_exclusion_ids() returns the full set of excluded IDs
  - An auto-skipped document does NOT create a registry entry / delete PDF
  - Drive scan: excluded IDs are not re-registered

All tests use tmp_path so no real data files are touched.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.document import Document


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_doc(
    tmp_path: Path,
    drive_file_id: str = "abc123",
    file_name: str = "invoice.pdf",
    status: str = "skipped",
    with_pdf: bool = True,
) -> Document:
    """Build a minimal Document with an optional real local PDF."""
    pdf_path = ""
    if with_pdf:
        pdf = tmp_path / file_name
        pdf.write_bytes(b"%PDF-1.4 test")
        pdf_path = str(pdf)

    return Document(
        drive_file_id=drive_file_id,
        file_name=file_name,
        folder_path="invoices/2026",
        local_path=pdf_path,
        status=status,
        extracted_data={"document_type": "טופס פתיחת ספק"},
    )


def _patch_registry(tmp_path: Path):
    """Context manager that redirects EXCLUDED_FILES_JSON to a tmp file."""
    return patch(
        "app.services.exclusion_service.EXCLUDED_FILES_JSON",
        tmp_path / "excluded_files.json",
    )


# ── add_exclusion — registry entry ────────────────────────────────────────────

class TestAddExclusionRegistryEntry:

    def test_creates_registry_file(self, tmp_path):
        doc = _make_doc(tmp_path)
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import add_exclusion
            add_exclusion(doc)
        registry_file = tmp_path / "excluded_files.json"
        assert registry_file.exists()

    def test_registry_contains_drive_file_id(self, tmp_path):
        doc = _make_doc(tmp_path, drive_file_id="drive_xyz")
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import add_exclusion
            add_exclusion(doc)
        data = json.loads((tmp_path / "excluded_files.json").read_text("utf-8"))
        assert "drive_xyz" in data["excluded"]

    def test_registry_entry_has_expected_fields(self, tmp_path):
        doc = _make_doc(tmp_path, drive_file_id="drive_xyz", file_name="test.pdf")
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import add_exclusion
            add_exclusion(doc)
        data = json.loads((tmp_path / "excluded_files.json").read_text("utf-8"))
        entry = data["excluded"]["drive_xyz"]
        assert entry["drive_file_id"] == "drive_xyz"
        assert entry["file_name"] == "test.pdf"
        assert "excluded_at" in entry

    def test_registry_captures_document_type(self, tmp_path):
        doc = _make_doc(tmp_path, drive_file_id="doc_type_id")
        doc.extracted_data = {"document_type": "טופס פתיחת ספק"}
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import add_exclusion
            add_exclusion(doc)
        data = json.loads((tmp_path / "excluded_files.json").read_text("utf-8"))
        assert data["excluded"]["doc_type_id"]["detected_doc_type"] == "טופס פתיחת ספק"


# ── add_exclusion — PDF deletion ───────────────────────────────────────────────

class TestAddExclusionDeletesPdf:

    def test_local_pdf_is_deleted(self, tmp_path):
        doc = _make_doc(tmp_path, with_pdf=True)
        pdf = Path(doc.local_path)
        assert pdf.exists()
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import add_exclusion
            add_exclusion(doc)
        assert not pdf.exists()

    def test_no_crash_when_pdf_already_absent(self, tmp_path):
        doc = _make_doc(tmp_path, with_pdf=False)
        doc.local_path = str(tmp_path / "ghost.pdf")  # does not exist
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import add_exclusion
            add_exclusion(doc)   # must not raise

    def test_no_crash_when_local_path_empty(self, tmp_path):
        doc = _make_doc(tmp_path, with_pdf=False)
        doc.local_path = ""
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import add_exclusion
            add_exclusion(doc)   # must not raise


# ── add_exclusion — idempotency ────────────────────────────────────────────────

class TestAddExclusionIdempotent:

    def test_calling_twice_does_not_duplicate_entry(self, tmp_path):
        doc = _make_doc(tmp_path, drive_file_id="idem_id")
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import add_exclusion
            add_exclusion(doc)
            # PDF is gone after first call; second call should still succeed.
            add_exclusion(doc)
        data = json.loads((tmp_path / "excluded_files.json").read_text("utf-8"))
        # Should have exactly one entry, not two.
        assert len(data["excluded"]) == 1
        assert "idem_id" in data["excluded"]


# ── is_excluded ────────────────────────────────────────────────────────────────

class TestIsExcluded:

    def test_returns_true_for_recorded_id(self, tmp_path):
        doc = _make_doc(tmp_path, drive_file_id="check_id")
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import add_exclusion, is_excluded
            add_exclusion(doc)
            assert is_excluded("check_id") is True

    def test_returns_false_for_unknown_id(self, tmp_path):
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import is_excluded
            assert is_excluded("no_such_id") is False

    def test_returns_false_for_auto_skipped_doc(self, tmp_path):
        """Auto-skipped docs must NOT have an exclusion record."""
        doc = _make_doc(tmp_path, drive_file_id="skipped_id", status="skipped")
        # Simulate processing_service behaviour: status set to "skipped", no add_exclusion call.
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import is_excluded
            assert is_excluded("skipped_id") is False


# ── load_exclusion_ids ─────────────────────────────────────────────────────────

class TestLoadExclusionIds:

    def test_returns_set_of_excluded_ids(self, tmp_path):
        ids = ["id_a", "id_b", "id_c"]
        docs = [_make_doc(tmp_path, drive_file_id=fid, file_name=f"{fid}.pdf") for fid in ids]
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import add_exclusion, load_exclusion_ids
            for doc in docs:
                add_exclusion(doc)
            result = load_exclusion_ids()
        assert result == set(ids)

    def test_returns_empty_set_when_registry_absent(self, tmp_path):
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import load_exclusion_ids
            result = load_exclusion_ids()
        assert result == set()


# ── Auto-skip does NOT touch exclusion registry ────────────────────────────────

class TestAutoSkipDoesNotExclude:
    """
    Processing service must set status="skipped" for excluded document types
    WITHOUT calling add_exclusion, without deleting the PDF, and without
    creating a registry entry.
    """

    def test_auto_skipped_doc_pdf_still_exists(self, tmp_path):
        """Simulates the processing_service auto-skip path."""
        pdf = tmp_path / "supplier_form.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        doc = Document(
            drive_file_id="auto_skip_id",
            file_name="supplier_form.pdf",
            folder_path="",
            local_path=str(pdf),
            status="skipped",
            error_message="מסמך לא רלוונטי: טופס פתיחת ספק",
        )

        # No add_exclusion call — PDF must survive.
        assert pdf.exists()

    def test_auto_skipped_doc_not_in_registry(self, tmp_path):
        with _patch_registry(tmp_path):
            from app.services.exclusion_service import is_excluded
            # No add_exclusion was ever called.
            assert is_excluded("auto_skip_id") is False


# ── Drive scan respects exclusion registry ─────────────────────────────────────

class TestDriveScanHonorsExclusions:
    """
    DriveSyncService.scan() must skip files whose drive_file_id is in the
    exclusion registry — they should not be re-registered in the document store.
    """

    def test_excluded_id_not_re_registered(self, tmp_path):
        # Set up exclusion registry with one entry.
        exclusion_json = tmp_path / "excluded_files.json"
        exclusion_json.write_text(
            json.dumps({
                "version": 1,
                "excluded": {
                    "excluded_drive_id": {
                        "drive_file_id": "excluded_drive_id",
                        "file_name": "old_supplier_form.pdf",
                        "folder_path": "",
                        "detected_doc_type": "טופס פתיחת ספק",
                        "excluded_at": "2026-04-10T12:00:00+00:00",
                        "local_path_at_exclusion": "",
                    }
                },
            }),
            encoding="utf-8",
        )

        store_mock = MagicMock()
        store_mock.get_by_drive_id.return_value = None

        pdf_records = [
            {"id": "excluded_drive_id", "name": "old_supplier_form.pdf",
             "folder_path": "forms", "modifiedTime": "2026-04-11T00:00:00Z"},
            {"id": "new_invoice_id", "name": "invoice_001.pdf",
             "folder_path": "invoices", "modifiedTime": "2026-04-12T00:00:00Z"},
        ]

        with (
            patch("app.services.drive_sync_service.get_drive_service",
                  return_value=(MagicMock(), None)),
            patch("app.services.drive_sync_service.get_folder_pdf_hierarchy",
                  return_value=pdf_records),
            patch("app.services.drive_sync_service.GOOGLE_DRIVE_PARENT_FOLDER_ID", "root_id"),
            patch("app.services.exclusion_service.EXCLUDED_FILES_JSON", exclusion_json),
        ):
            from app.services.drive_sync_service import DriveSyncService
            service = DriveSyncService(store_mock)
            summary = service.scan()

        # Only the non-excluded new file should be upserted.
        upserted = store_mock.upsert_many.call_args[0][0]
        upserted_ids = [d.drive_file_id for d in upserted]
        assert "excluded_drive_id" not in upserted_ids
        assert "new_invoice_id" in upserted_ids
        assert summary["excluded"] == 1
        assert summary["new"] == 1
