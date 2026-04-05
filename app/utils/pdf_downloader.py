"""
Temporary utility for downloading discovered PDFs from Google Drive to a local
directory, preserving the folder_path structure.

Intended for manual validation only. Remove or disable once the pipeline is
processing PDFs in-memory.
"""

import os
import re

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# Characters that are invalid in filenames on Windows and Linux/macOS.
# The slash is included because Google Drive permits it in filenames but it
# would be misinterpreted as a path separator locally.
_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')

_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


def _sanitize_name(name: str) -> str:
    """Replace filesystem-unsafe characters with underscores."""
    return _UNSAFE_CHARS.sub("_", name).strip()


def _resolve_dest(output_dir: str, pdf: dict) -> tuple[str, str]:
    """
    Return (directory, full_file_path) for a PDF record.

    folder_path components and the filename are each sanitized before being
    joined, so Drive names with unusual characters are safe on all platforms.
    """
    folder_path = pdf.get("folder_path", "")
    filename = _sanitize_name(pdf["name"])

    if folder_path:
        safe_parts = [_sanitize_name(part) for part in folder_path.split("/")]
        directory = os.path.join(output_dir, *safe_parts)
    else:
        directory = output_dir

    return directory, os.path.join(directory, filename)


def _download_file(service, file_id: str, dest_path: str) -> None:
    """
    Stream a single file from Drive to dest_path using chunked download.
    Prints progress as each chunk completes.
    """
    request = service.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=_CHUNK_SIZE)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"      {int(status.progress() * 100)}%")


def download_pdfs(service, records: list[dict], output_dir: str) -> None:
    """
    Download all PDF records to output_dir, mirroring folder_path as
    subdirectory structure.

    Args:
        service:    Authenticated Google Drive service instance.
        records:    Flat list of PDF dicts as returned by get_folder_pdf_hierarchy.
        output_dir: Root directory for downloaded files.

    Skips files that already exist at the computed local path.
    Logs failures and continues rather than aborting the run.
    """
    total = len(records)
    if total == 0:
        print("[downloader] No PDF records to download.")
        return

    print(f"[downloader] {total} file(s) to download → {output_dir!r}")

    success = skipped = failed = 0

    for pdf in records:
        directory, dest_path = _resolve_dest(output_dir, pdf)
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
        except HttpError as exc:
            print(f"  [error] {label} — API error: {exc}")
            failed += 1
        except OSError as exc:
            print(f"  [error] {label} — file error: {exc}")
            failed += 1

    print(
        f"\n[downloader] Complete — "
        f"{success} downloaded, {skipped} skipped, {failed} failed."
    )
