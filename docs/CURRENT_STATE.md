# Panda - Current State

This document describes the implemented Panda 2.0 application at release
version **2.0.0**. Future work is tracked separately in the
[Roadmap](ROADMAP.md).

## Product Status

Panda is an active, internal, single-user desktop application for Hebrew-first
accounting-document processing. It is implemented with Python and PySide6/Qt,
uses Google Drive as its remote PDF source, and stores operational state and
artifacts on the local filesystem.

The Panda 2.0 shell currently starts with:

```powershell
python run.py --panda2
```

The legacy desktop shell remains the no-flag startup path until startup
consolidation is decided. The older CLI also remains available. These legacy
paths do not change Panda 2.0's formal application version.

## Panda 2.0 Workspace

The implemented shell provides:

- an operational Overview;
- Inbox, Needs Attention, Ready, Irrelevant, and History queues;
- queue counts, search, filters, stable selection, and status presentation;
- an integrated document workspace with source PDF preview and page navigation;
- editable extracted fields with unsaved-change protection;
- previous/next document navigation;
- save, approval, duplicate-resolution, and irrelevant-document actions;
- selected/batch approval and Excel-export actions in Ready; and
- background task feedback through the Task Dock and Task Center.

The application uses a central queue policy to map each document to one primary
navigation destination. Duplicate suspicion is surfaced through Needs Attention.

## Processing Pipeline

The implemented production path is:

1. Discover PDF files recursively below the configured Google Drive folder.
2. Download each source into a contained local path.
3. Extract native text with pdfplumber.
4. Normalize Hebrew/RTL text while preserving meaningful mixed LTR tokens.
5. Classify document type and skip excluded receipt/combined-receipt policies.
6. Parse supplier, document date, document number, and payable amount.
7. Optionally apply the narrowly gated positional supplier resolver for the
   validated two-column customer/issuer ambiguity.
8. Validate the supplier and calculate confidence.
9. Route the record to processed, needs-review, skipped, or failed state.
10. Detect duplicate candidates and persist the result.

The parser is designed for native digital PDFs. OCR is not implemented. An
image-only or otherwise non-native PDF remains a needs-review document rather
than being presented as a native-parser regression.

## Native PDF Accuracy State

Panda includes tracked synthetic regression coverage and optional private
real-PDF regressions. The private corpus itself is not part of Git.

At 2.0.0 release preparation, local/private verification reported:

- 42 reviewed unique identities;
- 42/42 correct supplier, date, document number, and amount fields;
- 112 unique local identities, including 111 native digital PDFs and 1
  non-native PDF;
- 98 processed and 13 skipped by policy among native documents; and
- the non-native document remaining in needs-review without OCR.

These figures are local human-verification evidence, not clean-clone or CI data.
Operational processing status, field presence, reviewed accuracy, and fully
correct documents remain separate measurements.

## Developer PDF Benchmark

The developer-only PDF Benchmark is available from the Panda 2.0 secondary
tools entry. It reuses the production extraction/parser and existing PDF preview
while providing:

- SHA-256-based corpus identity and duplicate handling;
- source-system and native-text diagnostics;
- reviewed/unreviewed, mismatch, source, status, and confidence filters;
- editable human Ground Truth fields;
- Everything Correct and Save & Next workflows;
- reviewed progress and field/fully-correct accuracy; and
- atomic manifest persistence with actionable locked-file errors.

The same corpus and review behavior is shared with the CLI through
`app/services/pdf_corpus_service.py`.

## Persistence and Export

`DocumentStore` is the operational source of truth. It writes schema version
`CURRENT_STORE_VERSION = 2`, validates the top-level shape and exact supported
schema version while loading, rejects corrupt/unsupported stores, and writes
atomically through a temporary file and replacement.

Application release version `2.0.0` and document-store schema version `2` are
independent contracts. No automatic store migration framework exists.

Other local state includes downloaded PDFs, extracted text, correction maps,
learned supplier rules, exclusion data, and generated Excel workbooks. Runtime
and private corpus data are intentionally excluded from Git.

## Current Boundaries and Limitations

- Panda is local and single-user; there is no server, database, or web client.
- There is no OCR path for scanned/image-only PDFs.
- There is no packaged installer or binary distribution.
- The private corpus and Ground Truth are unavailable in clean clones and CI.
- The legacy shell and CLI still coexist with Panda 2.0.
- Document-store version compatibility is validated, but migrations are not
  implemented.
- Backup/recovery policy and broader release automation remain future work.
- No document content is sent to AI/LLM parsing or telemetry services.

See [Architecture](ARCHITECTURE.md), [Product Flows](PRODUCT_FLOWS.md), and
[Testing](TESTING.md) for the current implementation boundaries.
