"""
Document model — central data structure for the accountant tool.

Status lifecycle:
  new          — discovered in Drive, not yet processed
  processed    — parsed successfully with reasonable confidence (≥ 0.75)
  needs_review — parsed but low confidence or missing fields
  failed       — exception during download or parsing
  approved     — accountant has reviewed and signed off
  exported     — included in Excel export
  skipped      — system auto-classified as not relevant (receipt, supplier form,
                 etc.).  Local PDF is preserved.  Reversible — accountant can
                 review the raw text and reclassify.  Reason in error_message.
  excluded     — user-confirmed permanent exclusion (legacy name).  Local PDF has
                 been deleted.  Recorded in excluded_files.json so future Drive
                 scans do not re-download or re-process this file.  Never exported.
                 Old records keep this status; new code produces confirmed_irrelevant.
  confirmed_irrelevant — user explicitly confirmed the document is irrelevant via
                 the "Mark as Irrelevant" action.  Local PDF has been deleted.
                 Recorded in excluded_files.json so future Drive scans skip it.
                 Functionally identical to "excluded" but set by the new UI flow.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Document:
    # ── Drive identity ─────────────────────────────────────────────────────────
    drive_file_id: str
    file_name: str
    folder_path: str

    # ── Local state ────────────────────────────────────────────────────────────
    local_path: str = ""
    raw_text_path: str = ""

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    status: str = "new"          # new|processed|needs_review|failed|approved|exported
    confidence: float = 0.0

    # ── Extracted fields (from parser) ─────────────────────────────────────────
    supplier_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    subtotal: Optional[float] = None
    vat: Optional[float] = None
    total: Optional[float] = None
    description: Optional[str] = None

    # ── Raw + corrected storage ────────────────────────────────────────────────
    extracted_data: dict = field(default_factory=dict)
    corrected_data: dict = field(default_factory=dict)

    # ── Error info ─────────────────────────────────────────────────────────────
    error_message: Optional[str] = None

    # ── Export tracking ────────────────────────────────────────────────────────
    exported_to_excel: bool = False

    # ── Irrelevant confirmation ─────────────────────────────────────────────────
    confirmed_irrelevant_at: Optional[str] = None

    # ── Metadata ───────────────────────────────────────────────────────────────
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def effective(self, field_name: str) -> Any:
        """
        Return the corrected value if the accountant set one, otherwise the
        extracted value.  Falls back to the dataclass attribute itself.
        """
        if field_name in self.corrected_data and self.corrected_data[field_name] not in (None, ""):
            return self.corrected_data[field_name]
        return getattr(self, field_name, None)

    def touch(self) -> None:
        self.updated_at = _now()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)
