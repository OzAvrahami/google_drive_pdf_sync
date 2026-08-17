# Panda Product Flows

These flows describe the current implementation as traced from source. They do not define the desired Panda 2.0 experience. Primary workflow statuses and fields are detailed in [Data Model](DATA_MODEL.md).

## 1. Application Startup

**Trigger:** The user runs `python run.py`.

**Main sources:** `run.py`, `app/config.py`, `app/services/document_store.py`, `app/ui/main_window.py`.

1. `run.main()` calls `ensure_dirs()`, which creates the configured local runtime directories.
2. A `QApplication` is created, assigned the current Hebrew application label, and set to RTL.
3. The global Qt style sheet in `run.py` is applied.
4. `DocumentStore` loads the local document JSON.
5. `MainWindow` is constructed with the store and shown.
6. The New Documents view is selected initially and table/count projections are populated.

**Failure path:** An unhandled startup configuration, import, or store-loading failure can prevent the UI from opening. A corrupt store may instead be treated as empty; see [Current State](CURRENT_STATE.md#document-store-recovery).

**User-visible result:** The local desktop shell opens with sidebar, toolbar, queue table, and status bar.

## 2. Google Drive Scan

**Trigger:** The user selects the toolbar Drive-scan action.

**Main sources:** `app/ui/main_window.py:MainWindow._on_scan()`, `app/ui/workers.py:ScanWorker`, `app/services/drive_sync_service.py:DriveSyncService.scan()`, `app/clients/drive_client.py`.

1. The UI starts `ScanWorker` and locks toolbar actions.
2. `DriveSyncService` resolves the configured parent-folder ID and authenticates with the service-account file.
3. `get_folder_pdf_hierarchy()` recursively lists folders and PDF MIME-type entries.
4. Drive IDs in the local exclusion registry are omitted.
5. An unseen Drive ID creates a `Document` with status `new`.
6. A non-finalized record whose Drive modification time appears newer than local `updated_at` is updated and returned to `new`.
7. Records in `approved`, `exported`, `excluded`, or `confirmed_irrelevant` are not requeued.
8. New and changed records are persisted in one `upsert_many()` call.

**Persistence effects:** Document metadata and `new` status are written to the document store; no PDF is downloaded by scanning.

**Failure path:** Missing folder configuration, authentication failure, API error, or traversal error reaches the worker error signal and a user-facing error dialog.

**User-visible result:** Progress messages and a summary of total, new, updated, skipped, and excluded entries; counts/table then refresh.

## 3. New Document Processing

**Trigger:** The user selects the Process action.

**Main sources:** `MainWindow._on_process()`, `ProcessWorker`, `ProcessingService.process_new()` and `ProcessingService._process_one()`.

1. `ProcessWorker` selects all documents currently in `new`.
2. It authenticates with Drive once for the batch.
3. Each document is downloaded or resolved locally, extracted, classified, parsed, validated, scored, checked for duplicates, and persisted.
4. A successfully parsed record becomes `processed` or `needs_review`.
5. An automatically excluded document type becomes `skipped`.
6. An exception changes the record to `failed`, stores `error_message`, and continues with the remaining batch.

**Persistence effects:** PDF and text files may be created; parsing and workflow fields are updated in the document JSON.

**User-visible result:** A progress dialog receives per-file progress and a completion summary. The affected table rows and queue counts refresh.

## 4. PDF Extraction

**Trigger:** Processing reaches a local PDF.

**Main sources:** `app/parsers/pdf_parser.py:extract_text_from_pdf()`, `app/utils/text_helpers.py:normalize_rtl_text()`.

1. pdfplumber opens the local PDF.
2. Text is extracted page by page.
3. Private-use artifacts are removed and each page's text is normalized for Hebrew/RTL extraction.
4. Page text is joined into one string.
5. `ProcessingService` writes that text to `data/text/<Drive ID>.txt` and records `raw_text_path`.

**Failure path:** A missing, unreadable, encrypted, malformed, or otherwise unsupported PDF raises into processing and results in `failed`.

**User-visible result:** Extracted text becomes available in the Review dialog. There is no OCR fallback for image-only PDFs.

## 5. Document Classification

**Trigger:** Text extraction succeeds.

**Main source:** `app/parsers/invoice_parser.py:classify_document_type()`.

1. The classifier searches normalized extracted text for implemented Hebrew document-type patterns.
2. A detected value is returned as `document_type`.
3. Types present in `EXCLUDED_DOCUMENT_TYPES` follow the automatic skipped flow.
4. Other or unknown types continue to field parsing; classification alone does not approve a record.

**Persistence effects:** For skipped records, `extracted_data` contains the document type and `error_message` holds the reason.

**Failure path:** No matching label returns no type; later parsing/confidence determines whether review is needed.

## 6. Invoice Field Extraction

**Trigger:** The document is not automatically skipped.

**Main source:** `app/parsers/invoice_parser.py:parse_invoice_text()`.

1. The parser derives document type.
2. It attempts supplier/business-name, invoice-date, invoice-number, and amount extraction.
3. It normalizes dates, numeric amounts, and candidate names.
4. It applies correction-map substitutions as a post-processing layer.
5. The result, including supplier-validation metadata, becomes `Document.extracted_data`.
6. Selected values are copied to the active document fields used by the UI and export.

**Persistence effects:** Parsed values, extraction metadata, confidence, and status are stored in the document JSON.

**Failure path:** Missing fields remain empty; a completely absent/weak result receives low confidence and routes to review unless an exception causes `failed`.

## 7. Supplier Validation

**Trigger:** A supplier candidate is extracted.

**Main sources:** `app/parsers/supplier_validator.py:validate_supplier()`, supplier rules in local JSON.

1. The validator scores the proposed supplier using text characteristics and learned rules.
2. Address-like or otherwise improbable candidates are rejected.
3. A better text candidate can be selected as a fallback.
4. Validation metadata, including score, validity, and fallback use, is returned with parsed data.
5. A rejected supplier with no fallback forces `needs_review`, regardless of overall numeric score.

**Failure/default path:** Auxiliary rule-file read failures can fall back to default structures; the result may therefore omit learned behavior.

## 8. Confidence Routing

**Trigger:** Parsing and supplier validation finish.

**Main source:** `app/services/processing_service.py:_confidence()`.

1. Invoice date, invoice number, and amount contribute 0.25 each when present.
2. Supplier validation contributes up to 0.25 based on its 0–100 score.
3. The score is rounded and stored as `Document.confidence`.
4. Confidence at or above `0.75` becomes `processed`.
5. Lower confidence becomes `needs_review`.
6. A supplier rejected without fallback always becomes `needs_review`.

**User-visible result:** Confidence and attention reasons appear in tables; the document is routed to Processed / Pending or Needs Attention.

## 9. Review and Correction

**Trigger:** The user opens Review from a row/context menu or double-click behavior.

**Main sources:** `app/ui/review_dialog.py:ReviewDialog`, `app/services/correction_map_service.py`, `app/services/learning_service.py`.

1. A modal dialog loads the document, effective values, current status, and raw extracted text.
2. The user edits supplier, date, document number, total, and other displayed fields, or selects a status.
3. Saving collects non-empty corrections into `corrected_data`.
4. The dialog records manual-correction state and writes the document through `DocumentStore`.
5. Field changes are appended to the corrections log and may update correction mappings or learned rules.
6. The dialog closes or stays available according to the selected action; the main table refreshes after a saved change.

**Persistence effects:** Document JSON, corrections log, correction map, learned rules, and supplier rules may change.

**Failure/validation path:** Numeric conversion failure is handled weakly, date is free text, and empty values do not cleanly override an extracted value because `Document.effective()` falls back for `None` or empty string.

**User-visible result:** Corrected effective data appears in tables and later export.

## 10. Approval

**Trigger:** The user selects Approve in the Review dialog.

**Main source:** `app/ui/review_dialog.py:ReviewDialog._approve()`.

1. The dialog collects and saves current corrections.
2. It assigns status `approved`.
3. The updated document is persisted.
4. The record becomes eligible for Excel export.

**Alternative path:** Direct status selection can assign `approved` without a centrally enforced transition sequence.

**User-visible result:** The record moves into the approved subset of Processed / Pending until exported.

## 11. Excel Export

**Trigger:** The user selects Export.

**Main sources:** `MainWindow._on_export()`, `app/ui/workers.py:ExportWorker`, `app/writers/excel_writer.py:export_documents()`.

1. `ExportWorker` selects all records with status `approved`.
2. If none exist, it returns a no-records result.
3. `export_documents()` reads or creates the configured workbook and writes document rows.
4. Workbook formatting is applied with openpyxl.
5. Exported documents are assigned status `exported` and `exported_to_excel = true`.
6. Updated records are persisted with `upsert_many()`.

**Failure path:** Writer errors reach the worker error signal. An unreadable existing workbook may be treated as empty; see [Current State](CURRENT_STATE.md#excel-recovery).

**User-visible result:** An export-result dialog reports record count and path; exported records appear in History.

## 12. Automatic Skipped Classification

**Trigger:** Classification returns a type listed in `EXCLUDED_DOCUMENT_TYPES`.

**Main source:** `ProcessingService._process_one()`.

1. The document is assigned `skipped`.
2. The detected type is stored in `extracted_data`.
3. A reason is stored in `error_message`.
4. The record is persisted immediately.
5. The local PDF and extracted text are retained.

**Next actions:** The user can review, retry, manually change status, or explicitly mark the document irrelevant.

**User-visible result:** The record appears in the skipped subset of Needs Attention.

## 13. Confirmed Irrelevant / Exclusion

**Trigger:** The user selects Mark Irrelevant and confirms.

**Main sources:** `app/ui/confirm_irrelevant_dialog.py`, `ReviewDialog._confirm_exclusion()`, `MainWindow._on_mark_irrelevant()`, `app/services/exclusion_service.py`.

1. A confirmation dialog warns the user.
2. `confirm_irrelevant()` writes the Drive ID and metadata to the exclusion registry.
3. The persisted local PDF path is deleted if possible.
4. The caller assigns `confirmed_irrelevant` and `confirmed_irrelevant_at`, then persists the document.
5. Future Drive scans skip that Drive ID.

**Persistence effects:** Exclusion registry and document record change; source PDF is deleted. Extracted text is not necessarily deleted.

**Failure path:** Local PDF deletion logs and suppresses errors. Registry read errors can fall back to an empty registry.

**User-visible result:** The record moves to Irrelevant. Legacy records may retain status `excluded`.

## 14. Duplicate Detection

**Trigger:** Processing assigns its initial `processed` or `needs_review` status.

**Main source:** `app/services/duplicate_detection_service.py:detect_and_mark_duplicate()`.

1. The candidate must have a supplier.
2. Existing records are limited to `processed`, `needs_review`, `approved`, or `exported`.
3. An exact suspicion matches normalized supplier and invoice number, with matching dates when both are available.
4. A high suspicion applies when invoice number is absent and normalized supplier, date, and amount match.
5. The document retains its primary workflow status but gains duplicate flags and a reference to the existing record's Drive ID.

**Persistence effects:** `is_duplicate_suspected`, `duplicate_confidence`, and `suspected_duplicate_of` are stored.

**User-visible result:** The record is routed into Needs Attention and receives a duplicate reason.

## 15. Duplicate Resolution

**Trigger:** The user uses a duplicate context-menu action.

**Main sources:** `MainWindow._on_confirm_duplicate()`, `MainWindow._on_not_duplicate()`.

1. **Confirm duplicate:** after confirmation, the document follows the confirmed-irrelevant/exclusion flow and is removed from future Drive scans.
2. **Not a duplicate:** the duplicate flag, confidence, and references are cleared and the record is persisted.

**User-visible result:** The attention reason is removed on dismissal, or the record moves to Irrelevant on confirmation.

There is no built-in side-by-side duplicate comparison.

## 16. Single Retry

**Trigger:** The user selects retry for one record.

**Main sources:** `MainWindow._on_retry()`, `RetryWorker`, `ProcessingService.retry()`.

1. The selected Drive ID is resolved to a document.
2. `retry()` rejects only `excluded` and `confirmed_irrelevant`.
3. It clears the prior error, temporarily assigns `new`, and reruns the full processing pipeline.
4. The existing local PDF is reused if it is still present.
5. The new result is persisted and the UI refreshes.

**Failure path:** Worker or processing errors are surfaced; processing itself can assign `failed`.

## 17. Bulk Reprocessing

**Trigger:** The user multi-selects records and chooses bulk reprocessing.

**Main sources:** `MainWindow._on_bulk_process()`, `BulkProcessWorker`.

1. The UI filters selected records and blocks `approved`, `exported`, `excluded`, and `confirmed_irrelevant`.
2. The worker authenticates once and iterates selected Drive IDs.
3. Each allowed record calls `ProcessingService.retry()`.
4. Results are counted as success, needs-review, failed, or skipped.
5. Per-record changes are persisted by processing; the summary is shown at completion.

**Failure path:** A missing local record counts as skipped. Per-record exceptions assign `failed` and continue; fatal worker errors stop the operation.

## 18. Legacy CLI

**Trigger:** The user runs `python -m app.main`.

**Main sources:** `app/main.py`, `app/models/record.py`, `app/state/state_manager.py`, `app/utils/pdf_downloader.py`.

1. The CLI authenticates and recursively scans Drive.
2. `StateManager` filters new/changed records using its separate state JSON.
3. PDFs are downloaded.
4. Each PDF is extracted, classified, and parsed into legacy `InvoiceRecord`.
5. Legacy statuses include values such as `processed`, `parse_failed`, skipped variants, and unrecognized type.
6. Processed records are appended directly to Excel.
7. Legacy scan state is saved.

**Key difference:** This flow does not use the active desktop `DocumentStore`, review/approval lifecycle, or complete desktop status model. It is current repository code but marked legacy and under reconsideration.

## Workflow Inconsistencies

These are confirmed current issues; they are not proposed behavior.

### Retry Rules

Single-item retry in `ProcessingService.retry()` blocks only permanent irrelevant/excluded states. Bulk reprocessing in `MainWindow._on_bulk_process()` additionally blocks approved and exported records. Eligibility is therefore not identical.

### Manual Status Editing

`ReviewDialog` exposes status selection without a centralized transition validator. A user can assign a status that bypasses the intended processing, review, approval, and export sequence.

### Skipped Summary

`ProcessingService.process_new()` increments its `needs_review` summary count for every non-`processed` result, including `skipped`. `BulkProcessWorker` has a separate skipped count, so summary semantics differ.

### Irrelevant Terminology

Some confirmation wording refers to moving a record to history, while the implemented status/filter routing moves it to the Irrelevant view.
