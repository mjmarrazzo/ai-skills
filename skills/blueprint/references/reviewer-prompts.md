# Reviewer prompts

Two reviewers, dispatched in parallel on a complex spec (one of them on a medium spec). They review the same `spec.md` independently — don't show them each other's feedback. You (opus, the orchestrator) reconcile.

Both reviewers receive the same inputs:

- The full text of `spec.md`.
- The full text of `handoff.md` (for context, constraints, and out-of-scope decisions).
- A pointer to the workspace root and the repo root, so they can read source files they need.
- The reviewer-specific prompt below.

## Why two reviewers, and why these two

- **Sonnet subagent** (via `Agent` tool, `subagent_type: general-purpose`, `model: sonnet`): fresh perspective, no context contamination from this session. Catches things opus missed because it drafted the spec and is anchored on it. Cheap and fast.
- **Codex MCP** (via `mcp__codex__codex`): a different model family — different training, different failure modes, different blind spots. The point isn't "two opinions are better than one" — it's that **independent failure modes are better than redundant ones**. If both reviewers flag the same thing, that's a strong signal. If they disagree, that's where the interesting reconciliation happens, and the conflict goes in `decisions.md`.

If only one reviewer is warranted (medium complexity), use the sonnet subagent. The codex round-trip costs more and is best reserved for genuinely high-stakes specs.

## Dispatch — parallel, same message

When running both, send the `Agent` tool call and the `mcp__codex__codex` call **in the same message**. The reviewers run concurrently, which is the whole point.

## Reviewer prompt — sonnet subagent

```
You are reviewing an engineering spec for accuracy, completeness, and architectural soundness.
You are NOT writing code, not implementing, not drafting an alternate spec. You are reviewing.

Inputs:
- Spec: <path to spec.md>
- Handoff (context, constraints): <path to handoff.md>
- Repo root: <path>

Read the spec, then read the handoff for context, then read whatever source files the spec
references that you need to verify claims about existing code. Do NOT explore the whole repo
— stay focused on what the spec actually touches.

Report under 600 words, in this structure:

## Substantive concerns
Things that, if not addressed, would produce a broken or significantly worse implementation.
Each item: one sentence stating the concern, one sentence on why it matters, one sentence on
what to change. If none, write "None".

## Risk flags
Things that aren't outright wrong but increase risk: ambiguity that will cause divergent
implementations, irreversible decisions made implicitly, missing failure-mode coverage,
observability gaps. Same format as above.

## Verification gaps
Claims the spec makes about existing code that you couldn't verify, OR claims you verified
and found inaccurate. Cite file:line.

## Out of scope / not your call
Anything you noticed but is a matter of taste, not correctness. Brief bullets, no analysis.
This section trains the orchestrator to weight your other sections more heavily.

If the spec is solid, say so plainly. Don't manufacture concerns to look thorough.
```

## Reviewer prompt — codex MCP

The codex MCP accepts a prompt and runs autonomously. Use the same review framing but tuned for codex's strengths (deep code-grounded analysis):

```
Review the engineering spec at <path to spec.md>.

Context for the review: <path to handoff.md>. The spec describes a change to a codebase
rooted at <repo root>. You may read any files the spec references; do not explore the
whole repo.

Your job is to find specific, actionable problems. Not style commentary, not "consider
also X" speculation. For each concern:

1. State the concern in one sentence.
2. Quote the spec text (or the source-file text) that's the problem.
3. State what the spec should say instead, concretely.

Cover, in this order:
- Architectural soundness: does the proposed design actually solve the stated goal? Are
  there well-known patterns that fit better? Are any of the components doing too much?
- Contract / interface correctness: do the proposed contracts compose with existing
  code at the integration points? Cite file:line for every claim about existing code.
- Failure modes and edge cases: what cases does the spec not cover? Retry semantics,
  partial failures, concurrent calls, empty / oversized inputs, auth edge cases.
- Data integrity: if persisted state is touched, is the migration / backfill strategy
  safe under concurrent writes? Are invariants preserved?
- Observability and operability: when this is in production at 3am, what does the
  on-call engineer see? Is it enough?

Cap your output at 800 words. If the spec is solid, say so — don't pad.
```

## Reconciliation (orchestrator's job, opus session)

After both reviewers respond:

1. **Union the concerns.** Any item raised by either reviewer is on the table.
2. **Dedupe.** If both flagged the same thing, note it as high-confidence in `decisions.md`.
3. **Filter against handoff constraints.** If a reviewer suggested something that contradicts a user-stated constraint, drop it and note why in `decisions.md`.
4. **Apply changes directly to `spec.md`.** Don't ask the user to mediate reviewer feedback — that's the orchestrator's job. The user sees the result at the spec gate.
5. **Append a "Reviewer notes folded in" bullet list** to the bottom of `spec.md` summarizing what changed.
6. **Log every non-obvious resolution in `decisions.md`**, especially places where reviewers disagreed.

The user reviews the post-reconciliation `spec.md`, not the raw reviewer output. They're the gatekeeper, not the referee.
