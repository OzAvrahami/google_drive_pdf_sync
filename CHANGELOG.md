# Changelog

This file records project maintenance and future release changes. The repository currently has no formal Git tags or application releases; the entries below must not be interpreted as released semantic versions.

## [Unreleased]

### Added

- Completed a full repository and product audit before Panda 2.0 planning.
- Established the Panda 2.0 documentation baseline covering current behavior, architecture, workflows, data, UI, operations, security, testing, decisions, and roadmap.

### Changed

- Completed pre-Panda-2.0 repository hygiene.
- Removed runtime and generated operational data from current source tracking while preserving local working copies.
- Removed generated Python bytecode and cache artifacts from source tracking.
- Updated ignore rules for runtime data, generated outputs, local environment files, credentials, Python artifacts, and local development-tool settings.

### Security

- Removed the real local `.env` and Google service-account credential file from current Git tracking.
- Recorded that a Google service-account credential was historically committed. Rotation or revocation is deferred security work and is **not** recorded as completed.

## Historical Development Snapshot

Git history reflects iterative development of the desktop UI, Drive synchronization, document parsing and validation, review/correction behavior, duplicate handling, irrelevant-document handling, Excel export, and automated tests. These commits are development milestones, not formal releases.
