# Panda UI Inventory

This inventory describes the implemented Panda 2.0 desktop UI at application
version **2.0.0**.

## Application Shell

`PandaMainWindow` provides a Hebrew-first RTL shell with:

- the Panda navigation rail and authoritative application-version badge;
- primary route content;
- the document workspace as a separate shell mode;
- the developer PDF Benchmark as a secondary-tool mode; and
- the Task Dock and Task Center.

The approved token, typography, icon, spacing, surface, and status systems live
under `app/ui/theme/` and `app/ui/components/`.

## Primary Navigation

The primary business routes are:

1. **Overview** - queue totals, operational actions, current metrics, and recent
   document activity.
2. **Inbox** - new documents awaiting processing.
3. **Needs Attention** - needs-review, failed, skipped, and duplicate-suspected
   records with segment filters.
4. **Ready** - documents ready for approval or approved and ready for export.
5. **Irrelevant** - confirmed-irrelevant and excluded records.
6. **History** - exported records.

PDF Benchmark is intentionally not a primary queue. It is exposed as a
developer/secondary tool in the navigation rail.

## Queue Views

Queue views provide:

- route-appropriate headings, counts, and actions;
- search and typed sorting;
- stable single/multi-selection;
- status and attention indicators;
- attention and ready segment filters;
- open-on-row activation; and
- refresh behavior that preserves relevant selection where possible.

Ready additionally provides selected approval/export actions, eligibility
feedback, confirmation, and export results.

## Document Workspace

The workspace combines:

- origin queue and previous/next navigation;
- integrated PDF preview with page controls, disabled boundary states,
  accessibility names, and tooltips;
- supplier, document number, date, and amount presentation/editing;
- validation and workflow context;
- save and approval actions;
- duplicate candidate inspection, confirm, and dismiss actions; and
- confirmed irrelevant-document handling.

Draft state is separate from persisted data. Unsaved changes are surfaced and
guarded during navigation or close. Mixed Hebrew/Latin names, identifiers, and
amounts use the existing direction utilities rather than character reversal.

## PDF Preview

`app/ui/workspace/source_preview.py` is the single reusable PDF preview
implementation. Both the business workspace and developer Benchmark reuse it.
It manages page rendering, navigation state, source release, errors, and
asynchronous loading without duplicating PDF rendering logic.

## Task Dock and Task Center

The Task Dock summarizes session work and opens the non-modal Task Center.
The Task Center groups active and completed tasks, displays progress/current
items, results or actionable errors, and exposes cancellation only where the
underlying task supports it.

## Developer PDF Benchmark

The three-region Benchmark workspace contains:

- a filterable/sortable corpus list;
- the shared PDF preview; and
- an editable review panel comparing current Panda output with Ground Truth.

It includes reviewed progress, field and fully-correct accuracy, mismatch state,
source/status/native-text context, Everything Correct, Save & Next, intentional
blank semantics, unsaved-edit protection, and friendly locked-manifest errors.

Non-native documents are labelled as lacking meaningful native text and make
clear that OCR is not available. Policy-skipped documents are distinguished from
parser failures.

## Common UI States

Implemented views provide route-appropriate:

- loading/task feedback;
- empty queues and empty private-corpus state;
- disabled actions when selection or workflow capability is missing;
- inline validation and non-blocking success feedback;
- actionable error messages without raw tracebacks; and
- confirmation for destructive or unsaved-change decisions.

## Legacy Surface

The former `MainWindow` and dialogs remain available through the default
no-flag startup path. They are compatibility surfaces, not the Panda 2.0 UI
inventory. Consolidating startup and retiring legacy presentation are future
decisions.
