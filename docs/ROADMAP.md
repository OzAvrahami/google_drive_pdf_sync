# Panda Roadmap

Panda **2.0.0** is the first formal application release. This roadmap separates
implemented release history from possible future work; future items are not
commitments until explicitly approved.

## Released Baseline: Panda 2.0.0

The following development phases are implemented in the 2.0.0 source baseline:

- repository privacy and runtime-data hygiene;
- reliability foundations for fail-closed document loading, safe downloads,
  destructive operations, Excel export, workflow policy, and background work;
- Panda 2.0 design tokens, reusable components, and RTL/LTR conventions;
- application shell, Overview, and queue-based navigation;
- integrated document workspace and reusable PDF preview;
- Needs Attention, duplicate, irrelevant, approval, Ready/export, and History
  workflows;
- Task Dock, Task Center, and operational task integration;
- developer PDF Benchmark and shared human Ground Truth review service;
- private corpus intake, organization, diagnostics, and accuracy reporting;
- native digital-PDF parser, RTL, classification, supplier, date, number, and
  amount hardening;
- positional supplier analysis and narrowly gated production resolution; and
- deterministic positional-performance measurement and preflight optimization.

The implementation history remains visible in Git. `CHANGELOG.md` is the release
history from 2.0.0 onward.

## Near-Term Stabilization Candidates

These remain candidates for separate, evidence-driven work:

- decide whether Panda 2.0 becomes the default `run.py` shell and whether the
  legacy UI/CLI should be retired;
- add a checked-in CI workflow and decide linting, formatting, type-checking,
  coverage, and supported Python-version gates;
- define packaging/installer and source-release artifact policy;
- define backup/recovery procedures and platform-appropriate runtime-data
  locations;
- design explicit document-store migrations beyond exact schema-version
  rejection;
- continue human review across underrepresented private-corpus source/templates;
  and
- add only evidence-based parser/source-system improvements as separately scoped
  changes.

## Future Product/Architecture Questions

- OCR or another explicit workflow for scanned/image-only PDFs.
- Broader accounting-system integration.
- Localization beyond the current Hebrew-first experience.
- A more explicit operational audit-event model.
- Whether Panda remains local/single-user or adopts another deployment model.
- Cancellation for operations whose underlying implementation can stop safely.

No OCR, cloud parsing, AI/LLM parsing, database migration, or multi-user service
is implied by this roadmap.

## Security and Operations Follow-Up

A Google service-account credential was historically committed before repository
hygiene. Rotation/revocation remains an external manual action unless separately
confirmed complete. Real credentials, operational data, real invoice PDFs,
Ground Truth, and generated private benchmark artifacts must remain untracked.

## Decision Discipline

Material decisions about persistence, migration, packaging, OCR, deployment,
legacy retirement, or external integrations should be recorded through the
[Panda decision-record process](decisions/README.md) before implementation.
