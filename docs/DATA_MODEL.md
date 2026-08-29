# Panda Data Model

This document describes Panda **2.0.0** operational data and local persistence.

## Version Contracts

Panda has distinct version domains:

| Contract | Current value | Source |
| --- | --- | --- |
| Application release | `2.0.0` | `app/version.py` |
| Document-store schema | `2` | `DocumentStore.CURRENT_STORE_VERSION` |
| Correction/rule/diagnostic formats | format-specific `1` or `2` | owning service/script |

Application release changes do not automatically change storage schemas. The
schema values are compatibility contracts for their own files, not SemVer.

## Primary Entity: Document

`app/models/document.py` defines the operational `Document` record.

### Identity and Source

- stable local record ID;
- Google Drive file ID;
- source filename and folder path;
- Drive modification metadata; and
- local source/text paths.

### Workflow

The main status values represented by queue policy include:

- `new`;
- `needs_review`;
- `failed`;
- `skipped`;
- `processed`;
- `corrected` where retained by legacy/current workflows;
- `approved`;
- `confirmed_irrelevant` / `excluded`; and
- `exported`.

Duplicate suspicion is an orthogonal flag and routes the record to Needs
Attention until resolved.

### Structured Accounting Data

Documents retain parser output and effective workflow fields including:

- document type;
- supplier/business name;
- invoice/document date;
- invoice/document number;
- amount;
- confidence and error information; and
- supplier-validation details in extracted parser data.

Human corrections are stored separately from raw parser output so the effective
record can preserve review intent without rewriting production parsing logic.

### Review, Duplicate, and Export State

The entity also records correction history/flags, duplicate candidate and
resolution state, approval/export state, irrelevant/exclusion state, and
timestamps used by queue and Overview projections.

## DocumentStore

`app/services/document_store.py` is the operational source of truth. Its JSON
shape is an object containing:

- integer `version`, currently exactly `2`; and
- `documents`, an array of serialized document objects.

Load behavior is fail-closed:

- missing store starts empty;
- unreadable or malformed JSON raises `DocumentStoreLoadError`;
- non-object roots and non-array document collections are rejected;
- missing, non-integer, or unsupported schema versions are rejected;
- invalid document entries and duplicate/missing Drive IDs are rejected.

Writes occur under a lock, serialize to a temporary file, and replace the live
store. There is no automatic migration from older/newer store versions.

## Auxiliary Local State

Other local data includes:

- downloaded source PDFs and extracted text;
- correction logs/maps and learned supplier rules;
- exclusion registry data;
- legacy CLI state; and
- generated Excel workbooks.

These are operational artifacts, not application source.

## Private PDF Corpus Model

The developer corpus is separate from operational `DocumentStore` state.
`tests/fixtures/pdf/pdf_manifest.csv` inventories unique PDF identities by
SHA-256 and records source diagnostics plus optional human-reviewed expected
fields.

Important states remain distinct:

- a PDF can be operationally processed without being reviewed;
- blank expected data before review is not Ground Truth;
- intentional blank/N/A is a human review decision;
- correctness is `null` for unreviewed documents, not `false`; and
- duplicate physical paths count once by SHA identity for accuracy.

The real manifest and real PDFs are local-only. A tracked example manifest
contains schema guidance without private business data.

## Current Constraints

- There is no relational database or migration framework.
- Atomic replacement protects individual JSON writes but is not a backup plan.
- Runtime state remains repository-relative/local rather than platform-managed
  application data.
- Legacy and Panda 2.0 paths still share parts of the same model.
