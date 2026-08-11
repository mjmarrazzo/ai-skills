# spec.v<N>.md template

The spec is the **human's** document. It exists so the one person gating this work can read it in a few minutes and say *"no — we don't need CloudFront here"* before a line of code is written.

That makes it decision-led, not implementation-led. It locks architecture, contracts, and behavior. The plan is downstream — no steps here.

## The boundary against the plan

Both documents describe the same change; they are not allowed to describe it at the same depth.

**Belongs in the spec:**
- Decisions, and the alternatives they beat.
- Signatures, type definitions, DDL, JSON/event shapes, HTTP contracts.
- The architecture diagram and the boundaries between components.
- Behavior at the edges and under failure.

**Belongs in the plan, not here:**
- Function bodies, component markup, query/handler internals.
- Test code.
- File-by-file task ordering, commands, commit messages.

Rule of thumb: **a signature is a contract, a body is an implementation.** If a reader could hold you to it at review time, it's spec. If it's one of several correct ways to satisfy the contract, it's plan.

Scale each section to the work. A medium feature runs 1-2 pages; a migration across three services maybe 4. A trivial change that ran through blueprint anyway can be half a page — that's fine. Length is not thoroughness.

```markdown
# <Slug> — Spec

> Context, constraints, and discovery Q&A: `handoff.md`. Locked choices: `decisions.md`.

## Goal

One paragraph. What this change accomplishes from the system's perspective.

## Non-goals

What this deliberately doesn't address. Pulls the boundaries tight and stops the next
reader re-litigating settled scope.

## Architecture

**Lead with the decision.** Name the choice, then the options it beat and why each lost:

> **Decision:** a new `foo-service`, not an extension of `bar-service`.
> **Why not `bar-service`:** it's on a fail-closed path — a fetch failure 503s the whole
> tenant, and this content must never carry that blast radius.
> **Boundary rule:** composition lives in config, content lives in the content service.

A one-line boundary rule, where one exists, is worth more than three paragraphs of
description — it's the thing that settles the next ten arguments.

Then how the change fits: name the components, name the boundaries. Diagram if it helps
(ASCII or `dot`). Reference existing files by path and line range when modifying them.

If introducing a new component, the justification above is mandatory, not optional.

## Interfaces / contracts

Every public surface the change adds or modifies. Pick the format per surface:

- **HTTP:** method, path, request schema, response schema, status codes, error shapes.
- **Function / class:** signature, parameter semantics, return type, raised exceptions.
- **Event / message:** topic, payload shape, ordering / delivery guarantees.
- **DB:** tables, columns, indexes, migrations needed, backfill strategy.

Show concrete schemas — JSON, type defs, SQL DDL. No "TBD".

**Signatures, not bodies.** `refreshSession(): Promise<{outcome: RefreshOutcome}>` with a
sentence on single-flight semantics belongs here. The twenty lines that implement it do not.
When a contract's *meaning* isn't obvious from its shape, spend the words on the semantics —
what it guarantees, what it never does — not on the code.

## Data model

If the change touches persisted state. Entity relationships, invariants the system maintains,
what gets written when. Call out anything affecting existing rows: migrations, backfills,
default values, and whether the change is reversible.

## Behavior

The interesting cases — happy path, each failure mode, the edges (empty input, max-size
input, concurrent calls, retry semantics, partial failures). One short paragraph or bullet
per case. This section is where the reviewer earns their keep, so don't compress it.

## Observability

What we'll be able to see in production. New logs, metrics, traces, dashboards — and which
existing ones already cover this. If the codebase has no telemetry layer to extend, say so
rather than inventing one.

## Security / compliance

Anything load-bearing: authz checks, PII handling, audit entries, rate limits, secrets.
Skip the section entirely if genuinely not applicable; don't pad with "N/A".

## Open questions

If any survived discovery and drafting. Each one blocks the plan until resolved.

## Review record

**Reviewers:** <one line, always present — see the provenance stamp in
`references/reviewer-prompts.md`. e.g. `sonnet ✓ · codex not requested`>

Then a short bullet list of the substantive changes made from reviewer feedback. Keeps the
audit trail without bloating the body. If reviewers found nothing substantive, say that.
```

## Version notes

On a revision, open the document with a one-line `**v<N> change:**` summary pointing at what
moved and why. It's how the human re-reads a v2 without diffing 300 lines.
