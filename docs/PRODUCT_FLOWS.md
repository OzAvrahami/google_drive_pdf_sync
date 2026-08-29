# Panda Product Flows

These flows describe the implemented Panda 2.0 behavior at application version
**2.0.0**.

## 1. Startup

The user starts the Panda 2.0 shell with:

```powershell
python run.py --panda2
```

Panda creates the required local directories, configures Qt with the
authoritative application version, and loads `DocumentStore`. An existing
malformed, invalid, or unsupported store fails closed with a user-facing error;
Panda does not replace it with an empty store.

The shell opens on Overview and projects the current store into queue counts.

## 2. Drive Scan and Intake

The user requests a Drive refresh from the operational UI. The scan runs through
the task system and:

1. authenticates using the configured service account;
2. traverses the configured parent folder recursively;
3. filters excluded entries;
4. creates or refreshes local document records; and
5. updates queue counts and task feedback.

Downloads are resolved below the configured local download boundary.

## 3. Document Processing

Processing runs in the background for documents with `new` status:

1. download or resolve the local PDF;
2. extract and save normalized native text;
3. classify the document;
4. stop with `skipped` for configured receipt/combined-receipt policies;
5. parse supplier, date, document number, and amount;
6. optionally resolve the verified two-column supplier ambiguity with strict
   word-coordinate evidence;
7. validate supplier and compute confidence;
8. route to `processed` or `needs_review`;
9. run duplicate detection; and
10. persist atomically.

Failures become `failed` with an error message. Image-only PDFs receive no OCR
and remain review work rather than being treated as successful native parsing.

## 4. Queue Navigation

Each document belongs to one primary route:

- **Inbox** - newly discovered documents awaiting processing.
- **Needs Attention** - needs-review, failed, skipped, or duplicate-suspected
  documents, with segment filters.
- **Ready** - processed documents ready for approval and approved documents ready
  for export.
- **Irrelevant** - confirmed-irrelevant or excluded documents.
- **History** - exported documents.

Overview summarizes these queues and recent activity. Queue views support search,
typed sorting, selection, and opening the workspace.

## 5. Document Workspace

Opening a queue record creates a stable review session. The workspace shows the
source PDF and structured fields together, supports PDF page navigation, and
tracks an editable draft independently from persisted parser output.

The reviewer can:

- edit and save fields;
- navigate to previous/next queue documents;
- approve an eligible document;
- dismiss or confirm duplicate suspicion;
- inspect a duplicate candidate; or
- mark a document irrelevant after confirmation.

Unsaved edits require confirmation before route, document, benchmark, or window
navigation can discard them. Background store changes are reconciled visibly.

## 6. Ready, Approval, and Export

Ready distinguishes documents ready to approve from approved documents ready to
export. The user can approve selected eligible records and request selected
export. Export uses the existing Excel service, reports success/failure through
the task system, and moves exported records to History.

## 7. Duplicate Resolution

Duplicate suspicion routes a document to Needs Attention regardless of its
ordinary status. In the workspace, the user may inspect the related candidate,
dismiss the suspicion, or confirm the duplicate through guarded workflow
services. Confirmation does not rely solely on automatic similarity.

## 8. Irrelevant and Excluded Documents

Marking a record irrelevant is a confirmed workflow action. The exclusion
service records the decision so later Drive scans can continue to filter the
source. Permanently excluded/irrelevant documents cannot be retried without
removing the corresponding exclusion state.

Automatically skipped document types remain distinct from user-confirmed
irrelevant records.

## 9. Background Tasks

Drive scans, processing, retries, bulk work, and Excel export are represented in
the current-session `TaskManager`. Read/write access controls scheduling; the
Task Dock shows concise state and the Task Center provides active/completed task
details, progress, results, failures, and cancellation where supported.

## 10. Developer PDF Benchmark

PDF Benchmark is a developer-only secondary workspace, not a business queue.
It loads the local private corpus manifest, parses a selected PDF using current
production behavior, reuses the embedded PDF preview, and presents Panda output
beside editable human Ground Truth.

`Everything Correct` explicitly confirms all current Panda values. `Save & Next`
records corrected/intentional values and advances through the active filter.
Manifest writes are atomic; locked-file failures are actionable and do not
partially persist review state.

The CLI review tool uses the same corpus service. Neither UI nor CLI changes
production parser behavior while recording Ground Truth.

## 11. Legacy Paths

The no-flag desktop shell and `python -m app.main` remain available. They share
parts of the operational models and parser but are not the Panda 2.0 presentation
contract. Their consolidation or retirement is future work.
