# Panda Architecture Decision Records

Panda 2.0 decisions that materially affect architecture, persistence, workflow, operations, security, or product behavior will be captured as separate Architecture Decision Records (ADRs).

This directory is an index and template only. No Panda 2.0 architectural decision has been accepted merely because a topic appears in the [Roadmap](../ROADMAP.md).

## Process

1. Create one numbered Markdown file for a specific decision.
2. Record the current context and constraints from the factual baseline.
3. Mark the record **Proposed** while alternatives are being evaluated.
4. Change it to **Accepted** only after explicit review and approval.
5. If a later decision replaces it, retain the original and mark it **Superseded**, linking both records.
6. Update this index when a decision record is added.

Decision records should distinguish implemented current behavior from the proposed or accepted Panda 2.0 choice.

## Future Records

Likely future files include:

```text
001-persistence-strategy.md
002-status-workflow.md
003-legacy-cli.md
004-runtime-data-location.md
005-review-workspace.md
```

These files do not exist yet and must not be created until the corresponding decision is explicitly evaluated.

## ADR Template

```markdown
# ADR XXX — Title

## Status

Proposed / Accepted / Superseded

## Context

## Decision

## Consequences
```

Open questions are tracked in the [Architecture](../ARCHITECTURE.md#panda-20-architectural-questions) and [Roadmap](../ROADMAP.md#deferred--open-decisions).
