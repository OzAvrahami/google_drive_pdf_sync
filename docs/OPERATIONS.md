# Panda Operations

This document describes the current repository-local desktop installation. Panda does not currently provide an installer, managed deployment, automated backup, or restore command.

## Local Configuration

`app/config.py` loads a repository-root `.env`. Supported environment-variable names are:

```text
GOOGLE_DRIVE_PARENT_FOLDER_ID
GOOGLE_SERVICE_ACCOUNT_FILE
```

- `GOOGLE_DRIVE_PARENT_FOLDER_ID` identifies the remote parent hierarchy to scan.
- `GOOGLE_SERVICE_ACCOUNT_FILE` points to a local service-account JSON file. A relative path is resolved against the repository root.

`.env` and real credential files are local-only and ignored. Use `.env.example` as a names-only template; never commit real values.

## Google Drive Requirements

- A Google Cloud service account with access to the intended Drive folder.
- A local service-account JSON credential file.
- The Drive API dependencies declared in `requirements.txt`.
- Network access to Google Drive APIs.
- The configured parent folder shared with or otherwise accessible to the service account.

`app/clients/drive_client.py:get_drive_service()` authenticates and uses a read-only Drive scope. Panda recursively lists folders and PDF MIME-type entries beneath the configured parent.

## Running the Current Application

From the repository root:

```powershell
python run.py
```

The legacy CLI remains available separately:

```powershell
python -m app.main
```

It uses a different state model and should not be treated as equivalent to the desktop workflow. See [Architecture](ARCHITECTURE.md#legacy-cli).

## Runtime Directories

`app/config.py` defines all active paths relative to the repository root:

| Current path | Purpose |
| --- | --- |
| `data/documents.json` | Active desktop document records. |
| `data/downloads/` | Downloaded PDFs arranged from Drive-derived folder/file names. |
| `data/text/` | Extracted text files named by Drive ID. |
| `data/corrections_log.json` | Manual correction history. |
| `data/correction_map.json` | Global correction substitutions. |
| `data/learned_rules.json` | Learned parser rules. |
| `data/supplier_rules.json` | Learned supplier validation rules. |
| `data/excluded_files.json` | Permanent Drive-ID exclusions. |
| `data/output/invoices.xlsx` | Current Excel export. |
| `data/state/sync_state.json` | Legacy CLI synchronization state. |
| `data/processed/` | Configured local runtime directory; not the active document-record store. |
| `data/failed/` | Configured local runtime directory; failures are primarily represented in document JSON. |

`data/settings.json` is also defined, but there is no formal settings UI in the active application.

These locations are current implementation facts. Moving them to a platform application-data location is an unresolved Panda 2.0 architecture decision.

## Backup

Before significant application, parser, persistence, or runtime-layout changes, make a protected copy of:

- the complete `data/` tree, including downloaded PDFs, extracted text, JSON stores, exclusion state, legacy state, and generated workbook;
- the local `.env`;
- the local Google service-account credential file;
- any Excel workbook stored outside the configured default location.

Backups can contain sensitive accounting and credential material. Store them with appropriate access control and do not add them to Git.

The current application does **not** create these backups automatically. A backup should be verified independently before migration work starts.

## Recovery Limitations

The current implementation has no:

- formal backup/restore tooling;
- transaction log or audit-event log;
- schema migration tooling;
- point-in-time recovery;
- automatic rollback;
- validation that a store version is compatible before loading;
- safe recovery workflow for corrupt JSON or an unreadable workbook.

Some readers return empty/default state after an error. Operators should stop and preserve the affected files rather than continue writing when corruption is suspected.

## Logs and Troubleshooting

`run.py` configures INFO logging to the process console. Worker/service exceptions are logged and generally surfaced through UI dialogs; there is no dedicated log file configured by the application. Console output may contain sensitive filenames, paths, values, and exception details.

Common setup failures include:

- Python or dependencies unavailable;
- missing/empty Drive folder configuration;
- missing, unreadable, or unauthorized service-account file;
- Drive folder not shared with the service account;
- network/API failure;
- inaccessible runtime directories or output workbook;
- source PDF unavailable or unreadable.

## Before Panda 2.0 Persistence Changes

Operational data must be backed up before any future migration that changes persistence schema, JSON structure, runtime paths, exclusion behavior, or workbook handling. A migration plan should include validation, a dry run against a copy, rollback instructions, and regression checks. Current risks are documented in [Security and Privacy](SECURITY_AND_PRIVACY.md) and planned foundation work in the [Roadmap](ROADMAP.md).
