"""Small persistence boundary used by Panda application services."""

from __future__ import annotations

from typing import Protocol

from app.models.document import Document


class DocumentRepository(Protocol):
    """The subset of DocumentStore needed by review and approval services."""

    def get_by_drive_id(self, drive_file_id: str) -> Document | None: ...

    def upsert(self, document: Document) -> None: ...

    def upsert_many(self, documents: list[Document]) -> None: ...
