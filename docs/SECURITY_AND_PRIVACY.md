# Panda Security and Privacy

This document records current data boundaries, completed repository hygiene, and known findings. It is not a claim of a completed security hardening program.

## Local Sensitive Data

Panda may store sensitive operational and accounting information locally, including:

- source PDFs;
- extracted document text;
- invoice metadata and parsed values;
- user corrections and learned mappings;
- Google Drive file identifiers and folder paths;
- generated Excel exports;
- processing errors and log messages.

These artifacts must be treated as operational data, not source code. This documentation intentionally contains no real supplier names, document filenames, invoice values, Drive IDs, accounting records, credentials, or extracted content.

## Repository Hygiene

The pre-Panda-2.0 hygiene pass intentionally excludes these categories from current Git tracking:

- runtime data and local state;
- downloaded PDFs and extracted text;
- generated Excel and other output/test artifacts;
- `.env`;
- real service-account credentials;
- Python bytecode, `__pycache__`, and pytest caches;
- local development-tool settings.

Safe templates such as `.env.example` may remain tracked when they contain names/placeholders only. Ignore rules reduce future exposure risk but do not erase historical commits.

## Google Service Account

Panda authenticates to Google Drive using a local Google service-account JSON file configured by `GOOGLE_SERVICE_ACCOUNT_FILE`. The Drive API client requests read-only access.

Real credential files must remain local and must never be committed or copied into documentation.

A real service-account credential was historically committed before repository hygiene was introduced. Rotation or revocation of that credential remains a known deferred manual security action. It is **not complete**, and this documentation does not claim otherwise. The deferred action does not block Panda 2.0 documentation or design planning.

## Known Security / Reliability Findings

These are current findings, not completed fixes.

### Download Path Boundary

`app/utils/pdf_downloader.py:resolve_local_path()` constructs local paths from Drive-derived folder and filename values. The sanitization does not establish and verify a resolved-path containment boundary, so crafted `..`-style path components could escape the intended downloads directory.

### Local Delete Boundary

`app/services/exclusion_service.py:_delete_local_pdf()` trusts `Document.local_path` loaded from persistence and calls `Path.unlink()` without confirming that the resolved target remains inside Panda's downloads directory. A corrupted or malicious store entry could target an unintended local file.

### Excel Formula Injection

`app/writers/excel_writer.py` writes parsed and user-corrected strings into spreadsheet cells without neutralizing formula-leading characters. A document-derived value beginning with a formula prefix could be interpreted by spreadsheet software when the workbook opens.

### Logs

Application logging and progress messages can include filenames, folder paths, extracted field values, exception text, and local paths. Console/log output should therefore be treated as potentially sensitive. The current application does not implement structured redaction.

### Irrelevant Retention

Confirming a document as irrelevant deletes its local PDF through `exclusion_service.py`, but does not necessarily delete its extracted-text file or remove all parsed/correction metadata. The UI wording may therefore imply broader deletion than occurs.

### Corrupt Store Fallback

`app/services/document_store.py:DocumentStore._load()` can handle unreadable/corrupt JSON by continuing with an empty in-memory collection. A subsequent write could replace the prior store, creating a data-loss risk.

### Broad Exception Fallbacks

`app/services/exclusion_service.py`, `app/services/learning_service.py`, `app/services/correction_map_service.py`, `app/parsers/supplier_validator.py`, and workbook-loading logic use broad exception fallbacks in some read paths. Empty/default structures can keep the application running but can silently discard learned, exclusion, or existing-output context.

## Current Trust and Deployment Boundary

Panda is a local desktop tool that trusts:

- the operator's machine and filesystem permissions;
- the configured Google service account;
- files returned from the configured Drive hierarchy;
- local JSON state;
- the installed Python environment and dependencies;
- the user's default PDF and spreadsheet applications.

There is no remote Panda server, user-account system, role model, encryption-at-rest layer, central secrets manager, or audit-event service in the current implementation.

## Operational Guidance

Keep `.env`, credentials, runtime data, extracted text, and exports outside Git; restrict filesystem access according to the data's sensitivity; and back up operational state before future persistence changes. See [Operations](OPERATIONS.md).
