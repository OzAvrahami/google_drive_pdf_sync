# Panda

Panda is a local, Hebrew-first desktop application for reviewing and processing
accounting documents from Google Drive.

| Project metadata | Value |
| --- | --- |
| Project | Panda |
| Version | **2.0.0** |
| Status | **Active — internal desktop application** |
| Distribution | Source-only; no packaged installer |
| Latest release | [GitHub Releases/latest](https://github.com/OzAvrahami/google_drive_pdf_sync/releases/latest) |

The authoritative application version is defined in `app/version.py`. The
planned `v2.0.0` tag and matching GitHub Release complete the external release
evidence; they are not created by release-preparation changes.

## What Panda Does

Panda discovers PDFs below a configured Google Drive folder, downloads them to
local storage, extracts and normalizes native text, classifies accounting
documents, parses structured invoice fields, validates suppliers, and routes
records through review, approval, duplicate, irrelevant, export, and history
workflows.

The Panda 2.0 desktop experience provides:

- Overview and queue-based navigation for Inbox, Needs Attention, Ready,
  Irrelevant, and History;
- an integrated document workspace with PDF preview, field editing, navigation,
  approval, duplicate resolution, and irrelevant-document actions;
- background task feedback through the Task Dock and Task Center; and
- a developer-only PDF Benchmark workspace for local human Ground Truth review.

Panda remains local and single-user. It has no application server or database,
and no document content is sent to an AI or cloud parsing service.

## Technology

- Python and PySide6 / Qt
- Google Drive API
- pdfplumber
- pandas and openpyxl
- local JSON and filesystem persistence

Pinned dependencies are listed in `requirements.txt` and
`requirements-dev.txt`.

## Setup

```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Create `.env` from `.env.example` and configure:

```text
GOOGLE_DRIVE_PARENT_FOLDER_ID
GOOGLE_SERVICE_ACCOUNT_FILE
```

Real environment values and credentials are local-only and must not be
committed.

## Running

Panda 2.0 desktop shell:

```powershell
python run.py --panda2
```

The legacy desktop shell remains available while startup consolidation is still
an explicit future decision:

```powershell
python run.py
```

The older CLI pipeline remains available for diagnostics and compatibility:

```powershell
python -m app.main
```

There is currently no packaged installer or binary release artifact.

## Testing

Canonical command:

```powershell
python -B -m pytest
```

Release-preparation result for 2.0.0:

```text
1043 passed
0 failed
0 skipped
```

Real invoice PDFs, their manifest, and generated benchmark artifacts are private
and ignored by Git. When those fixtures exist locally, optional real-PDF
regressions run. In a clean clone, they skip explicitly while synthetic and unit
coverage remains active.

Developers can add private PDFs under `tests/fixtures/pdf/_incoming/` and use:

```powershell
python -B scripts/diagnose_pdf_batch.py "tests/fixtures/pdf" --new-only
python -B scripts/diagnose_pdf_batch.py "tests/fixtures/pdf" --organize --dry-run
python -B scripts/review_pdf_corpus.py "tests/fixtures/pdf"
python -B scripts/diagnose_pdf_batch.py "tests/fixtures/pdf"
```

Operational parser status and human-reviewed accuracy are intentionally reported
as separate measurements. See [PDF Corpus Workflow](docs/pdf-corpus-workflow.md).

## Documentation

- [Current State](docs/CURRENT_STATE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Product Flows](docs/PRODUCT_FLOWS.md)
- [Data Model](docs/DATA_MODEL.md)
- [UI Inventory](docs/UI_INVENTORY.md)
- [Security and Privacy](docs/SECURITY_AND_PRIVACY.md)
- [Operations](docs/OPERATIONS.md)
- [Testing](docs/TESTING.md)
- [Roadmap](docs/ROADMAP.md)
- [Decision Records](docs/decisions/README.md)
- [Changelog](CHANGELOG.md)
