# Changelog

All notable changes to Panda are documented in this file. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) for formal releases.

## [Unreleased]

## [2.0.0] - 2026-08-29

This is Panda's first formal release. Earlier Git history records development
milestones rather than published application releases.

### Added

- Added the Panda 2.0 desktop shell, Overview, queue navigation, document
  workspace, embedded PDF preview, and page navigation.
- Added session task management with the Task Dock and Task Center.
- Added document approval and Excel-export workflows, duplicate resolution,
  irrelevant-document handling, and guarded destructive actions.
- Added the developer-only PDF Benchmark workspace and the shared local corpus
  service used by both the desktop UI and review CLI.
- Added private-corpus intake, SHA-256 inventory, organization, human Ground
  Truth review, mismatch reporting, and verified-accuracy tooling.
- Added reusable positional PDF layout analysis plus diagnostic and deterministic
  performance benchmark tools.
- Added synthetic regressions and optional private-real-PDF regressions that
  skip explicitly when local fixtures are unavailable.

### Changed

- Hardened native digital-PDF parsing, including mixed Hebrew/LTR normalization,
  transaction-invoice and payment-request variants, supplier selection,
  document-number extraction, document-date priority, and payable totals.
- Added conservative positional supplier resolution for the verified
  two-column customer/issuer ambiguity while keeping text parsing authoritative
  by default.
- Reduced positional geometry analysis from 70 corpus identities to 5 without
  changing structured parser results.
- Separated operational parser metrics from reviewed Ground Truth accuracy.

### Fixed

- Prevented structural source markers and service/product descriptions from
  being selected as suppliers.
- Corrected customer/issuer ambiguity caused by merged two-column PDF text and
  bounded legal-entity/branding extraction.
- Prevented technical footer generation dates from outranking stronger business
  document dates.
- Added verified payment-request and transaction-invoice number forms, including
  semantically labelled slash-containing identifiers.
- Added bounded support for adjacent value-before-final-total layouts without
  promoting subtotals or VAT-only values.

### Security / Privacy

- Kept all real corpus PDFs and the real human Ground Truth manifest local-only
  through explicit Git ignore rules.
- Kept generated private benchmark and layout-analysis artifacts local-only.
- Preserved clean-clone and CI safety: synthetic tests remain available while
  private-real-PDF tests skip with an explicit reason when fixtures are absent.

### Verification

- **Repository-verifiable release preparation:** the incoming baseline was
  1,041 passing tests; final verification reached 1,043 after adding the two
  application-version contract tests, with no failures or skips.
- **Local/private verification (not reproducible from a clean clone):** all 42
  human-reviewed unique identities matched Ground Truth for supplier, date,
  document number, and amount.
- **Local/private corpus snapshot:** 112 unique identities, including 111 native
  digital PDFs and 1 non-native PDF; 98 processed, 13 skipped by policy, and the
  non-native document remained in needs-review without OCR.

[Unreleased]: https://github.com/OzAvrahami/google_drive_pdf_sync/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/OzAvrahami/google_drive_pdf_sync/releases/tag/v2.0.0
