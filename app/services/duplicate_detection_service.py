"""
Duplicate document detection.

Runs after invoice parsing. Compares the newly processed document against
existing documents in the store using normalized field matching.

Matching strategy:
  EXACT  — supplier_name + invoice_number + date all match → duplicate_confidence='exact'
  HIGH   — supplier_name + invoice_date + total match (when invoice_number absent)
           → duplicate_confidence='high'

False-positive prevention:
  - Requires supplier_name to be present
  - EXACT match requires invoice_number AND date to match
  - HIGH match requires all three fields (supplier + date + amount)
  - Only compares against documents with status in _VALID_COMPARISON_STATUSES
  - Skips if supplier_name is null/empty
"""
import re
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.document import Document
    from app.services.document_store import DocumentStore

logger = logging.getLogger(__name__)

_VALID_COMPARISON_STATUSES = frozenset({
    "processed", "needs_review", "approved", "exported"
})


def detect_and_mark_duplicate(doc: "Document", store: "DocumentStore") -> None:
    """
    Check doc against existing documents in store.
    Sets is_duplicate_suspected, suspected_duplicate_of, duplicate_confidence
    on doc in-place if a duplicate is found.
    Does nothing if insufficient data for reliable comparison.
    """
    supplier = doc.effective("supplier_name")
    if not supplier or not supplier.strip():
        return

    norm_supplier = _normalize(supplier)
    norm_number   = _normalize_invoice_number(doc.effective("invoice_number"))
    norm_date     = _normalize_date(doc.effective("invoice_date"))
    amount        = doc.effective("total")

    candidates = [
        d for d in store.all()
        if d.drive_file_id != doc.drive_file_id
        and d.status in _VALID_COMPARISON_STATUSES
    ]

    for existing in candidates:
        existing_supplier = existing.effective("supplier_name")
        if not existing_supplier:
            continue
        if _normalize(existing_supplier) != norm_supplier:
            continue

        # EXACT: supplier + invoice_number + date
        if norm_number:
            existing_number = _normalize_invoice_number(existing.effective("invoice_number"))
            if existing_number and existing_number == norm_number:
                existing_date = _normalize_date(existing.effective("invoice_date"))
                # If both dates are available they must match
                if norm_date and existing_date and norm_date != existing_date:
                    continue
                logger.warning(
                    "Duplicate detected (exact): %r matches existing %r (drive_id=%s)",
                    doc.file_name, existing.file_name, existing.drive_file_id,
                )
                doc.is_duplicate_suspected = True
                doc.suspected_duplicate_of = [existing.drive_file_id]
                doc.duplicate_confidence   = "exact"
                return

        # HIGH: supplier + date + amount (only when invoice_number is absent)
        if not norm_number and norm_date and amount is not None:
            existing_date   = _normalize_date(existing.effective("invoice_date"))
            existing_amount = existing.effective("total")
            if (existing_date and existing_date == norm_date
                    and existing_amount is not None
                    and abs(existing_amount - amount) < 0.01):
                logger.warning(
                    "Duplicate detected (high confidence): %r matches existing %r (drive_id=%s)",
                    doc.file_name, existing.file_name, existing.drive_file_id,
                )
                doc.is_duplicate_suspected = True
                doc.suspected_duplicate_of = [existing.drive_file_id]
                doc.duplicate_confidence   = "high"
                return


# ── Normalization helpers ───────────────────────────────────────────────────────

def _normalize(value) -> str:
    """Collapse whitespace for consistent comparison."""
    if not value:
        return ""
    return " ".join(str(value).strip().split())


def _normalize_invoice_number(value) -> str:
    """Strip delimiters and uppercase for robust invoice number comparison."""
    if not value:
        return ""
    s = " ".join(str(value).strip().split())
    s = re.sub(r'[-/\\._\s]', '', s)
    return s.upper()


def _normalize_date(date_str) -> str:
    """Convert DD/MM/YYYY to YYYY-MM-DD for reliable comparison."""
    if not date_str:
        return ""
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})', str(date_str).strip())
    if m:
        day, month, year = m.groups()
        return f"{year}-{month}-{day}"
    return ""
