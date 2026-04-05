"""
Main pipeline entry point.

Run from the project root:
    python -m app.main

Flow
----
1.  Authenticate with Google Drive (service account).
2.  Recursively scan the configured parent folder for PDF files.
3.  Compare against state to find only new or changed files.
4.  Download new PDFs to the local downloads directory.
5.  Extract text and parse invoice fields from each new PDF.
6.  Append new records to the Excel output file.
7.  Persist updated state so repeated runs stay incremental.
"""

import sys
import os

# Allow running as  `python app/main.py`  as well as  `python -m app.main`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import DOWNLOAD_DIR, EXCEL_OUTPUT_PATH, STATE_FILE_PATH
from app.clients.drive_client import get_drive_service, get_folder_pdf_hierarchy
from app.state.state_manager import StateManager
from app.utils.pdf_downloader import download_pdfs, resolve_local_path
from app.parsers.pdf_parser import extract_text_from_pdf
from app.parsers.invoice_parser import classify_document_type, parse_invoice_text
from app.models.record import InvoiceRecord
from app.writers.excel_writer import append_records


def main() -> None:
    # ── 1. Auth ────────────────────────────────────────────────────────────────
    print("[main] Connecting to Google Drive...")
    service, parent_folder_id = get_drive_service()

    # ── 2. Discover ────────────────────────────────────────────────────────────
    print("[main] Scanning for PDF files...")
    all_pdfs = get_folder_pdf_hierarchy(service, parent_folder_id)
    print(f"[main] Found {len(all_pdfs)} PDF(s) on Drive.")

    # ── 3. Filter new / changed ────────────────────────────────────────────────
    state = StateManager(STATE_FILE_PATH)
    new_pdfs = state.filter_new(all_pdfs)

    if not new_pdfs:
        print("[main] Nothing new to process. Excel is up to date.")
        return

    print(f"[main] {len(new_pdfs)} new/changed file(s) to process.")

    # ── 4. Download ────────────────────────────────────────────────────────────
    download_pdfs(service, new_pdfs, DOWNLOAD_DIR)

    # ── 5. Parse ───────────────────────────────────────────────────────────────
    print("\n[main] Parsing invoices...")
    records: list[InvoiceRecord] = []

    for pdf in new_pdfs:
        local_path = resolve_local_path(DOWNLOAD_DIR, pdf)
        label = f"{pdf.get('folder_path') or '(root)'}/{pdf['name']}"

        rec = InvoiceRecord(
            file_id     = pdf["id"],
            file_name   = pdf["name"],
            folder_path = pdf.get("folder_path", ""),
        )

        if not os.path.exists(local_path):
            rec.status = "parse_failed"
            rec.error  = "Local file not found after download"
            state.mark_processed(pdf, status="failed", error=rec.error)
            records.append(rec)
            print(f"  [missing] {label}")
            continue

        try:
            text      = extract_text_from_pdf(local_path)
            doc_type  = classify_document_type(text)
            parsed    = parse_invoice_text(text)

            if parsed:
                rec.status         = "processed"
                rec.document_type  = parsed.get("document_type")
                rec.business_name  = parsed.get("business_name")
                rec.invoice_date   = parsed.get("invoice_date")
                rec.invoice_number = parsed.get("invoice_number")
                rec.amount         = parsed.get("amount")
            elif doc_type in {"קבלה"}:
                rec.status        = "skipped_receipt"
                rec.document_type = doc_type
            elif doc_type in {"חשבונית מס קבלה"}:
                rec.status        = "skipped_invoice_receipt"
                rec.document_type = doc_type
            else:
                rec.status        = "unrecognized_document_type"
                rec.document_type = doc_type

            state.mark_processed(pdf, status=rec.status)
            print(f"  [{rec.status}] {label}")

        except Exception as exc:
            rec.status = "parse_failed"
            rec.error  = f"{type(exc).__name__}: {exc}"
            state.mark_processed(pdf, status="failed", error=rec.error)
            print(f"  [failed] {label} — {exc}")

        records.append(rec)

    # ── 6. Write Excel ─────────────────────────────────────────────────────────
    processed = [r for r in records if r.status == "processed"]
    if processed:
        print(f"\n[main] Writing {len(processed)} record(s) to Excel...")
        append_records(processed, EXCEL_OUTPUT_PATH)
        print(f"[main] Excel updated: {EXCEL_OUTPUT_PATH}")
    else:
        print("\n[main] No processable records — Excel unchanged.")

    # ── 7. Save state ──────────────────────────────────────────────────────────
    state.save()

    # ── Summary ────────────────────────────────────────────────────────────────
    from collections import Counter
    counts = Counter(r.status for r in records)
    print(f"\n── Run summary ──────────────────────────────")
    print(f"  Total processed : {len(records)}")
    print(f"  Invoices written: {counts.get('processed', 0)}")
    print(f"  Skipped receipts: {counts.get('skipped_receipt', 0) + counts.get('skipped_invoice_receipt', 0)}")
    print(f"  Unrecognized    : {counts.get('unrecognized_document_type', 0)}")
    print(f"  Errors          : {counts.get('parse_failed', 0)}")


if __name__ == "__main__":
    main()
