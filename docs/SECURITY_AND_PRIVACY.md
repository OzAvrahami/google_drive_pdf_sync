# Panda Security and Privacy

This document records the current Panda 2.0.0 data boundary and implemented
safeguards. It is not a claim of a complete security program.

## Local Sensitive Data

Panda can store sensitive accounting and operational data locally:

- source PDFs and extracted text;
- parsed invoice fields and human corrections;
- Google Drive identifiers and folder paths;
- local JSON state and learned rules;
- generated Excel workbooks; and
- filenames, paths, values, and exceptions in console output.

These are operational data, not source code. Access to the workstation,
repository-local runtime directories, backups, and generated outputs must reflect
their sensitivity.

## Repository and Private Corpus Boundary

Git ignore rules protect:

- runtime data, downloads, extracted text, and outputs;
- `.env` and real service-account credentials;
- real PDFs anywhere below `tests/fixtures/pdf/`;
- the real `pdf_manifest.csv` Ground Truth inventory;
- generated benchmark and positional-layout artifacts; and
- caches and local development-tool state.

Tracked corpus content is limited to safe templates, empty-directory markers,
synthetic tests, and code. Ignore rules prevent current accidental tracking but
do not erase historical Git content.

## Implemented Safeguards

- Drive-derived download paths are sanitized and resolved within the configured
  download root.
- Local PDF deletion verifies that the resolved target remains within the
  intended download boundary.
- Excel output neutralizes unsafe formula-leading document values and avoids
  destructive recovery from unreadable workbooks.
- `DocumentStore` validates exact schema version and structure, fails closed on
  corrupt/unsupported data, and writes atomically.
- Destructive irrelevant and duplicate workflows use explicit confirmation and
  service boundaries.
- Private manifest updates use temporary-file replacement and report locked-file
  errors without partial writes.
- Private fixture regressions skip safely when local data is absent.

## Google Service Account

Panda uses the configured local Google service-account JSON and requests
read-only Drive access. The credential file must remain local and must never be
copied into documentation, tests, or commits.

A real credential was historically committed before repository hygiene.
Rotation/revocation remains an external manual action unless separately
confirmed complete. Panda 2.0.0 does not claim that action was completed.

## Remaining Risks and Boundaries

- Console logs and progress/error messages may contain sensitive filenames,
  paths, parsed values, or exception details; structured redaction is not
  implemented.
- Marking a document irrelevant does not imply secure erasure of every derived
  text, correction, backup, or historical artifact.
- Some auxiliary rule/map readers retain compatibility fallbacks; operational
  files should be preserved before troubleshooting unexpected defaults.
- Panda has no encryption-at-rest layer, secrets manager, remote account/role
  model, central audit service, or automatic backup/restore system.
- Panda does not upload documents to AI/LLM parsing or telemetry services.

See [Operations](OPERATIONS.md) for local setup, backup, and troubleshooting.
