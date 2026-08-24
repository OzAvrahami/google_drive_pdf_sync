from __future__ import annotations

from pathlib import Path

import pytest

from app.utils import pdf_downloader
from app.utils.pdf_downloader import (
    UnsafeDownloadPathError,
    remove_cached_download,
    resolve_local_path,
)


@pytest.mark.parametrize(
    ("folder", "name", "parts"),
    (
        ("חשבוניות/אוגוסט", "חשבונית.pdf", ("חשבוניות", "אוגוסט", "חשבונית.pdf")),
        ("Suppliers/Cloud", "invoice.pdf", ("Suppliers", "Cloud", "invoice.pdf")),
        ("A/B/C", "one.pdf", ("A", "B", "C", "one.pdf")),
        ("A\\B/C", "mixed.pdf", ("A", "B", "C", "mixed.pdf")),
    ),
)
def test_safe_nested_paths_resolve_below_root(tmp_path, folder, name, parts) -> None:
    root = tmp_path / "downloads"
    resolved = Path(resolve_local_path(str(root), {"folder_path": folder, "name": name}))
    assert resolved == root.resolve().joinpath(*parts)
    assert resolved.is_relative_to(root.resolve())


def test_windows_invalid_filename_characters_are_sanitized_and_contained(tmp_path) -> None:
    root = tmp_path / "downloads"
    resolved = Path(
        resolve_local_path(str(root), {"folder_path": "2026", "name": 'invoice:*?"<>|.pdf'})
    )
    assert resolved.name == "invoice_______.pdf"
    assert resolved.is_relative_to(root.resolve())


@pytest.mark.parametrize(
    ("folder", "name"),
    (
        ("..", "escape.pdf"),
        (".", "escape.pdf"),
        ("safe/../outside", "escape.pdf"),
        ("safe\\..\\outside", "escape.pdf"),
        ("/absolute/path", "escape.pdf"),
        ("\\\\server\\share", "escape.pdf"),
        ("C:\\outside", "escape.pdf"),
        ("safe", "../escape.pdf"),
        ("safe", "C:\\escape.pdf"),
        ("safe", "."),
        ("safe", ".."),
    ),
)
def test_unsafe_drive_paths_are_rejected(tmp_path, folder, name) -> None:
    with pytest.raises(UnsafeDownloadPathError):
        resolve_local_path(str(tmp_path / "downloads"), {"folder_path": folder, "name": name})


def test_windows_reserved_filename_is_neutralized(tmp_path) -> None:
    resolved = Path(
        resolve_local_path(str(tmp_path), {"folder_path": "", "name": "CON.pdf"})
    )
    assert resolved.name == "_CON.pdf"


def test_two_sanitized_names_are_deterministic_and_remain_contained(tmp_path) -> None:
    root = tmp_path / "downloads"
    first = Path(resolve_local_path(str(root), {"folder_path": "A", "name": "one?.pdf"}))
    second = Path(resolve_local_path(str(root), {"folder_path": "A", "name": "one*.pdf"}))
    assert first == second
    assert first.is_relative_to(root.resolve())


def test_cache_invalidation_deletes_only_contained_regular_file(tmp_path) -> None:
    root = tmp_path / "downloads"
    cached = root / "safe" / "one.pdf"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"stale")
    assert remove_cached_download(root, cached) is True
    assert not cached.exists()
    assert remove_cached_download(root, cached) is False


def test_cache_invalidation_rejects_root_escape(tmp_path) -> None:
    root = tmp_path / "downloads"
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"must remain")
    with pytest.raises(UnsafeDownloadPathError):
        remove_cached_download(root, outside)
    assert outside.read_bytes() == b"must remain"


def test_failed_download_removes_partial_file_and_never_publishes_target(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "fresh.pdf"

    class RequestFiles:
        def get_media(self, *, fileId):
            return object()

    class Service:
        def files(self):
            return RequestFiles()

    class FailingDownload:
        def __init__(self, handle, request, chunksize):
            self.handle = handle

        def next_chunk(self):
            self.handle.write(b"partial remote bytes")
            raise OSError("network failed")

    monkeypatch.setattr(pdf_downloader, "MediaIoBaseDownload", FailingDownload)
    with pytest.raises(OSError, match="network failed"):
        pdf_downloader._download_file(Service(), "drive-1", str(target))
    assert not target.exists()
    assert list(tmp_path.glob("*.part")) == []

