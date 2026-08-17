# Panda UI Inventory

This is the factual inventory of the current PySide6 desktop UI. It is intended to be primary implementation input for future Panda 2.0 design work, not a design proposal. Workflow details are in [Product Flows](PRODUCT_FLOWS.md).

## View and Dialog Inventory

| View / Dialog | Source | Purpose | Core Data | Main Actions | Important States |
| --- | --- | --- | --- | --- | --- |
| Main application shell | `app/ui/main_window.py:MainWindow`, `app/ui/sidebar_widget.py:SidebarWidget` | Hosts navigation, toolbar, search, dashboard/table stack, and status bar | Document counts, selected Drive IDs, active view/filter | Navigate, scan, process, retry, export, search, open row context menu | Toolbar locked during workers; current view; row selection |
| Dashboard | `app/ui/dashboard_widget.py:DashboardWidget` | Shows summary cards, recent documents, and shortcut actions | Status counts and recent records | Scan Drive, process new documents | Counts refresh when shown; no dedicated empty illustration |
| New Documents | `MainWindow` shared table | Work queue for `new` records | New document metadata | Process, reprocess selected, open/review, retry, mark irrelevant | Empty table or one/multi-row selection |
| Needs Attention | `MainWindow` shared table and attention filter bar | Combines review, failure, skipped, and suspected-duplicate work | `needs_review`, `failed`, `skipped`, duplicate flags/reasons | Filter, review/edit, retry, reprocess, resolve duplicate, mark irrelevant | All, review, failed, skipped, duplicate filters; reason column shown |
| Processed / Pending | `MainWindow` shared table and results filter bar | Shows processed and approved documents awaiting or eligible for export | `processed`, `approved`, correction flag | Filter, review/edit, approve through review, retry/reprocess when allowed, export approved | All, automatic, corrected, approved filters |
| Irrelevant | `MainWindow` shared table | Shows permanently excluded records | `confirmed_irrelevant`, legacy `excluded` | Open/view where available | Source PDF may have been deleted; retry is blocked by service |
| History | `MainWindow` shared table | Shows locally exported records | `exported`, export boolean, effective invoice fields | Open/view/review; source PDF access if retained | No pagination; records are a status projection, not immutable audit events |
| Review / Correction Dialog | `app/ui/review_dialog.py:ReviewDialog` | Inspect extracted text and edit one document | Effective invoice fields, status, confidence, raw text, source-PDF path | Open PDF, save corrections, approve, mark irrelevant, cancel, edit status | Modal; save default button; irreversible action disabled for already irrelevant/excluded |
| Progress Dialog | `app/ui/progress_dialog.py:ProgressDialog` | Reports long-running scan/process/retry/export work | Current step, totals, progress messages/log | Close after completion | Modal; close disabled while active; no cancel action |
| Irrelevant Confirmation | `app/ui/confirm_irrelevant_dialog.py:ConfirmIrrelevantDialog` | Confirms permanent exclusion and local PDF deletion | One or multiple selected filenames | Confirm or cancel | Destructive warning; selected-file list for multiple records |
| Duplicate Confirmation | `app/ui/main_window.py:MainWindow._on_confirm_duplicate()` | Confirms treating one suspected duplicate as irrelevant | Selected document and duplicate flags | Confirm or cancel | Only offered for one suspected duplicate |
| Export Result | `app/ui/main_window.py:MainWindow._on_export()`, `ExportWorker` completion handlers | Reports no-op, success, or failure after Excel export | Exported count and output path | Dismiss | Informational/success/error variants |
| Generic informational/error dialogs | `app/ui/main_window.py`, `app/ui/review_dialog.py`, worker callbacks | Communicates invalid selection, missing file/text, completion, or exceptions | Message text derived from action/service | Dismiss | Information, warning, confirmation, critical/error |

## Navigation

`SidebarWidget` is fixed at 175 px and uses a `QListWidget` with six current items:

1. Dashboard
2. New Documents
3. Needs Attention
4. Processed / Pending
5. Irrelevant
6. History

Count badges are appended to queue labels. The sidebar defaults to row 1, **New Documents**, not Dashboard.

`MainWindow` uses a `QStackedWidget` with two content widgets:

- index 0: Dashboard;
- index 1: the shared table area used for every queue/history view.

Changing a non-dashboard navigation item changes the status/filter projection and reuses the same table. The Dashboard is refreshed only when selected.

## Toolbar

The non-movable top toolbar in `MainWindow._build_toolbar()` exposes:

- Scan Drive;
- Process New Documents;
- Retry Selected;
- Export to Excel.

The buttons are locked while a worker is active and unlocked after completion/error. Dashboard shortcut buttons duplicate scan and process actions.

## Search

One search field appears above the stacked Dashboard/table content. Its placeholder specifies filename, supplier, and invoice/document number, and `MainWindow._passes_filter()` searches those fields case-insensitively.

Every text change calls `_refresh_table()`, which clears and reconstructs the shared table. When Dashboard is visible, the search control remains visible but does not filter Dashboard content, creating a control/content mismatch.

## Filters

### Needs Attention

The attention filter bar provides:

- all attention;
- needs review;
- failed;
- skipped;
- suspected duplicate.

Duplicate filtering is based on `is_duplicate_suspected`, not a primary status. The attention-reason column is visible only in this view.

### Processed / Pending

The results filter bar provides:

- all;
- automatically processed;
- manually corrected;
- approved.

These combine primary status and `was_manually_corrected`.

## Document Table

The shared `QTableWidget` has ten configured columns:

1. Filename.
2. Drive folder path.
3. Supplier.
4. Date.
5. Document number.
6. Total.
7. Status.
8. Confidence.
9. Attention reason.
10. Hidden Drive ID.

Current behavior:

- rows are read-only;
- row selection is extended/multi-select;
- native table sorting is enabled;
- columns use interactive resize with initial hard-coded widths;
- vertical and horizontal scrolling are supplied by Qt as needed;
- the attention-reason column is hidden outside Needs Attention;
- the Drive-ID column is always hidden and used for record lookup;
- there is no pagination;
- there is no custom virtualization;
- refresh repopulates all matching rows;
- totals and confidence are rendered as formatted strings, so native sorting is lexical rather than numeric.

## Context Menu

Depending on selection count and record state, the row context menu includes:

- Open / Edit;
- Retry;
- Reprocess one or the selected count;
- Mark as Irrelevant, including multi-selection;
- Confirm Duplicate — move to Irrelevant;
- Not a Duplicate — return to normal display.

Duplicate-resolution actions appear only for a single selected suspected duplicate. Double-click opens the one-document review flow.

## Review Dialog

`ReviewDialog` is modal and has a minimum size of 1000 × 620. A splitter presents:

- an editable fields panel;
- a read-only raw extracted-text panel.

Editable/current fields:

- supplier;
- document number;
- date;
- total;
- VAT;
- subtotal;
- description;
- primary status selector.

Read-only context:

- confidence percentage with color styling;
- raw extracted text in Courier New;
- filename in the window title.

Actions:

- Open PDF — delegates to the operating system's default external PDF application;
- Approve Document;
- Mark as Irrelevant;
- Save Corrections;
- Cancel.

The status selector includes primary statuses and permits direct assignment. Total/VAT/subtotal parsing provides weak feedback for invalid input, date is free text, and empty-string corrections fall back to extracted values.

## Loading States

- Long tasks open a modal `ProgressDialog` with title/header, determinate or updated progress, current-file text, and a scrollable log.
- Toolbar buttons are disabled while a worker runs.
- The progress close button remains disabled until the worker completes.
- Table row updates and status-bar messages provide partial live feedback during processing.
- There is no skeleton/loading representation inside Dashboard or table views.

## Empty States

- Queue views display an empty table when no records match.
- Filtered searches can also produce an empty table.
- Dashboard recent activity can be empty.
- Export explicitly reports when there are no approved records.

There are no substantial task-specific empty-state explanations, illustrations, or next-step guidance in the queue tables.

## Error States

- Worker exceptions emit a text error and are shown with message boxes.
- Failed records persist `error_message` and appear in Needs Attention.
- Attention reasons summarize failure, missing/low-confidence data, skipped classification, or duplicate suspicion.
- Missing source files and source-opening failures produce dialogs.
- Some lower-level auxiliary-store failures silently return empty/default structures and may not be understandable to the user; see [Security and Privacy](SECURITY_AND_PRIVACY.md).

## Disabled States

- Toolbar actions are disabled during active workers.
- Progress-dialog close is disabled while work runs.
- Mark Irrelevant in Review is disabled for `excluded` and `confirmed_irrelevant`.
- Some context-menu actions depend on single selection, multi-selection, status, or duplicate flags.

There is no centralized UI capability model; enablement and eligibility rules are distributed among handlers.

## Confirmation States

- Irrelevant marking requires a dedicated confirmation; multi-selection lists affected filenames.
- Confirming a duplicate as irrelevant requires confirmation.
- Dismissing a duplicate clears flags without an integrated document comparison.
- Export completion and ordinary errors use modal message boxes.

## RTL / LTR

- `run.py` sets the entire application to RTL.
- Main windows, forms, tables, and primary copy are Hebrew-first.
- Filename, Drive path, numeric/date, and raw extracted/log content can contain LTR or mixed-direction data.
- Raw text is currently forced RTL, while log/source identifiers do not have a formal per-field bidi convention.
- There is no localization framework; user-facing strings are embedded in Python.

## Current Window Constraints

- Main window: minimum 1100 × 680; default resize 1400 × 820.
- Sidebar: fixed width 175 px.
- Review dialog: minimum 1000 × 620.
- Progress dialog: minimum 540 × 420.
- Irrelevant confirmation: minimum width 460.

Layouts use Qt containers and can grow, but these fixed/minimum desktop dimensions and the wide table make small-window behavior constrained. There is no mobile or web responsive mode.

## Existing Visual Language

Current styling is implemented with Qt Style Sheets:

- a global style string in `run.py`;
- widget-specific inline style strings throughout `app/ui/`;
- Arial for application text;
- Courier New for raw extracted text and progress/log presentation;
- recurring blue, green, orange, red, teal, gray, and white treatment for actions, statuses, cards, and feedback;
- 3–4 px control radii and small fixed paddings in many rules;
- a fixed light sidebar;
- emoji characters used as navigation/action icons;
- native Qt layout and table behavior.

There is no formal token system, shared theme model, icon library, dark mode, theme infrastructure, or localization framework. Colors, padding, radii, and component rules are repeated inline.

## Confirmed UX Limitations

These findings are supported directly by the implementation:

- Dashboard is not the default startup view.
- Search remains visible on Dashboard but does not operate on Dashboard content.
- Review is modal and limited to one document.
- PDF review switches to an external application.
- There is no batch approval.
- There is no side-by-side duplicate comparison.
- Many routine outcomes and decisions use modal dialogs.
- Progress cannot be cancelled.
- Formatted numeric values sort lexically.
- Search rebuilds the whole table on each change.
- Empty queues have weak guidance.
- There is no application-specific keyboard workflow or shortcut layer.
- Direct status editing can bypass expected workflow transitions.
- Numeric and date validation provide weak feedback.
- A field cannot cleanly override extracted data with an intentional empty value.

## Panda 2.0 Designer Constraints

A future visual/interaction redesign must not accidentally remove these implemented product requirements:

- scan a Google Drive folder recursively;
- process new PDFs and expose background progress;
- access the original/source PDF;
- inspect extracted text and parsed fields;
- correct extracted fields and preserve correction/learning behavior;
- show confidence and actionable attention reasons;
- approve documents;
- retry one document and reprocess eligible selections;
- detect, confirm, or dismiss duplicate suspicions;
- mark one or more records irrelevant with confirmation;
- export approved records to Excel;
- access exported history;
- operate as a local desktop application;
- support Hebrew-first RTL workflows while handling mixed LTR content.

Possible redesign concepts belong in the [Roadmap](ROADMAP.md) and future design work, not in this current-state inventory.
