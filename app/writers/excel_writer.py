"""
Excel writer: export approved Document records to the output workbook.

Columns (Hebrew headers visible to the accountant):
  שם קובץ     — file name
  נתיב         — folder path in Drive
  סוג מסמך    — document type (human-readable)
  שם ספק      — supplier name
  תאריך מסמך  — invoice date
  מספר מסמך   — invoice number
  סכום         — total amount

Internal (hidden) column appended at the end:
  drive_file_id — deduplication key

Duplicate rows (same supplier + number + date + amount) are highlighted
in light red.

Public API
----------
export_documents(docs, output_path) -> int   # returns count exported
"""
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DISPLAY_COLS = [
    "שם קובץ",
    "נתיב",
    "סוג מסמך",
    "שם ספק",
    "תאריך מסמך",
    "מספר מסמך",
    "סכום",
]
_ALL_COLS = _DISPLAY_COLS + ["drive_file_id"]
_DUP_COLOR = "FFC7CE"

_TYPE_LABELS = {
    "transaction_invoice": "חשבון עסקה",
    "tax_invoice":         "חשבונית מס",
    "payment_request":     "דרישת תשלום",
}


def export_documents(docs: list, output_path: str) -> int:
    """
    Export Document objects with status "approved" to an Excel workbook.

    - Skips docs already present (by drive_file_id).
    - Highlights duplicate rows.
    - Returns the number of newly written rows.
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip install pandas openpyxl")

    existing_df = _load_existing(output_path)
    existing_ids: set = (
        set(existing_df["drive_file_id"].astype(str).tolist())
        if not existing_df.empty else set()
    )

    new_rows = []
    for doc in docs:
        fid = doc.drive_file_id
        if fid in existing_ids:
            logger.debug("Skipping already-exported: %s", doc.file_name)
            continue

        # Use corrected values where available, otherwise extracted values.
        supplier = doc.effective("supplier_name") or ""
        date     = doc.effective("invoice_date")  or ""
        number   = doc.effective("invoice_number") or ""
        total    = doc.effective("total")

        doc_type = _type_label(doc.extracted_data.get("document_type"))

        new_rows.append({
            "שם קובץ":     doc.file_name,
            "נתיב":         doc.folder_path,
            "סוג מסמך":    doc_type,
            "שם ספק":      supplier,
            "תאריך מסמך":  date,
            "מספר מסמך":   number,
            "סכום":         total if total is not None else "",
            "drive_file_id": fid,
        })

    if not new_rows and existing_df.empty:
        return 0

    new_df = (
        pd.DataFrame(new_rows, columns=_ALL_COLS) if new_rows
        else pd.DataFrame(columns=_ALL_COLS)
    )
    combined = (
        pd.concat([existing_df, new_df], ignore_index=True)
        if not existing_df.empty else new_df
    )

    # Duplicate detection
    dup_keys = ["שם ספק", "מספר מסמך", "תאריך מסמך", "סכום"]
    has_content = combined[dup_keys].apply(lambda r: any(str(v).strip() for v in r), axis=1)
    key_tuples  = combined[dup_keys].apply(tuple, axis=1)
    freq        = key_tuples.value_counts()
    dup_mask    = has_content & key_tuples.map(lambda k: freq[k] > 1)
    dup_indices = set(combined.index[dup_mask].tolist())

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    combined.to_excel(output_path, index=False, sheet_name="חשבוניות")
    _format_workbook(output_path, dup_indices)

    logger.info("Exported %d new row(s) to %s", len(new_rows), output_path)
    return len(new_rows)


# ── Legacy API (kept for backward compatibility with old main.py) ──────────────

def append_records(records: list, output_path: str) -> None:
    """
    Append InvoiceRecord objects (old model) to an Excel workbook.
    Kept so the original CLI pipeline still works.
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip install pandas openpyxl")

    _LEGACY_DISPLAY = ["שם קובץ", "סוג קובץ", "שם ספק", "תאריך מסמך", "מספר מסמך", "סכום"]
    _LEGACY_ALL     = _LEGACY_DISPLAY + ["file_id"]

    existing_df = _load_existing_legacy(output_path, _LEGACY_ALL)
    existing_ids: set = (
        set(existing_df["file_id"].astype(str).tolist())
        if not existing_df.empty else set()
    )

    new_rows = []
    for rec in records:
        fid = getattr(rec, "file_id", "") or ""
        if fid and fid in existing_ids:
            continue
        new_rows.append({
            "שם קובץ":    getattr(rec, "file_name", "") or "",
            "סוג קובץ":   _type_label(getattr(rec, "document_type", None)),
            "שם ספק":     getattr(rec, "business_name", "") or "",
            "תאריך מסמך": getattr(rec, "invoice_date", "") or "",
            "מספר מסמך":  getattr(rec, "invoice_number", "") or "",
            "סכום":        getattr(rec, "amount", "") if getattr(rec, "amount", None) is not None else "",
            "file_id":     fid,
        })

    if not new_rows and existing_df.empty:
        return

    new_df  = pd.DataFrame(new_rows, columns=_LEGACY_ALL) if new_rows else pd.DataFrame(columns=_LEGACY_ALL)
    combined = pd.concat([existing_df, new_df], ignore_index=True) if not existing_df.empty else new_df

    dup_keys = ["שם ספק", "מספר מסמך", "תאריך מסמך", "סכום"]
    has_content = combined[dup_keys].apply(lambda r: any(str(v).strip() for v in r), axis=1)
    key_tuples  = combined[dup_keys].apply(tuple, axis=1)
    freq        = key_tuples.value_counts()
    dup_mask    = has_content & key_tuples.map(lambda k: freq[k] > 1)
    dup_indices = set(combined.index[dup_mask].tolist())

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    combined.to_excel(output_path, index=False, sheet_name="חשבוניות")
    _format_workbook(output_path, dup_indices)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _type_label(doc_type: Optional[str]) -> str:
    if not doc_type:
        return ""
    return _TYPE_LABELS.get(doc_type, doc_type)


def _load_existing(path: str):
    import pandas as pd
    if not os.path.exists(path):
        return pd.DataFrame(columns=_ALL_COLS)
    try:
        df = pd.read_excel(path, sheet_name="חשבוניות", dtype=str)
        for col in _ALL_COLS:
            if col not in df.columns:
                df[col] = ""
        return df[_ALL_COLS]
    except Exception:
        return pd.DataFrame(columns=_ALL_COLS)


def _load_existing_legacy(path: str, cols: list):
    import pandas as pd
    if not os.path.exists(path):
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_excel(path, sheet_name="חשבוניות", dtype=str)
        for col in cols:
            if col not in df.columns:
                df[col] = ""
        return df[cols]
    except Exception:
        return pd.DataFrame(columns=cols)


def _format_workbook(path: str, dup_indices: set) -> None:
    from openpyxl import load_workbook
    from openpyxl.styles import PatternFill
    from openpyxl.utils import get_column_letter

    fill = PatternFill(start_color=_DUP_COLOR, end_color=_DUP_COLOR, fill_type="solid")

    wb = load_workbook(path)
    ws = wb.active

    for idx in dup_indices:
        for cell in ws[idx + 2]:   # +2: 1-based + header row
            cell.fill = fill

    for col_idx, col_cells in enumerate(ws.columns, start=1):
        max_len = max((len(str(c.value or "")) for c in col_cells), default=10)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 55)

    wb.save(path)
