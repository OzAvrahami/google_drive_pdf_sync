"""
Excel writer: incrementally append new invoice records to the output workbook.

The sheet has two column groups:
  - Display columns (Hebrew headers) — what accountants see
  - Internal column (file_id)        — used for deduplication on re-runs

Duplicate rows (same supplier + document number + date + amount) are
highlighted in light red so they are easy to spot.

Public API
----------
append_records(records, output_path) -> None
"""

import os
from pathlib import Path
from typing import Optional

# Display columns shown to users
_DISPLAY_COLS = ["שם קובץ", "סוג קובץ", "שם ספק", "תאריך מסמך", "מספר מסמך", "סכום"]
# Internal column kept at the end for dedup — not for presentation
_ALL_COLS = _DISPLAY_COLS + ["file_id"]

_DUP_COLOR = "FFC7CE"   # standard Excel "bad" light-red


def append_records(records: list, output_path: str) -> None:
    """
    Append new InvoiceRecord objects to the Excel workbook at output_path.

    - If the workbook does not exist it is created from scratch.
    - Rows whose file_id already appears in the sheet are skipped (dedup).
    - After appending, duplicate rows (by supplier+number+date+amount) are
      highlighted in light red.
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip install pandas openpyxl")

    # Load existing data
    existing_df = _load_existing(output_path)
    existing_ids: set = set(existing_df["file_id"].astype(str).tolist()) if not existing_df.empty else set()

    # Build rows for records not yet in the sheet
    new_rows = []
    for rec in records:
        fid = getattr(rec, "file_id", "") or ""
        if fid and fid in existing_ids:
            continue   # already in Excel
        new_rows.append({
            "שם קובץ":    getattr(rec, "file_name", "") or "",
            "סוג קובץ":   _type_label(getattr(rec, "document_type", None)),
            "שם ספק":     getattr(rec, "business_name", "") or "",
            "תאריך מסמך": getattr(rec, "invoice_date", "") or "",
            "מספר מסמך":  getattr(rec, "invoice_number", "") or "",
            "סכום":       getattr(rec, "amount", "") if getattr(rec, "amount", None) is not None else "",
            "file_id":    fid,
        })

    if not new_rows and existing_df.empty:
        return  # nothing to write

    new_df = pd.DataFrame(new_rows, columns=_ALL_COLS) if new_rows else pd.DataFrame(columns=_ALL_COLS)
    combined = pd.concat([existing_df, new_df], ignore_index=True) if not existing_df.empty else new_df

    # Duplicate detection: same (שם ספק, מספר מסמך, תאריך מסמך, סכום)
    dup_key_cols = ["שם ספק", "מספר מסמך", "תאריך מסמך", "סכום"]
    has_content = combined[dup_key_cols].apply(lambda r: any(str(v).strip() for v in r), axis=1)
    counts = combined[dup_key_cols].apply(tuple, axis=1)
    freq = counts.value_counts()
    dup_mask = has_content & counts.map(lambda k: freq[k] > 1)
    dup_indices = set(combined.index[dup_mask].tolist())

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    combined.to_excel(output_path, index=False, sheet_name="חשבוניות")

    # Apply highlight and column formatting with openpyxl
    _format_workbook(output_path, dup_indices, len(combined))


# ── Helpers ────────────────────────────────────────────────────────────────────

_TYPE_LABELS = {
    "transaction_invoice": "חשבון עסקה",
    "tax_invoice":         "חשבונית מס",
    "payment_request":     "דרישת תשלום",
}


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
        # Ensure all expected columns exist (handles files from earlier schema)
        for col in _ALL_COLS:
            if col not in df.columns:
                df[col] = ""
        return df[_ALL_COLS]
    except Exception:
        return pd.DataFrame(columns=_ALL_COLS)


def _format_workbook(path: str, dup_indices: set, total_rows: int) -> None:
    from openpyxl import load_workbook
    from openpyxl.styles import PatternFill
    from openpyxl.utils import get_column_letter

    fill = PatternFill(start_color=_DUP_COLOR, end_color=_DUP_COLOR, fill_type="solid")

    wb = load_workbook(path)
    ws = wb.active

    # Highlight duplicate rows (excel rows are 1-based; row 1 is header)
    for idx in dup_indices:
        excel_row = idx + 2
        for cell in ws[excel_row]:
            cell.fill = fill

    # Auto-fit column widths (approximate)
    for col_idx, col_cells in enumerate(ws.columns, start=1):
        max_len = max((len(str(c.value or "")) for c in col_cells), default=10)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 50)

    wb.save(path)
