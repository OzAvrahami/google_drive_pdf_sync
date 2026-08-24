"""
PDF downloader: downloads discovered Drive PDFs to a local directory,
preserving the folder_path structure as subdirectories.

Public API
----------
download_pdfs(service, records, output_dir)       -> None
resolve_local_path(output_dir, pdf_record)        -> str
"""

import os
import re
import tempfile
from pathlib import Path, PureWindowsPath

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# Characters invalid in filenames on Windows and macOS/Linux.
_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')
_WINDOWS_RESERVED = re.compile(
    r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$", re.IGNORECASE
)
_CHUNK_SIZE   = 8 * 1024 * 1024  # 8 MB


class UnsafeDownloadPathError(ValueError):
    """Raised when Drive-derived path data cannot be contained safely."""


class DownloadCacheInvalidationError(OSError):
    """Raised when a stale cached PDF cannot be removed safely."""


def _sanitize_segment(value: object, *, kind: str) -> str:
    raw = str(value or "")
    if "\x00" in raw:
        raise UnsafeDownloadPathError(f"Unsafe {kind}: contains a null byte")
    if raw in {".", ".."}:
        raise UnsafeDownloadPathError(f"Unsafe {kind}: relative traversal component")
    if Path(raw).is_absolute() or PureWindowsPath(raw).is_absolute():
        raise UnsafeDownloadPathError(f"Unsafe {kind}: absolute path component")
    if PureWindowsPath(raw).drive:
        raise UnsafeDownloadPathError(f"Unsafe {kind}: Windows drive prefix")
    sanitized = _UNSAFE_CHARS.sub("_", raw).strip().rstrip(". ")
    if not sanitized or sanitized in {".", ".."}:
        raise UnsafeDownloadPathError(f"Unsafe {kind}: empty path component")
    if _WINDOWS_RESERVED.match(sanitized):
        sanitized = f"_{sanitized}"
    return sanitized


def _folder_segments(folder_path: object) -> list[str]:
    raw = str(folder_path or "")
    if not raw:
        return []
    if raw.startswith(("/", "\\")) or PureWindowsPath(raw).drive:
        raise UnsafeDownloadPathError("Unsafe folder path: absolute or drive-prefixed")
    normalized = raw.replace("\\", "/")
    parts = normalized.split("/")
    if any(part == "" for part in parts):
        raise UnsafeDownloadPathError("Unsafe folder path: empty component")
    return [_sanitize_segment(part, kind="folder segment") for part in parts]


def _contained_path(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise UnsafeDownloadPathError(
            "Resolved download destination escapes the configured downloads root"
        ) from exc
    return resolved_candidate


def resolve_local_path(output_dir: str, pdf: dict) -> str:
    """
    Return the full local file path for a Drive PDF record.
    Mirrors the folder_path as subdirectories under output_dir.
    """
    _, dest = _dest(output_dir, pdf)
    return dest


def _dest(output_dir: str, pdf: dict) -> tuple[str, str]:
    root = Path(output_dir).resolve(strict=False)
    raw_filename = str(pdf["name"])
    if "/" in raw_filename or "\\" in raw_filename:
        raise UnsafeDownloadPathError("Unsafe filename: path separators are not allowed")
    filename = _sanitize_segment(raw_filename, kind="filename")
    candidate = _contained_path(
        root,
        root.joinpath(*_folder_segments(pdf.get("folder_path", "")), filename),
    )
    return str(candidate.parent), str(candidate)


def remove_cached_download(output_dir: str | Path, cached_path: str | Path) -> bool:
    """Remove one stale cache file only when it resolves below ``output_dir``."""

    root = Path(output_dir).resolve(strict=False)
    target = _contained_path(root, Path(cached_path))
    if not target.exists():
        return False
    if not target.is_file():
        raise DownloadCacheInvalidationError(
            "Cached download target is not a regular file"
        )
    try:
        target.unlink()
    except OSError as exc:
        raise DownloadCacheInvalidationError(
            "Stale cached PDF could not be removed; refresh stopped safely"
        ) from exc
    return True


def _download_file(service, file_id: str, dest_path: str) -> None:
    request = service.files().get_media(fileId=file_id)
    target = Path(dest_path)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".part",
            delete=False,
        ) as fh:
            temporary_path = Path(fh.name)
            downloader = MediaIoBaseDownload(fh, request, chunksize=_CHUNK_SIZE)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    print(f"      {int(status.progress() * 100)}%")
        os.replace(temporary_path, target)
    except Exception:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def download_pdfs(service, records: list[dict], output_dir: str) -> tuple[int, int, int]:
    """
    Download PDF records to output_dir.

    Returns:
        (success_count, skipped_count, failed_count)

    Skips files that already exist locally.
    Logs failures and continues rather than aborting.
    """
    if not records:
        print("[downloader] Nothing to download.")
        return 0, 0, 0

    print(f"[downloader] {len(records)} file(s) → {output_dir!r}")
    success = skipped = failed = 0

    for pdf in records:
        directory, dest_path = _dest(output_dir, pdf)
        label = f"{pdf.get('folder_path') or '(root)'}/{pdf['name']}"

        if os.path.exists(dest_path):
            print(f"  [skip]  {label}")
            skipped += 1
            continue

        os.makedirs(directory, exist_ok=True)
        print(f"  [start] {label}")

        try:
            _download_file(service, pdf["id"], dest_path)
            print(f"  [done]  {label}")
            success += 1
        except (HttpError, OSError) as exc:
            print(f"  [error] {label} — {exc}")
            failed += 1

    print(f"\n[downloader] {success} downloaded, {skipped} skipped, {failed} failed.")
    return success, skipped, failed
