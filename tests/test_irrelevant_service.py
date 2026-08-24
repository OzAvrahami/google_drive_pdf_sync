from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.application.irrelevant_service import (
    IrrelevantReason,
    IrrelevantService,
)
from app.models.document import Document
from app.services.exclusion_service import (
    LocalPdfDeletionError,
    LocalPdfDeletionResult,
    UnsafeLocalPdfDeletionError,
    delete_local_pdf_safely,
    validate_local_pdf_deletion_target,
)


class MemoryRepository:
    def __init__(self, *documents: Document, fail_upsert: bool = False) -> None:
        self.documents = {d.drive_file_id: deepcopy(d) for d in documents}
        self.fail_upsert = fail_upsert
        self.upsert_calls = 0

    def get_by_drive_id(self, drive_file_id: str) -> Document | None:
        doc = self.documents.get(drive_file_id)
        return deepcopy(doc) if doc else None

    def upsert(self, document: Document) -> None:
        self.upsert_calls += 1
        if self.fail_upsert:
            raise OSError("store unavailable")
        document.touch()
        self.documents[document.drive_file_id] = deepcopy(document)

    def upsert_many(self, documents: list[Document]) -> None:
        for document in documents:
            self.upsert(document)


def make_document(root: Path, *, status: str = "processed", with_pdf: bool = True) -> Document:
    local_path = ""
    if with_pdf:
        pdf = root / "nested" / "invoice.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4 safe")
        local_path = str(pdf)
    return Document(
        drive_file_id="drive-current",
        file_name="invoice.pdf",
        folder_path="invoices",
        local_path=local_path,
        raw_text_path=str(root.parent / "text" / "invoice.txt"),
        status=status,
        supplier_name="Test Supplier",
    )


class TestSafeLocalPdfDeletion:
    def test_valid_nested_pdf_is_deleted(self, tmp_path: Path) -> None:
        root = tmp_path / "downloads"
        document = make_document(root)

        result = delete_local_pdf_safely(document.local_path, root)

        assert result.deleted is True
        assert not Path(document.local_path).exists()

    @pytest.mark.parametrize("local_path", [None, "", "   "])
    def test_null_path_is_safe_noop(self, tmp_path: Path, local_path: str | None) -> None:
        result = delete_local_pdf_safely(local_path, tmp_path / "downloads")
        assert result == LocalPdfDeletionResult(False, False, False)

    def test_already_missing_contained_pdf_is_safe_noop(self, tmp_path: Path) -> None:
        root = tmp_path / "downloads"
        result = delete_local_pdf_safely(root / "gone.pdf", root)
        assert result == LocalPdfDeletionResult(True, False, False)

    def test_parent_escape_is_rejected_and_outside_file_survives(self, tmp_path: Path) -> None:
        root = tmp_path / "downloads"
        root.mkdir()
        outside = tmp_path / "outside.pdf"
        outside.write_bytes(b"keep")
        with pytest.raises(UnsafeLocalPdfDeletionError):
            delete_local_pdf_safely(root / ".." / "outside.pdf", root)
        assert outside.read_bytes() == b"keep"

    def test_absolute_external_path_is_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "downloads"
        root.mkdir()
        external = tmp_path / "external" / "invoice.pdf"
        external.parent.mkdir()
        external.write_bytes(b"keep")
        with pytest.raises(UnsafeLocalPdfDeletionError):
            validate_local_pdf_deletion_target(external.resolve(), root)
        assert external.exists()

    def test_alternate_separator_escape_is_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "downloads"
        root.mkdir()
        outside = tmp_path / "outside.pdf"
        outside.write_bytes(b"keep")
        attack = str(root / "child" / ".." / ".." / "outside.pdf").replace(
            os.sep, "\\" if os.sep == "/" else "/"
        )
        with pytest.raises(UnsafeLocalPdfDeletionError):
            validate_local_pdf_deletion_target(attack, root)
        assert outside.exists()

    def test_non_pdf_target_is_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "downloads"
        target = root / "invoice.txt"
        target.parent.mkdir()
        target.write_text("keep", encoding="utf-8")
        with pytest.raises(UnsafeLocalPdfDeletionError):
            delete_local_pdf_safely(target, root)
        assert target.exists()

    def test_file_symlink_is_rejected_where_supported(self, tmp_path: Path) -> None:
        root = tmp_path / "downloads"
        root.mkdir()
        outside = tmp_path / "outside.pdf"
        outside.write_bytes(b"keep")
        link = root / "link.pdf"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlink creation is unavailable on this platform")
        with pytest.raises(UnsafeLocalPdfDeletionError):
            delete_local_pdf_safely(link, root)
        assert outside.exists()


class TestIrrelevantService:
    def test_success_updates_registry_document_and_deletes_only_pdf(self, tmp_path: Path) -> None:
        root = tmp_path / "downloads"
        document = make_document(root)
        raw_text = tmp_path / "text" / "invoice.txt"
        raw_text.parent.mkdir()
        raw_text.write_text("retained", encoding="utf-8")
        document.raw_text_path = str(raw_text)
        repository = MemoryRepository(document)
        registry = tmp_path / "excluded.json"
        with patch("app.services.exclusion_service.EXCLUDED_FILES_JSON", registry):
            result = IrrelevantService(repository, downloads_root=root).mark_irrelevant(
                document.drive_file_id,
                expected_status="processed",
                expected_updated_at=document.updated_at,
            )

        assert result.succeeded is True
        assert result.pdf_deleted is True
        persisted = repository.get_by_drive_id(document.drive_file_id)
        assert persisted.status == "confirmed_irrelevant"
        assert persisted.confirmed_irrelevant_at
        assert persisted.local_path == ""
        assert raw_text.read_text(encoding="utf-8") == "retained"
        assert document.drive_file_id in json.loads(registry.read_text("utf-8"))["excluded"]

    @pytest.mark.parametrize("local_path", ["", None])
    def test_missing_or_null_pdf_still_allows_irrelevant(self, tmp_path: Path, local_path) -> None:
        root = tmp_path / "downloads"
        document = make_document(root, with_pdf=False)
        document.local_path = local_path
        repository = MemoryRepository(document)
        with patch(
            "app.services.exclusion_service.EXCLUDED_FILES_JSON", tmp_path / "excluded.json"
        ):
            result = IrrelevantService(repository, downloads_root=root).mark_irrelevant(
                document.drive_file_id
            )
        assert result.succeeded is True
        assert result.pdf_deleted is False

    @pytest.mark.parametrize(
        "status", ["new", "processed", "needs_review", "failed", "skipped"]
    )
    def test_each_policy_eligible_status_can_be_marked_irrelevant(
        self, tmp_path: Path, status: str
    ) -> None:
        document = make_document(
            tmp_path / "downloads", status=status, with_pdf=False
        )
        repository = MemoryRepository(document)
        result = IrrelevantService(
            repository, registry_add=Mock(return_value=False)
        ).mark_irrelevant(document.drive_file_id)
        assert result.succeeded is True
        assert repository.get_by_drive_id(document.drive_file_id).status == (
            "confirmed_irrelevant"
        )

    def test_already_missing_contained_pdf_still_allows_irrelevant(self, tmp_path: Path) -> None:
        root = tmp_path / "downloads"
        document = make_document(root, with_pdf=False)
        document.local_path = str(root / "already-gone.pdf")
        repository = MemoryRepository(document)
        with patch(
            "app.services.exclusion_service.EXCLUDED_FILES_JSON", tmp_path / "excluded.json"
        ):
            result = IrrelevantService(repository, downloads_root=root).mark_irrelevant(
                document.drive_file_id
            )
        assert result.succeeded is True

    @pytest.mark.parametrize("status", ["approved", "exported", "confirmed_irrelevant", "excluded"])
    def test_terminal_or_read_only_status_is_blocked(self, tmp_path: Path, status: str) -> None:
        document = make_document(tmp_path / "downloads", status=status, with_pdf=False)
        repository = MemoryRepository(document)
        registry_add = Mock()
        result = IrrelevantService(repository, registry_add=registry_add).mark_irrelevant(
            document.drive_file_id
        )
        assert result.reason_code == "status_not_eligible"
        registry_add.assert_not_called()
        assert repository.upsert_calls == 0

    def test_stale_status_blocks_before_side_effects(self, tmp_path: Path) -> None:
        document = make_document(tmp_path / "downloads", status="needs_review", with_pdf=False)
        registry_add = Mock()
        result = IrrelevantService(
            MemoryRepository(document), registry_add=registry_add
        ).mark_irrelevant(document.drive_file_id, expected_status="processed")
        assert result.reason_code == "stale_document"
        registry_add.assert_not_called()

    def test_stale_updated_timestamp_blocks_before_side_effects(self, tmp_path: Path) -> None:
        document = make_document(tmp_path / "downloads", with_pdf=False)
        registry_add = Mock()
        result = IrrelevantService(
            MemoryRepository(document), registry_add=registry_add
        ).mark_irrelevant(document.drive_file_id, expected_updated_at="older")
        assert result.reason_code == "stale_document"
        registry_add.assert_not_called()

    def test_unsafe_path_blocks_before_registry(self, tmp_path: Path) -> None:
        root = tmp_path / "downloads"
        root.mkdir()
        external = tmp_path / "outside.pdf"
        external.write_bytes(b"keep")
        document = make_document(root, with_pdf=False)
        document.local_path = str(external)
        registry_add = Mock()
        result = IrrelevantService(
            MemoryRepository(document), downloads_root=root, registry_add=registry_add
        ).mark_irrelevant(document.drive_file_id)
        assert result.reason_code == "unsafe_local_path"
        registry_add.assert_not_called()
        assert external.exists()

    def test_registry_failure_prevents_delete_and_store(self, tmp_path: Path) -> None:
        root = tmp_path / "downloads"
        document = make_document(root)
        repository = MemoryRepository(document)
        result = IrrelevantService(
            repository,
            downloads_root=root,
            registry_add=Mock(side_effect=OSError("registry")),
        ).mark_irrelevant(document.drive_file_id)
        assert result.reason_code == "exclusion_registry_failed"
        assert Path(document.local_path).exists()
        assert repository.upsert_calls == 0

    def test_delete_failure_rolls_back_new_registry(self, tmp_path: Path) -> None:
        document = make_document(tmp_path / "downloads", with_pdf=False)
        repository = MemoryRepository(document)
        remove = Mock(return_value=True)
        result = IrrelevantService(
            repository,
            registry_add=Mock(return_value=True),
            registry_remove=remove,
            pdf_delete=Mock(side_effect=LocalPdfDeletionError("delete")),
        ).mark_irrelevant(document.drive_file_id)
        assert result.reason_code == "local_pdf_deletion_failed"
        assert result.partial_failure is False
        remove.assert_called_once_with(document.drive_file_id)
        assert repository.upsert_calls == 0

    def test_delete_failure_reports_failed_rollback(self, tmp_path: Path) -> None:
        document = make_document(tmp_path / "downloads", with_pdf=False)
        result = IrrelevantService(
            MemoryRepository(document),
            registry_add=Mock(return_value=True),
            registry_remove=Mock(side_effect=OSError("rollback")),
            pdf_delete=Mock(side_effect=LocalPdfDeletionError("delete")),
        ).mark_irrelevant(document.drive_file_id)
        assert result.partial_failure is True
        assert result.rollback_failed is True
        assert result.registry_recorded is True

    def test_store_failure_after_pdf_delete_is_explicit_partial_failure(self, tmp_path: Path) -> None:
        root = tmp_path / "downloads"
        document = make_document(root)
        repository = MemoryRepository(document, fail_upsert=True)
        result = IrrelevantService(
            repository,
            downloads_root=root,
            registry_add=Mock(return_value=True),
            registry_remove=Mock(),
        ).mark_irrelevant(document.drive_file_id)
        assert result.reason_code == "document_persistence_failed"
        assert result.partial_failure is True
        assert result.pdf_deleted is True
        assert repository.get_by_drive_id(document.drive_file_id).status == "processed"

    def test_store_failure_without_deleted_file_rolls_back_registry(self, tmp_path: Path) -> None:
        document = make_document(tmp_path / "downloads", with_pdf=False)
        remove = Mock(return_value=True)
        result = IrrelevantService(
            MemoryRepository(document, fail_upsert=True),
            registry_add=Mock(return_value=True),
            registry_remove=remove,
        ).mark_irrelevant(document.drive_file_id)
        assert result.partial_failure is False
        assert result.registry_recorded is False
        remove.assert_called_once()

    def test_confirmed_duplicate_clears_secondary_duplicate_state(self, tmp_path: Path) -> None:
        document = make_document(tmp_path / "downloads", with_pdf=False)
        document.is_duplicate_suspected = True
        document.suspected_duplicate_of = ["original"]
        document.duplicate_confidence = "exact"
        repository = MemoryRepository(document)
        result = IrrelevantService(
            repository, registry_add=Mock(return_value=False)
        ).mark_irrelevant(
            document.drive_file_id, reason=IrrelevantReason.CONFIRMED_DUPLICATE
        )
        assert result.succeeded
        persisted = repository.get_by_drive_id(document.drive_file_id)
        assert persisted.is_duplicate_suspected is False
        assert persisted.suspected_duplicate_of is None
        assert persisted.duplicate_confidence is None
