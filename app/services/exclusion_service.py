"""Permanent exclusion registry and safe cached-PDF deletion.

The exclusion registry prevents a confirmed irrelevant Drive file from being
registered again. Deletion is deliberately limited to Panda's configured
downloads directory; a persisted path is never trusted on its own.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import DOWNLOADS_DIR, EXCLUDED_FILES_JSON

if TYPE_CHECKING:
    from app.models.document import Document

logger = logging.getLogger(__name__)


class ExclusionRegistryError(RuntimeError):
    """Base error for registry operations used by destructive workflows."""


class ExclusionRegistryLoadError(ExclusionRegistryError):
    """The existing registry could not be loaded safely."""


class ExclusionRegistryWriteError(ExclusionRegistryError):
    """The registry could not be persisted atomically."""


class UnsafeLocalPdfDeletionError(ValueError):
    """A cached-PDF deletion target is outside the approved boundary."""


class LocalPdfDeletionError(OSError):
    """A validated cached PDF could not be deleted."""


@dataclass(frozen=True)
class LocalPdfDeletionPlan:
    """Validated deletion target. ``target`` is absent for a null path."""

    target: Path | None
    exists: bool


@dataclass(frozen=True)
class LocalPdfDeletionResult:
    """Observable outcome of a safe cached-PDF deletion."""

    had_path: bool
    existed: bool
    deleted: bool


def confirm_irrelevant(doc: "Document") -> None:
    """Legacy-compatible registry + safe cached-PDF operation."""
    add_exclusion(doc)


def add_exclusion(doc: "Document") -> None:
    """Record *doc* and safely remove its cached PDF.

    The target is validated before the registry changes. If deletion fails
    after a new registry entry was written, a best-effort registry rollback is
    attempted and the original deletion error is re-raised.
    """
    plan = validate_local_pdf_deletion_target(doc.local_path)
    created = record_exclusion(doc)
    try:
        delete_local_pdf_safely(plan=plan)
    except Exception:
        if created:
            try:
                remove_exclusion(doc.drive_file_id)
            except ExclusionRegistryError:
                logger.exception("Could not roll back exclusion registry entry")
        raise


def record_exclusion(doc: "Document") -> bool:
    """Persist one exclusion entry and return whether it was newly created."""
    data = _load_registry(strict=True)
    if doc.drive_file_id in data["excluded"]:
        return False

    data["excluded"][doc.drive_file_id] = {
        "drive_file_id": doc.drive_file_id,
        "file_name": doc.file_name,
        "folder_path": doc.folder_path,
        "detected_doc_type": (doc.extracted_data or {}).get("document_type", ""),
        "excluded_at": datetime.now(timezone.utc).isoformat(),
        "local_path_at_exclusion": doc.local_path,
    }
    _save_registry(data)
    logger.info("Exclusion recorded: %s id=%s", doc.file_name, doc.drive_file_id)
    return True


def remove_exclusion(drive_file_id: str) -> bool:
    """Remove one registry entry for compensating rollback."""
    data = _load_registry(strict=True)
    if drive_file_id not in data["excluded"]:
        return False
    del data["excluded"][drive_file_id]
    _save_registry(data)
    return True


def is_excluded(drive_file_id: str) -> bool:
    """Return whether *drive_file_id* is in the registry."""
    return drive_file_id in _load_registry()["excluded"]


def load_exclusion_ids() -> set[str]:
    """Return all excluded Drive IDs for bulk scan filtering."""
    ids = set(_load_registry()["excluded"].keys())
    logger.debug("Exclusion registry loaded: %d excluded file(s).", len(ids))
    return ids


def validate_local_pdf_deletion_target(
    local_path: str | None,
    downloads_root: str | Path | None = None,
) -> LocalPdfDeletionPlan:
    """Canonicalize and validate a cached-PDF deletion without deleting it."""
    if not local_path or not str(local_path).strip():
        return LocalPdfDeletionPlan(target=None, exists=False)

    root = Path(downloads_root if downloads_root is not None else DOWNLOADS_DIR).resolve(
        strict=False
    )
    raw = str(local_path).strip()
    if os.name != "nt":
        raw = raw.replace("\\", os.sep)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate

    # Never follow a file symlink for deletion. Parent symlink/junction escapes
    # are caught by the resolved containment check below.
    if candidate.is_symlink():
        raise UnsafeLocalPdfDeletionError("Local PDF path is a symbolic link")

    target = candidate.resolve(strict=False)
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise UnsafeLocalPdfDeletionError(
            "Local PDF path is outside Panda's downloads directory"
        ) from exc

    if relative == Path(".") or target.suffix.lower() != ".pdf":
        raise UnsafeLocalPdfDeletionError("Local deletion target is not a cached PDF")
    if target.exists() and not target.is_file():
        raise UnsafeLocalPdfDeletionError("Local deletion target is not a regular file")
    return LocalPdfDeletionPlan(target=target, exists=target.exists())


def delete_local_pdf_safely(
    local_path: str | None = None,
    downloads_root: str | Path | None = None,
    *,
    plan: LocalPdfDeletionPlan | None = None,
) -> LocalPdfDeletionResult:
    """Delete only a validated PDF below Panda's downloads root."""
    validated = plan or validate_local_pdf_deletion_target(local_path, downloads_root)
    if validated.target is None:
        return LocalPdfDeletionResult(had_path=False, existed=False, deleted=False)
    if not validated.exists:
        return LocalPdfDeletionResult(had_path=True, existed=False, deleted=False)
    try:
        validated.target.unlink()
    except OSError as exc:
        raise LocalPdfDeletionError("The local cached PDF could not be removed") from exc
    logger.info("Deleted local cached PDF beneath downloads root")
    return LocalPdfDeletionResult(had_path=True, existed=True, deleted=True)


def _load_registry(*, strict: bool = False) -> dict:
    """Load the registry; legacy scan reads retain their historical fallback."""
    if not EXCLUDED_FILES_JSON.exists():
        return {"version": 1, "excluded": {}}
    try:
        data = json.loads(EXCLUDED_FILES_JSON.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("excluded"), dict):
            raise ValueError("invalid exclusion registry shape")
        return data
    except Exception as exc:
        if strict:
            raise ExclusionRegistryLoadError(
                "The exclusion registry could not be loaded safely"
            ) from exc
        logger.warning("Could not read excluded_files.json; using an empty scan view")
        return {"version": 1, "excluded": {}}


def _save_registry(data: dict) -> None:
    """Atomically write the exclusion registry."""
    EXCLUDED_FILES_JSON.parent.mkdir(parents=True, exist_ok=True)
    tmp = EXCLUDED_FILES_JSON.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(EXCLUDED_FILES_JSON)
    except Exception as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ExclusionRegistryWriteError(
            "The exclusion registry could not be saved"
        ) from exc
