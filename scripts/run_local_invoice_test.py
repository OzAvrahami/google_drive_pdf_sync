"""
Local invoice pipeline test runner
===================================
Scans a local folder of downloaded PDFs, runs the invoice parser,
and writes results to an Excel file.

Usage (from the project root):
    python -m scripts.run_local_invoice_test

Edit LOCAL_PDF_ROOT and OUTPUT_EXCEL_PATH below before running.
"""

import sys
import os
import traceback
from pathlib import Path

# Allow imports from project root as 'app.*'
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parsers.pdf_parser import extract_text_from_pdf
from app.parsers.invoice_parser import classify_document_type, parse_invoice_text

# ── Configuration ──────────────────────────────────────────────────────────────

LOCAL_PDF_ROOT   = r"D:\code\google_drive_pdf_sync\downloads\ינואר 2026\חשבון עסקה בגין ינואר"
OUTPUT_EXCEL_PATH = r"D:\code\google_drive_pdf_sync\output\test\invoice_test_results.xlsx"

# ── PDF scanning ───────────────────────────────────────────────────────────────

def scan_pdfs(root: str) -> list[dict]:
    root_path = Path(root)
    records = []
    for pdf_path in sorted(root_path.rglob("*.pdf")):
        rel = pdf_path.relative_to(root_path)
        records.append({
            "file_name":          pdf_path.name,
            "parent_folder_name": pdf_path.parent.name,
            "relative_path":      str(rel),
            "full_path":          str(pdf_path),
        })
    return records


# ── Per-file processing ────────────────────────────────────────────────────────

_STATUS_MAP = {
    "חשבון עסקה":       "processed",
    "חשבונית מס":       "processed",
    "קבלה":             "skipped_receipt",
    "חשבונית מס קבלה": "skipped_invoice_receipt",
}


def process_pdf(meta: dict) -> dict:
    row = {
        "file_name":          meta["file_name"],
        "parent_folder_name": meta["parent_folder_name"],
        "relative_path":      meta["relative_path"],
        "full_path":          meta["full_path"],
        "document_type":      "",
        "status":             "",
        "business_name":      "",
        "invoice_date":       "",
        "invoice_number":     "",
        "amount":             "",
        "error":              "",
    }

    try:
        text = extract_text_from_pdf(meta["full_path"])
        doc_type = classify_document_type(text)

        if doc_type is None:
            row["status"] = "unrecognized_document_type"
            return row

        row["document_type"] = doc_type
        row["status"] = _STATUS_MAP.get(doc_type, "unrecognized_document_type")

        parsed = parse_invoice_text(text)
        if parsed:
            row["document_type"]  = parsed.get("document_type", doc_type)
            row["business_name"]  = parsed.get("business_name")  or ""
            row["invoice_date"]   = parsed.get("invoice_date")   or ""
            row["invoice_number"] = parsed.get("invoice_number") or ""
            amount = parsed.get("amount")
            row["amount"] = amount if amount is not None else ""

    except Exception as exc:
        row["status"] = "parse_failed"
        row["error"]  = f"{type(exc).__name__}: {exc}"

    return row


# ── Excel export ───────────────────────────────────────────────────────────────

def write_excel(rows: list[dict], output_path: str) -> None:
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip install pandas openpyxl")

    df = pd.DataFrame(rows, columns=[
        "file_name", "parent_folder_name", "relative_path", "full_path",
        "document_type", "status",
        "business_name", "invoice_date", "invoice_number", "amount", "error",
    ])
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, index=False, sheet_name="Results")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    if not Path(LOCAL_PDF_ROOT).exists():
        print(f"ERROR: LOCAL_PDF_ROOT does not exist: {LOCAL_PDF_ROOT}")
        sys.exit(1)

    print(f"Scanning: {LOCAL_PDF_ROOT}")
    pdfs = scan_pdfs(LOCAL_PDF_ROOT)
    print(f"Found {len(pdfs)} PDF(s)\n")

    rows = []
    for meta in pdfs:
        print(f"  {meta['relative_path']} ... ", end="", flush=True)
        row = process_pdf(meta)
        rows.append(row)
        print(row["status"])

    write_excel(rows, OUTPUT_EXCEL_PATH)

    # Summary
    from collections import Counter
    counts = Counter(r["status"] for r in rows)
    processed = counts.get("processed", 0)
    skipped   = counts.get("skipped_receipt", 0) + counts.get("skipped_invoice_receipt", 0)
    failed    = counts.get("parse_failed", 0)
    other     = len(rows) - processed - skipped - failed

    print(f"\n── Summary ───────────────────────────")
    print(f"  Total PDFs : {len(rows)}")
    print(f"  Processed  : {processed}")
    print(f"  Skipped    : {skipped}")
    print(f"  Failed     : {failed}")
    if other:
        print(f"  Other      : {other}")
    print(f"\nExcel written to: {OUTPUT_EXCEL_PATH}")


if __name__ == "__main__":
    main()
