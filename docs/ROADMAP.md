# Panda Roadmap

This roadmap separates the current implementation from proposed Panda 2.0 work. Planned phases are direction and sequencing, not approved designs or implementation commitments. Significant decisions will be recorded through the [Panda ADR process](decisions/README.md).

## Current Baseline

The current application is the Panda 1.x / legacy current baseline: a functional local Hebrew-first PySide6 accounting-document workflow using Google Drive, local JSON/files, and Excel.

“1.x” is a descriptive baseline label only. Panda has no formal application versioning system, semantic-version release, or Git tag today. The implementation snapshot is documented in [Current State](CURRENT_STATE.md).

## Panda 2.0

> Transform Panda from a functional internal desktop accounting tool into a polished, efficient, reliable document-processing product while preserving the proven parsing and accounting workflow.

## Phase 0 — Repository & Project Baseline

**Status: Completed / mostly completed**

- Full project audit — completed.
- Runtime and generated files removed from current Git tracking — completed.
- `.env` and real credential files removed from current Git tracking — completed.
- Generated Python artifacts removed from current Git tracking — completed.
- Official current-state and Panda 2.0 documentation baseline — completed by this documentation task, pending normal review.

Google service-account key rotation/revocation is deferred and not completed. It is a manual security action and does not block Panda 2.0 product, documentation, or design planning.

## Phase 1 — Product & UX Definition

**Status: Planned**

- Define Panda 2.0 information architecture.
- Redesign the Dashboard concept.
- Define queue structure and ownership.
- Redesign review and correction workflow.
- Define duplicate-resolution UX.
- Define background-task UX.
- Establish an RTL design language.
- Produce a complete target screen/state inventory.
- Use Claude Design for exploration based on factual repository constraints.
- Review and approve the design before implementation planning.

## Phase 2 — Reliability Foundation

**Status: Planned**

Work derives from confirmed current findings:

- Correct changed Drive-file handling so reprocessing cannot reuse stale bytes.
- Centralize and enforce status-transition policy.
- Implement safe persistence corruption/recovery behavior.
- Establish a backup strategy.
- Enforce download-path containment.
- Enforce a safe local-deletion boundary.
- Protect Excel export from unsafe content and destructive recovery.
- Define schema versioning and migration strategy.
- Establish a reproducible Python and test environment.

The exact persistence and migration implementation depends on future ADRs.

## Phase 3 — Panda 2.0 Design System

**Status: Planned**

- Design tokens.
- Typography.
- Color system.
- Spacing.
- Status semantics.
- Iconography.
- Buttons.
- Inputs and validation.
- Tables and queue controls.
- Badges.
- Empty states.
- Loading/progress states.
- Dialogs and confirmations.
- RTL/LTR conventions for mixed content.

## Phase 4 — Application Shell & Dashboard

**Status: Planned**

Concept-level goals:

- modern application shell;
- clear navigation;
- work-focused dashboard;
- actionable queue counts;
- recent activity;
- attention-focused information hierarchy.

No final UI structure or technology change is approved yet.

## Phase 5 — Document Workspace

**Status: Planned**

Potential product/design goals:

- queue-oriented review;
- source/PDF context inside the review experience if technically approved;
- structured editable fields;
- visible confidence, validation, and error context;
- stronger field validation;
- next/previous navigation;
- approval;
- efficient repetitive processing.

These are design goals, not final technical commitments.

## Phase 6 — Attention & Duplicate Workflows

**Status: Planned**

- Dedicated needs-attention workflow.
- Better failure visibility and recovery guidance.
- Duplicate comparison.
- Confirm or dismiss duplicate.
- Retry.
- Batch operations where appropriate and safe.

## Phase 7 — Processed, Irrelevant & History

**Status: Planned**

- Clarify the distinction between processed, approved, exported/history, automatically skipped, and confirmed irrelevant.
- Improve processed/pending inspection and export readiness.
- Align irrelevant wording with actual retention and exclusion behavior.
- Define history and audit expectations.
- Preserve access to required source and effective accounting data according to approved retention decisions.

## Phase 8 — Background Tasks & Operations

**Status: Planned**

- Non-blocking progress UX.
- Better task feedback and completion summaries.
- Retry and understandable error recovery.
- Potential cancellation where the underlying operation can be stopped safely.
- Operational backup and recovery guidance aligned with the chosen persistence model.

## Phase 9 — Regression, Migration & Release Readiness

**Status: Planned**

- Back up operational data.
- Perform migration dry runs against copies.
- Run parser regression and characterization checks.
- Run workflow regression checks.
- Run Excel export regression checks.
- Validate against a representative real-world dataset without exposing it.
- Define packaging and release strategy.
- Prepare changelog and release notes.

## Deferred / Open Decisions

None of these items is an approved Panda 2.0 feature or architecture choice:

- Google service-account credential rotation/revocation — required manual security action, deferred.
- JSON versus SQLite for primary persistence.
- Keep, replace, or retire the legacy CLI.
- Whether and how to add OCR.
- Packaging and installer approach.
- Runtime-data location outside the repository.
- Whether Panda remains single-user/local or evolves toward multi-user/server architecture.
- Direct integration with an accounting system.
- Localization beyond the Hebrew-first product.
- An explicit audit-event model.
- Central state/workflow service design.
- Embedded PDF approach and its platform constraints.

Accepted choices should be captured as individual [decision records](decisions/README.md) before implementation.
