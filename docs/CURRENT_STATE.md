# Panda — Current State

This document is the authoritative factual snapshot of the implemented Panda application at the start of Panda 2.0 planning. Planned work is kept in the [Roadmap](ROADMAP.md); it is not described here as current behavior.

## Product Status

Panda is currently a local, single-user desktop accounting-document processing application. Its primary UI is Hebrew-first and application-wide right-to-left (RTL), implemented with Python and PySide6/Qt.

The active execution model is:

1. The user starts `run.py`.
2. Panda reads local configuration and JSON persistence.
3. Explicit user actions start background Qt workers for Drive scanning, document processing, retries, or export.
4. Google Drive is used as a remote PDF source through a service account.
5. All application records and artifacts remain on the local filesystem.
6. Approved data is written to an Excel workbook.

There is no application server, database, multi-user service, or web client. See [Product Flows](PRODUCT_FLOWS.md) for the traced workflows and [Architecture](ARCHITECTURE.md) for component boundaries.

## Current Capabilities

The current implementation supports:

- recursive discovery of PDFs below a configured Google Drive parent folder;
- filtering of entries recorded in the local exclusion registry;
- local PDF download;
- PDF text extraction with pdfplumber and RTL-text normalization;
- local storage of extracted text;
- document classification, including automatically skipped document types;
- invoice field parsing for document type, supplier, date, document number, subtotal, VAT, total, and description;
- supplier matching, validation, learned supplier rules, and fallbacks;
- confidence scoring and routing to automatic processing or manual attention;
- review and correction of extracted fields and status;
- correction logging, correction mapping, and learned parsing rules;
- duplicate suspicion using exact and high-confidence comparisons;
- manual duplicate confirmation or dismissal;
- approval;
- confirmed-irrelevant handling and an exclusion registry;
- retry of a single document and bulk reprocessing;
- Excel export of approved records;
- local exported-document history; and
- background execution through Qt worker threads with progress reporting.

## Current Views

The main shell in `app/ui/main_window.py` contains these views:

- **Dashboard** — summary cards and recent-document presentation.
- **New Documents** — records awaiting processing.
- **Needs Attention** — review, failure, skipped, and duplicate-focused queues with filters.
- **Processed / Pending** — processed, corrected, and approved records with filters.
- **Irrelevant** — confirmed-irrelevant and legacy-excluded records.
- **History** — exported records.

Supporting dialogs include:

- **Review / Correction Dialog** in `app/ui/review_dialog.py`;
- **Progress Dialog** in `app/ui/progress_dialog.py`;
- confirmations for irrelevant classification and duplicate resolution; and
- export-result, informational, warning, and error message boxes.

The detailed inventory is in [UI Inventory](UI_INVENTORY.md).

## Current Persistence

Panda stores data only in local JSON files and filesystem artifacts:

- document records;
- downloaded source PDFs;
- extracted text files;
- correction logs and mappings;
- learned parsing and supplier rules;
- an excluded-file registry;
- legacy CLI state;
- and generated Excel workbooks.

`app/services/document_store.py` owns the active document JSON store. There is no relational database, server-side persistence, transaction log, or migration framework. Runtime files are operational data and are intentionally excluded from Git. See [Data Model](DATA_MODEL.md) and [Operations](OPERATIONS.md).

## Current Dataset Scale

The repository audit examined Panda against an active local working dataset containing hundreds of document records. No operational filenames, supplier identities, invoice values, amounts, or document contents are reproduced in this documentation.

## Known Product Limitations

These are confirmed characteristics of the current implementation, not Panda 2.0 features:

- Review is modal and one document at a time.
- Source PDFs open in an external application, requiring context switching.
- There is no batch-approval action.
- Duplicate resolution has no integrated side-by-side comparison.
- The progress dialog cannot be cancelled.
- Searching and refreshing rebuilds the complete visible table.
- Numeric amounts and confidence values are displayed and sorted as formatted strings.
- There is no formal settings UI.
- There is no OCR fallback for image-only PDFs.
- There is no packaging or installer.
- There is no application-versioning system.
- The legacy CLI overlaps with the active architecture.
- There is no dedicated application keyboard workflow.

## Known Reliability / Correctness Issues

The following findings are documented for later remediation. No fix is implied.

### Changed Drive File Handling

`app/services/drive_sync_service.py` can detect a changed Drive file and requeue its record. During processing, `app/services/processing_service.py` may reuse an already-present local PDF instead of downloading the changed remote bytes. The record can therefore be reprocessed from stale local content.

### Workflow State Enforcement

Workflow transitions are distributed among `app/ui/main_window.py`, `app/ui/review_dialog.py`, `app/ui/workers.py`, `app/services/processing_service.py`, and related services. No single component validates a central transition graph, and manual status editing can bypass intended sequences.

### Document Store Recovery

`DocumentStore` in `app/services/document_store.py` catches failures while loading the document JSON and can continue with an empty in-memory store. A subsequent save could overwrite the only persisted record set, creating a data-loss risk.

### Excel Recovery

`app/writers/excel_writer.py` can treat an unreadable existing workbook as an empty workbook and continue. A later write can replace data that was present but could not be read.

### Schema Evolution

The document store writes a version field, but `DocumentStore` does not validate it or apply formal migrations. Compatibility across future schema changes is not guaranteed.

## Current, Known, and Planned Boundaries

- **Current implementation:** everything under Product Status, Current Capabilities, Views, and Persistence above.
- **Known issues and debt:** the limitations and reliability findings above.
- **Planned or proposed Panda 2.0 direction:** only the items explicitly marked planned or open in the [Roadmap](ROADMAP.md) and [Decision Records](decisions/README.md).
