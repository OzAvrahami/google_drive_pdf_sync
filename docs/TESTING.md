# Panda Testing

This document records the test and private-benchmark contract for Panda
**2.0.0**.

## Canonical Command

```powershell
python -B -m pytest
```

Release-preparation result on 2026-08-29:

```text
1043 passed
0 failed
0 skipped
```

The incoming implementation baseline contained 1,041 passing tests. Two focused
application-version contract tests were added during release preparation. The
1,043-test result was produced in the local release workspace where the optional
private corpus was present. Test counts in a clean clone can differ because
private-real-PDF tests skip explicitly when their fixtures are unavailable.

## Tracked Coverage

The test suite includes unit and focused integration coverage for:

- document models, persistence validation, atomic store behavior, and workflow
  policy;
- Drive freshness, download containment, exclusions, duplicates, approval,
  irrelevant handling, export, and Excel safety;
- invoice classification and supplier/date/number/amount parsing;
- supplier validation, correction/learning behavior, RTL normalization, and
  confidence routing;
- Panda 2.0 theme/components, route and queue models, Overview, Ready, shell,
  tasks, workspace editing, source preview, and guarded workflows;
- PDF corpus inventory, review semantics, organization, accuracy calculation,
  diagnostics, layout analysis, and Benchmark UI; and
- application-version integration.

Synthetic/unit regressions protect important parser behavior independently of
the private corpus.

## Private Real-PDF Coverage

Real PDFs under `tests/fixtures/pdf/`, the real `pdf_manifest.csv`, and generated
benchmark/layout artifacts are ignored. When available locally:

- real-PDF regression tests run against verified controls;
- the batch analyzer executes current production behavior;
- reviewed accuracy compares current parser output with human Ground Truth; and
- duplicate physical files are counted once by SHA-256 identity.

When absent, private fixture tests skip with an explicit reason such as
`private real-PDF fixture not available locally`. They do not cause ordinary
clean-clone test failure, and Panda never derives expected values from its own
parser output.

## Benchmark Commands

```powershell
python -B scripts/diagnose_pdf.py "<pdf>"
python -B scripts/diagnose_pdf_batch.py "tests/fixtures/pdf"
python -B scripts/diagnose_pdf_batch.py "tests/fixtures/pdf" --new-only
python -B scripts/diagnose_pdf_layout.py "tests/fixtures/pdf"
python -B scripts/benchmark_pdf_performance.py "tests/fixtures/pdf" --repeat 3
python -B scripts/review_pdf_corpus.py "tests/fixtures/pdf"
```

Operational processing, field presence, reviewed accuracy, and fully-correct
documents are separate metrics. Unreviewed documents never enter Ground Truth
accuracy denominators.

## Local Release Verification

The private release-preparation snapshot reported:

- 42/42 reviewed unique identities fully correct across supplier, date,
  document number, and amount;
- 112 unique identities, including 111 native digital and 1 non-native PDF;
- 98 processed and 13 skipped by policy; and
- the non-native document remaining in needs-review with OCR out of scope.

These numbers are local/private verification and cannot be reproduced from the
public repository alone.

## Remaining Quality Work

- There is no checked-in CI workflow, coverage threshold, formatter, linter, or
  static type-checking gate.
- The private sample is intentionally not distributable and should continue to
  grow through human review rather than parser-generated expectations.
- OCR/scanned-document behavior has no implementation coverage because OCR is
  not implemented.
- Packaging/installer and migration verification remain future release work.
