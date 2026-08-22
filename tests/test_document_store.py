"""Safety and persistence tests for the active JSON DocumentStore."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.document import Document
from app.services.document_store import (
    CURRENT_STORE_VERSION,
    DocumentStore,
    DocumentStoreLoadError,
)


def _document(drive_id: str = "drive-1", **overrides) -> Document:
    values = {
        "drive_file_id": drive_id,
        "file_name": f"{drive_id}.pdf",
        "folder_path": "invoices",
        "status": "processed",
        "supplier_name": "Example Supplier",
        "total": 125.5,
    }
    values.update(overrides)
    return Document(**values)


def _write_payload(path: Path, documents: list[Document], version: int = 2) -> None:
    path.write_text(
        json.dumps(
            {"version": version, "documents": [doc.to_dict() for doc in documents]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_missing_store_starts_empty_without_creating_a_file(tmp_path: Path) -> None:
    path = tmp_path / "documents.json"

    store = DocumentStore(path)

    assert store.total() == 0
    assert not path.exists()


def test_valid_current_store_loads(tmp_path: Path) -> None:
    path = tmp_path / "documents.json"
    _write_payload(path, [_document()])

    store = DocumentStore(path)

    assert store.total() == 1
    assert store.get_by_drive_id("drive-1").supplier_name == "Example Supplier"


def test_save_round_trip_preserves_documents_and_current_schema(tmp_path: Path) -> None:
    path = tmp_path / "documents.json"
    store = DocumentStore(path)

    store.upsert(_document(corrected_data={"total": 130.0}))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == CURRENT_STORE_VERSION
    assert isinstance(payload["documents"], list)
    assert len(payload["documents"]) == 1

    reloaded = DocumentStore(path)
    assert reloaded.get_by_drive_id("drive-1").effective("total") == 130.0


def test_save_uses_temporary_file_then_replaces_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "documents.json"
    calls: list[tuple[Path, Path]] = []
    original_replace = Path.replace

    def recording_replace(source: Path, target: Path) -> Path:
        calls.append((source, target))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", recording_replace)
    DocumentStore(path).upsert(_document())

    assert calls == [(path.with_suffix(".tmp"), path)]
    assert path.exists()
    assert not path.with_suffix(".tmp").exists()


def test_malformed_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "documents.json"
    path.write_text('{"version": 2, "documents": [', encoding="utf-8")

    with pytest.raises(DocumentStoreLoadError) as error:
        DocumentStore(path)

    assert error.value.category == "malformed_json"


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"version": 2},
        {"version": 2, "documents": {}},
    ],
)
def test_invalid_top_level_structure_fails_closed(tmp_path: Path, payload) -> None:
    path = tmp_path / "documents.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DocumentStoreLoadError) as error:
        DocumentStore(path)

    assert error.value.category == "invalid_shape"


@pytest.mark.parametrize("version", [None, "2", 1, 3])
def test_invalid_or_unsupported_version_fails_closed(tmp_path: Path, version) -> None:
    path = tmp_path / "documents.json"
    path.write_text(
        json.dumps({"version": version, "documents": []}),
        encoding="utf-8",
    )

    with pytest.raises(DocumentStoreLoadError) as error:
        DocumentStore(path)

    assert error.value.category in {"invalid_version", "unsupported_version"}


def test_invalid_document_entry_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "documents.json"
    path.write_text(
        json.dumps({"version": 2, "documents": [{"file_name": "missing-id.pdf"}]}),
        encoding="utf-8",
    )

    with pytest.raises(DocumentStoreLoadError) as error:
        DocumentStore(path)

    assert error.value.category == "invalid_document"


def test_unreadable_existing_store_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "documents.json"
    path.write_text("placeholder", encoding="utf-8")

    with patch.object(Path, "open", side_effect=PermissionError("access denied")):
        with pytest.raises(DocumentStoreLoadError) as error:
            DocumentStore(path)

    assert error.value.category == "unreadable"
    assert "access denied" not in str(error.value)


def test_inaccessible_store_path_is_not_treated_as_missing(tmp_path: Path) -> None:
    path = tmp_path / "documents.json"

    with patch.object(Path, "stat", side_effect=PermissionError("access denied")):
        with pytest.raises(DocumentStoreLoadError) as error:
            DocumentStore(path)

    assert error.value.category == "unreadable"


def test_failed_load_does_not_modify_or_replace_source(tmp_path: Path) -> None:
    path = tmp_path / "documents.json"
    original = b'{"version": 2, "documents": [broken'
    path.write_bytes(original)

    with pytest.raises(DocumentStoreLoadError):
        DocumentStore(path)

    assert path.read_bytes() == original
    assert not path.with_suffix(".tmp").exists()
