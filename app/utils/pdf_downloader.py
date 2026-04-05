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

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# Characters invalid in filenames on Windows and macOS/Linux.
_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')
_CHUNK_SIZE   = 8 * 1024 * 1024  # 8 MB


def _sanitize_name(name: str) -> str:
    return _UNSAFE_CHARS.sub("_", name).strip()


def resolve_local_path(output_dir: str, pdf: dict) -> str:
    """
    Return the full local file path for a Drive PDF record.
    Mirrors the folder_path as subdirectories under output_dir.
    """
    _, dest = _dest(output_dir, pdf)
    return dest


def _dest(output_dir: str, pdf: dict) -> tuple[str, str]:
    folder_path = pdf.get("folder_path", "")
    filename    = _sanitize_name(pdf["name"])
    if folder_path:
        safe_parts = [_sanitize_name(p) for p in folder_path.split("/")]
        directory  = os.path.join(output_dir, *safe_parts)
    else:
        directory = output_dir
    return directory, os.path.join(directory, filename)


def _download_file(service, file_id: str, dest_path: str) -> None:
    request = service.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=_CHUNK_SIZE)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"      {int(status.progress() * 100)}%")


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
