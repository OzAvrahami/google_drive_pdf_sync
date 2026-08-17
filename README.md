# Panda

Panda is a local, Hebrew-first desktop application for accounting-document processing. The current UI still uses the Hebrew product label `כלי חשבונאות` in places; Panda branding has not yet been fully migrated into the application.

This repository documents the current implementation separately from known issues and proposed Panda 2.0 work. Start with [Current State](docs/CURRENT_STATE.md), [Architecture](docs/ARCHITECTURE.md), and the [Roadmap](docs/ROADMAP.md).

## Product Overview

The implemented desktop workflow:

- recursively discovers PDF files in a configured Google Drive folder;
- downloads source PDFs to local storage and extracts text;
- classifies accounting documents and extracts invoice fields;
- validates suppliers and computes confidence;
- routes documents through review, correction, approval, duplicate-resolution, irrelevant/excluded, export, and local-history workflows;
- learns from selected user corrections; and
- exports approved records to Excel.

Panda runs locally. It has no application server or database.

## Technology

- Python
- PySide6 / Qt
- Google Drive API
- pdfplumber
- pandas
- openpyxl
- local JSON and filesystem persistence

Explicit dependency versions are recorded in `requirements.txt`. See [Architecture](docs/ARCHITECTURE.md) for component responsibilities.

## Entry Points

### Current Desktop App

`run.py` is the active application entry point:

```powershell
python run.py
```

### Legacy CLI

`app/main.py` provides an older command-line pipeline:

```powershell
python -m app.main
```

The CLI uses legacy models and state persistence that overlap with the desktop architecture. It remains present today but is under reconsideration for Panda 2.0.

## Setup

Install the repository's declared dependencies:

```powershell
pip install -r requirements.txt
```

Create a local `.env` from the safe `.env.example` template and configure these names:

```text
GOOGLE_DRIVE_PARENT_FOLDER_ID
GOOGLE_SERVICE_ACCOUNT_FILE
```

`.env` and real Google service-account credential files are local-only and must never be committed. Do not place real values in documentation or example files.

## Running

Desktop application:

```powershell
python run.py
```

Legacy CLI:

```powershell
python -m app.main
```

There is currently no packaged installer or formal release artifact.

## Tests

The test suite uses pytest. Current coverage, gaps, and the audit environment limitation are documented in [Panda Testing](docs/TESTING.md).

## Documentation

- [Current State](docs/CURRENT_STATE.md) — authoritative snapshot of implemented behavior and confirmed limitations
- [Architecture](docs/ARCHITECTURE.md) — current components, boundaries, and architectural questions
- [Product Flows](docs/PRODUCT_FLOWS.md) — end-to-end implemented workflows
- [Data Model](docs/DATA_MODEL.md) — document entity, statuses, and runtime persistence
- [UI Inventory](docs/UI_INVENTORY.md) — current screens, controls, states, and designer constraints
- [Security and Privacy](docs/SECURITY_AND_PRIVACY.md) — sensitive-data boundaries and known findings
- [Operations](docs/OPERATIONS.md) — local configuration, runtime files, backup, and recovery limits
- [Testing](docs/TESTING.md) — current verification baseline and planned quality work
- [Roadmap](docs/ROADMAP.md) — proposed path toward Panda 2.0
- [Decision Records](docs/decisions/README.md) — lightweight ADR process for future decisions
- [Changelog](CHANGELOG.md) — repository-maintenance history
