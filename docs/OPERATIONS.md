# Panda Operations

Panda 2.0.0 is a source-only local desktop application. It does not currently
provide an installer, managed deployment, automatic backup, or restore command.

## Configuration

Create a local `.env` from `.env.example` and configure:

```text
GOOGLE_DRIVE_PARENT_FOLDER_ID
GOOGLE_SERVICE_ACCOUNT_FILE
```

The Drive folder must be accessible to the service account. Panda uses a
read-only Drive scope. `.env` and the credential JSON are ignored and must remain
local.

## Running

Panda 2.0 shell:

```powershell
python run.py --panda2
```

Legacy desktop and CLI compatibility paths:

```powershell
python run.py
python -m app.main
```

The legacy paths are not equivalent to the Panda 2.0 presentation contract.

## Runtime Locations

`app/config.py` defines repository-relative local paths:

| Path | Purpose |
| --- | --- |
| `data/documents.json` | Versioned operational document store |
| `data/downloads/` | Contained downloaded PDF hierarchy |
| `data/text/` | Extracted text by Drive ID |
| `data/corrections_log.json` | Correction history |
| `data/correction_map.json` | Correction substitutions |
| `data/learned_rules.json` | Learned parser rules |
| `data/supplier_rules.json` | Supplier validation rules |
| `data/excluded_files.json` | Drive-ID exclusion registry |
| `data/output/invoices.xlsx` | Default Excel export |
| `data/state/sync_state.json` | Legacy CLI state |

These paths contain operational data and are ignored. Moving them to a
platform-managed application-data location remains future work.

## Private PDF Corpus

The developer corpus lives below `tests/fixtures/pdf/` but is local-only. New
documents enter through `_incoming/`; the batch diagnostic can register and
organize them by evidence-based source detection. Human review writes the local
manifest atomically.

See [PDF Corpus Workflow](pdf-corpus-workflow.md) for commands and privacy rules.

## Backup

Before application, parser, persistence, or runtime-layout changes, protect a
copy of:

- the complete `data/` tree;
- `.env` and the service-account credential;
- workbooks stored outside the default path; and
- the private PDF corpus and reviewed manifest when needed for development.

Backups remain sensitive and must not be added to Git. Verify a backup before
performing migration work.

## Recovery and Compatibility

`DocumentStore` accepts only schema version `2` and fails closed for malformed,
invalid, duplicate-ID, or unsupported-version data. It does not silently replace
an invalid existing store with an empty one. Writes use temporary-file
replacement.

Panda still has no schema migration tool, point-in-time recovery, transaction
log, or automatic rollback. Preserve the affected files and stop writing if
corruption is suspected. Application version `2.0.0` does not change the store
schema version automatically.

## Testing and Release Verification

```powershell
python -B -m pytest
python -B scripts/diagnose_pdf_batch.py "tests/fixtures/pdf"
```

The batch command requires the private local corpus for its full reviewed
accuracy result. A clean clone retains synthetic coverage and skips unavailable
private-real-PDF tests explicitly.

## Logs and Troubleshooting

`run.py` logs to the process console. Treat console output as potentially
sensitive because it may include filenames, paths, field values, and exception
details.

Common failures include missing dependencies/configuration, inaccessible Drive
folders or credentials, network/API errors, unreadable source PDFs, invalid
runtime-store data, locked manifests/workbooks, and inaccessible output paths.
