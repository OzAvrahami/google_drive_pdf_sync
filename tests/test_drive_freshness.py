from __future__ import annotations

from pathlib import Path

import pytest

from app.models.document import Document
from app.services import drive_sync_service, processing_service
from app.services.drive_sync_service import DriveSyncService
from app.services.processing_service import ProcessingService
from app.utils.pdf_downloader import resolve_local_path


class MemoryStore:
    def __init__(self, documents=()) -> None:
        self.documents = {document.drive_file_id: document for document in documents}
        self.upserted = []

    def get_by_drive_id(self, drive_id):
        return self.documents.get(drive_id)

    def get_by_status(self, *statuses):
        return [document for document in self.documents.values() if document.status in statuses]

    def upsert(self, document):
        self.documents[document.drive_file_id] = document
        self.upserted.append(document.drive_file_id)

    def upsert_many(self, documents):
        for document in documents:
            self.documents[document.drive_file_id] = document
            self.upserted.append(document.drive_file_id)


def remote_record(*, modified="2026-08-24T10:00:00+00:00", name="invoice.pdf"):
    return {
        "id": "drive-1",
        "name": name,
        "folder_path": "Suppliers/2026",
        "modifiedTime": modified,
    }


def configure_scan(monkeypatch, tmp_path, store, record) -> DriveSyncService:
    monkeypatch.setattr(drive_sync_service, "DOWNLOADS_DIR", tmp_path / "downloads")
    monkeypatch.setattr(drive_sync_service, "GOOGLE_DRIVE_PARENT_FOLDER_ID", "folder")
    monkeypatch.setattr(drive_sync_service, "get_drive_service", lambda: (object(), None))
    monkeypatch.setattr(
        drive_sync_service,
        "get_folder_pdf_hierarchy",
        lambda _service, _folder: [record],
    )
    monkeypatch.setattr(drive_sync_service, "load_exclusion_ids", lambda: set())
    return DriveSyncService(store)


def test_new_remote_document_is_registered_and_downloads_when_processed(
    tmp_path, monkeypatch
) -> None:
    store = MemoryStore()
    scan = configure_scan(monkeypatch, tmp_path, store, remote_record())
    assert scan.scan()["new"] == 1
    document = store.get_by_drive_id("drive-1")
    assert document.status == "new"

    monkeypatch.setattr(processing_service, "DOWNLOADS_DIR", tmp_path / "downloads")
    downloads = []

    def download(_service, _file_id, destination):
        downloads.append(destination)
        Path(destination).write_bytes(b"new remote")

    monkeypatch.setattr(processing_service, "_download_file", download)
    path = ProcessingService(store)._download(document, object())
    assert path.read_bytes() == b"new remote"
    assert downloads == [str(path)]


def test_unchanged_document_with_valid_cache_reuses_local_file(tmp_path, monkeypatch) -> None:
    document = Document(
        drive_file_id="drive-1",
        file_name="invoice.pdf",
        folder_path="Suppliers/2026",
        status="processed",
        updated_at="2026-08-24T12:00:00+00:00",
    )
    store = MemoryStore([document])
    scan = configure_scan(
        monkeypatch,
        tmp_path,
        store,
        remote_record(modified="2026-08-24T10:00:00+00:00"),
    )
    root = tmp_path / "downloads"
    cached = Path(resolve_local_path(str(root), remote_record()))
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"valid cached bytes")
    document.local_path = str(cached)

    assert scan.scan()["skipped"] == 1
    monkeypatch.setattr(processing_service, "DOWNLOADS_DIR", root)
    monkeypatch.setattr(
        processing_service,
        "_download_file",
        lambda *_args: pytest.fail("unchanged cached PDF should be reused"),
    )
    assert ProcessingService(store)._download(document, object()).read_bytes() == b"valid cached bytes"


def test_changed_remote_document_invalidates_stale_cached_bytes(tmp_path, monkeypatch) -> None:
    document = Document(
        drive_file_id="drive-1",
        file_name="invoice.pdf",
        folder_path="Suppliers/2026",
        status="processed",
        updated_at="2026-08-24T08:00:00+00:00",
    )
    store = MemoryStore([document])
    record = remote_record(modified="2026-08-24T10:00:00+00:00")
    scan = configure_scan(monkeypatch, tmp_path, store, record)
    root = tmp_path / "downloads"
    stale = Path(resolve_local_path(str(root), record))
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale bytes")
    document.local_path = str(stale)
    document.raw_text_path = str(tmp_path / "old.txt")

    assert scan.scan()["updated"] == 1
    assert not stale.exists()
    assert document.status == "new"
    assert document.local_path == "" and document.raw_text_path == ""


def test_changed_remote_bytes_reach_extraction_and_parser_boundary(tmp_path, monkeypatch) -> None:
    document = Document(
        drive_file_id="drive-1",
        file_name="invoice.pdf",
        folder_path="Suppliers/2026",
        status="processed",
        updated_at="2026-08-24T08:00:00+00:00",
    )
    store = MemoryStore([document])
    record = remote_record()
    scan = configure_scan(monkeypatch, tmp_path, store, record)
    root = tmp_path / "downloads"
    stale = Path(resolve_local_path(str(root), record))
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"STALE")
    document.local_path = str(stale)
    scan.scan()

    monkeypatch.setattr(processing_service, "DOWNLOADS_DIR", root)
    monkeypatch.setattr(processing_service, "TEXT_DIR", tmp_path / "text")
    monkeypatch.setattr(
        processing_service,
        "_download_file",
        lambda _svc, _id, path: Path(path).write_bytes(b"FRESH REMOTE CONTENT"),
    )
    monkeypatch.setattr(
        processing_service,
        "extract_text_from_pdf",
        lambda path: Path(path).read_bytes().decode("ascii"),
    )
    monkeypatch.setattr(processing_service, "classify_document_type", lambda _text: None)
    monkeypatch.setattr(processing_service, "load_correction_map", lambda: {"fields": {}})
    parsed_text = []

    def parse(text, correction_map):
        parsed_text.append(text)
        return {
            "business_name": "Supplier",
            "invoice_date": "24/08/2026",
            "invoice_number": "INV-1",
            "amount": 100,
            "supplier_validation": {"score": 100, "is_valid": True},
        }

    monkeypatch.setattr(processing_service, "parse_invoice_text", parse)
    monkeypatch.setattr(processing_service, "detect_and_mark_duplicate", lambda *_args: None)
    ProcessingService(store)._process_one(document, object())

    assert parsed_text == ["FRESH REMOTE CONTENT"]
    assert document.status == "processed"
    assert Path(document.local_path).read_bytes() == b"FRESH REMOTE CONTENT"


def test_failed_refreshed_download_never_falls_back_to_stale_file(tmp_path, monkeypatch) -> None:
    document = Document(
        drive_file_id="drive-1",
        file_name="invoice.pdf",
        folder_path="Suppliers/2026",
        status="processed",
        updated_at="2026-08-24T08:00:00+00:00",
    )
    store = MemoryStore([document])
    record = remote_record()
    scan = configure_scan(monkeypatch, tmp_path, store, record)
    root = tmp_path / "downloads"
    stale = Path(resolve_local_path(str(root), record))
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"STALE")
    document.local_path = str(stale)
    scan.scan()
    assert not stale.exists()

    monkeypatch.setattr(processing_service, "DOWNLOADS_DIR", root)
    monkeypatch.setattr(
        processing_service,
        "_download_file",
        lambda *_args: (_ for _ in ()).throw(OSError("refresh failed")),
    )
    summary = ProcessingService(store).process_new(drive_service=object())
    assert summary == {"total": 1, "success": 0, "needs_review": 0, "failed": 1}
    assert document.status == "failed"
    assert document.error_message == "refresh failed"
    assert not stale.exists()

