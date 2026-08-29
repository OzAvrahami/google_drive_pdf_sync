# Panda Architecture

This document describes the implemented architecture for Panda **2.0.0**.

## System Context

Panda is a local PySide6 desktop application. Google Drive supplies remote PDFs;
Panda downloads and processes them locally, persists document state in JSON,
and exports approved records to Excel.

```text
Google Drive
    |
    v
Drive sync and safe download
    |
    v
ProcessingService
    |-- native PDF text extraction
    |-- RTL normalization
    |-- classification and text parsing
    |-- optional positional supplier resolution
    |-- supplier validation and confidence
    |-- duplicate detection
    v
DocumentStore (local JSON)
    |
    +--> Panda 2.0 queues and document workspace
    +--> approval / irrelevant / duplicate workflows
    +--> Excel export and history
```

## Entry Points

- `run.py --panda2` starts the Panda 2.0 shell.
- `run.py` starts the legacy desktop shell.
- `python -m app.main` runs the older CLI pipeline.
- `scripts/` contains local diagnostics, private-corpus tooling, and visual
  development harnesses.

`app/version.py` is the authoritative application-release version. Qt receives
that value through `QApplication.setApplicationVersion()`.

## Presentation Layer

`app/ui/shell.py` composes the Panda 2.0 application shell:

- `app/ui/routes.py` is the primary-route definition source.
- `app/ui/views/` implements Overview, document queues, and Ready.
- `app/ui/workspace/` implements the document review workspace and shared PDF
  source preview.
- `app/ui/tasks/` presents current-session background work through the Task Dock
  and Task Center.
- `app/ui/benchmark/` implements the developer-only PDF Benchmark workspace.
- `app/ui/components/` and `app/ui/theme/` provide reusable controls, icons,
  typography, tokens, and stylesheet boundaries.

Typed Qt models and proxy models keep queue membership, presentation, filtering,
and stable document selection separate from widgets.

## Application and Workflow Services

- `app/application/task_manager.py` owns the in-memory task lifecycle and
  read/write scheduling contract.
- Worker adapters and operational controllers bridge existing QThread workers to
  the task model.
- Workspace approval, duplicate, irrelevant, and export services contain the
  guarded mutations used by the UI.
- `app/services/processing_service.py` owns the production document-processing
  sequence.
- `app/services/document_store.py` owns operational persistence.
- Drive, exclusion, learning, duplicate, export, and correction-map services
  remain focused local boundaries.

## PDF Parsing Boundary

The production parser is layered:

1. `app/parsers/pdf_parser.py` opens the PDF and extracts page text with
   pdfplumber.
2. `app/utils/text_helpers.py` performs production RTL normalization.
3. `app/parsers/invoice_parser.py` classifies and extracts text-based fields.
4. `app/parsers/pdf_layout.py` performs optional word-coordinate analysis only
   for a strict text-detected customer/addressee ambiguity.
5. `app/parsers/supplier_validator.py` validates the final supplier candidate.
6. `ProcessingService` calculates the existing confidence and status.

Text parsing remains authoritative by default. Layout analysis cannot change
classification, date, number, amount, confidence weights, or processing
thresholds. Its cheap preflight limits `extract_words()` to the verified
ambiguity family.

OCR, cloud parsing, and AI/LLM parsing are not part of this architecture.

## Persistence

`DocumentStore` keeps documents indexed by Drive file ID in memory and persists
them to a local JSON object containing a schema version and document array.
The current schema version is `CURRENT_STORE_VERSION = 2`.

Loading fails closed for malformed JSON, invalid structure, unsupported schema
versions, invalid documents, or duplicate Drive IDs. Writes use a temporary file
followed by replacement. Schema version `2` is not the application version and
does not imply a migration framework.

Other runtime JSON/files contain corrections, learned rules, exclusions,
downloads, extracted text, and export artifacts.

## Developer Corpus Boundary

`app/services/pdf_corpus_service.py` is shared by the desktop Benchmark UI and
CLI review tooling. It owns manifest inventory, SHA identity, current parser
analysis, Ground Truth comparison, filters/sorting, review updates, and atomic
manifest persistence.

Real corpus PDFs, the real manifest, and generated benchmark/layout artifacts
are ignored. Tracked code includes only synthetic fixtures/templates and tests
that skip explicitly when a private real fixture is unavailable.

## Export

Approved documents are exported through the existing Excel writer and export
services. Export tasks are serialized through the task-access contract, and
exported documents appear in History.

## Remaining Architecture Boundaries

- Panda 2.0 and the legacy shell still share the repository and operational
  model; retirement or default-startup changes remain explicit decisions.
- Local JSON persistence has strict version validation but no migrations.
- Packaging, installer design, CI, backup/recovery, and OCR remain outside the
  current implementation.
- The application remains intentionally local and single-user.
