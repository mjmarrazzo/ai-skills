# spec.v<N>.md template

The spec is the **what**, not the **how**. It locks in architecture, contracts, and behavior. The implementation plan is downstream — don't list steps here.

Scale each section to the work's complexity. A medium feature might be 1-2 pages. A migration touching three services might be 5. A trivial spec that ran through blueprint anyway might be half a page — that's fine.

```markdown
# <Slug> — Spec

> See `handoff.md` for context, constraints, and discovery Q&A.

## Goal

One paragraph. What this change accomplishes from the system's perspective.

## Non-goals

What this spec deliberately doesn't address. Pulls the boundaries tight.

## Architecture

How the change fits into the existing system. Diagram if it helps (ASCII or `dot`). Name the components, name the boundaries between them. Reference existing files / modules by path when you're modifying them.

If introducing a new component, justify it: why doesn't an existing one extend?

## Interfaces / contracts

Every public surface the change adds or modifies. Pick the right format per surface:

- **HTTP:** method, path, request schema, response schema, status codes, error shapes.
- **Function / class:** signature, parameter semantics, return type, raised exceptions.
- **Event / message:** topic, payload shape, ordering / delivery guarantees.
- **DB:** tables, columns, indexes, migrations needed, backfill strategy if any.

Show concrete schemas — JSON, type defs, SQL DDL. No "TBD".

## Data model

If the change touches persisted state. Entity relationships, invariants the system maintains, what gets written when. Call out anything that affects existing rows (migrations, backfills, default values).

## Behavior

The interesting cases — what happens on the happy path, what happens on each failure mode, what happens at the edges (empty input, max-size input, concurrent calls, retry semantics, partial failures). One paragraph or bullet list per case.

## Observability

What we'll be able to see when this is in production. Logs, metrics, traces, dashboards — what new ones, what existing ones cover this.

## Security / compliance

Anything load-bearing: authz checks, PII handling, audit log entries, rate limits, secrets / credentials. Skip the section if genuinely not applicable; don't pad with "N/A".

## Open questions

If any survived discovery + drafting. Each one blocks the plan until resolved.

## Reviewer notes folded in

After Phase 3 reconciliation, append a short bullet list of the substantive changes you made based on reviewer feedback. Keeps the audit trail without bloating the body.
```
