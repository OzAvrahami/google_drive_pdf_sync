# Panda Testing

This document records the current verification baseline. Planned Panda 2.0 quality work is explicitly separated from what exists today.

## Framework

The repository uses pytest. Tests live under `tests/` and exercise parsing, validation, learning, exclusion, legacy state, and selected utilities.

## Existing Coverage

Current test modules cover aspects of:

- invoice/document classification;
- invoice-number extraction;
- date extraction and normalization;
- amount extraction;
- supplier/business-name extraction;
- Hebrew/RTL text normalization;
- supplier validation and learned supplier rules;
- confidence calculation and routing;
- learning and correction behavior;
- exclusion registry behavior;
- Drive exclusion filtering;
- legacy `StateManager` filtering/persistence;
- local file opening behavior.

These tests are primarily unit or focused integration-style tests with temporary files and mocked dependencies. Their presence does not establish complete end-to-end coverage.

## Current Gaps

No comprehensive automated coverage was identified for:

- the full `ProcessingService` pipeline from Drive bytes through persisted result;
- changed Drive-file behavior when a stale local PDF already exists;
- `DocumentStore` corruption and safe recovery;
- duplicate detection/resolution as a full workflow;
- Excel export preservation, corruption, and formula-safety behavior;
- Qt worker lifecycle and cancellation/cleanup behavior;
- `MainWindow` filtering, selection, enablement, and navigation behavior;
- Review-dialog validation and allowed state transitions;
- end-to-end scan → process → review → approve → export;
- large queue performance and search behavior;
- configuration and credential failure modes;
- store-version and future migration compatibility.

There are no established repository quality gates for linting, formatting, static type checking, UI/E2E testing, coverage thresholds, or CI.

## Known Test Problem

`tests/test_pdf_parser.py` performs local file I/O during module import/test collection and contains a hard-coded Windows path. On a machine without that exact local file, collection can fail before normal test execution. This is a known test-structure issue and was not changed by the documentation task.

## Existing Commands

The repository's current pytest command is:

```powershell
pytest tests/ -v
```

Individual modules can also be selected with ordinary pytest arguments, but no custom validation script or CI workflow is currently defined.

## Audit Verification Limitation

During the comprehensive repository audit, Python and pytest were unavailable on `PATH` in the audit environment. The test suite was therefore **not run**, and this documentation does not claim that it passes.

This documentation-baseline task does not install dependencies or create a Python environment.

## Panda 2.0 Quality Baseline — Planned

The following are planned quality-foundation goals, not current capabilities:

- a reproducible Python environment;
- pinned or otherwise reproducibly resolved dependencies;
- parser characterization/regression tests preserving current accepted behavior;
- full processing-pipeline tests;
- Drive new/changed-file tests, including stale local content;
- persistence load/save/corruption/recovery tests;
- explicit state-transition tests;
- duplicate-detection and resolution tests;
- Excel export preservation and safety tests;
- UI and workflow tests;
- large-queue behavior tests;
- configuration/credential failure tests;
- migration compatibility fixtures;
- linting;
- formatting checks;
- type checking;
- continuous integration.

The sequence for establishing these gates is tracked in the [Roadmap](ROADMAP.md).
