# Reviewer prompts

Blueprint reviews at **two gates**, and the two reviews have deliberately different lenses:

| Gate | Document | Lens |
|---|---|---|
| Phase 3 (before the spec gate) | `spec.v<N>.md` | **Is this the right shape?** Architecture, blast radius, alternatives, failure-mode coverage. |
| Phase 5b (before the plan gate) | `plan.v<N>.md` | **Does this shape get built correctly and completely?** Spec coverage, name consistency, missing traps, missed deletions, gate honesty. |

**Default is one `sonnet` subagent per gate.** Two gates × one reviewer covers architecture *and* mechanism, which beats two reviewers double-covering architecture at one gate for roughly the same spend.

Cross-family reviewers (codex, LM Studio) are an **opt-in escalation** for genuinely high-stakes work — irreversible migrations, auth/authz changes, anything with a blast radius past one service. See "Escalation reviewers" below.

Every reviewer receives:

- The full text of the document under review.
- The full text of `spec.v<N>.md` when reviewing a plan (the plan is judged against it).
- A pointer to the workspace root and the repo root, so they can read source files to verify claims.
- The reviewer-specific prompt below.

Reviewers never see each other's feedback. The orchestrator (opus) reconciles.

Do **not** hand a reviewer `handoff.md` at the plan gate. By then the spec carries the constraints; the handoff adds tokens and a second, possibly stale, copy of the contract.

## Provenance stamp (mandatory)

Every reviewed document carries a one-line stamp in its review section, so a reader can tell months later what actually looked at it. Never omit it, and never imply a reviewer ran when it didn't:

```
**Reviewers:** sonnet ✓ · codex not requested
**Reviewers:** sonnet ✓ · codex ✓ (escalated: irreversible migration)
**Reviewers:** sonnet ✓ · codex skipped (usage gate) · LM Studio unreachable — single-reviewer round
**Reviewers:** none — sonnet subagent failed twice; document is UNREVIEWED
```

The last form must also be stated out loud at the gate. An unreviewed document is the human's call to accept, not the orchestrator's to hide.

## Reviewer prompt — spec review (sonnet subagent)

Dispatch via `Agent`, `subagent_type: general-purpose`, `model: sonnet`.

```
You are reviewing an engineering spec for accuracy, completeness, and architectural soundness.
You are NOT writing code, not implementing, not drafting an alternate spec. You are reviewing.

Inputs:
- Spec: <path to spec.v<N>.md>
- Handoff (context, constraints): <path to handoff.md>
- Repo root: <path>

Read the spec, then the handoff for context, then whatever source files the spec references
that you need to verify claims about existing code. Do NOT explore the whole repo — stay
focused on what the spec actually touches.

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
Anything you noticed that's a matter of taste, not correctness. Brief bullets, no analysis.
This section trains the orchestrator to weight your other sections more heavily.

If the spec is solid, say so plainly. Don't manufacture concerns to look thorough.
```

## Reviewer prompt — plan review (sonnet subagent)

Dispatch the same way, at Phase 5b. This reviewer's job is **not** to re-litigate the architecture — that gate has closed. It judges the plan as an executable artifact.

```
You are reviewing an implementation plan against the spec it implements. The architecture is
already approved and NOT up for debate — do not propose a different design. Judge whether
this plan, executed literally by a competent but codebase-ignorant model, produces the
change the spec describes.

Inputs:
- Plan: <path to plan.v<N>.md>
- Spec (the approved contract): <path to spec.v<N>.md>
- Repo root: <path>

The plan deliberately does NOT contain finished code — it carries intent, contracts,
traps to avoid, and verification commands. Do not flag the absence of pasted
implementations or pasted test bodies; that is the format working as intended.

Read the plan, then the spec, then the source files the plan says it modifies. Verify that
the paths and line ranges actually exist and contain what the plan claims.

Report under 700 words, in this structure:

## Coverage gaps
Spec sections with no task implementing them, or tasks that only partially deliver one.
Cite the spec section and say which task should own it.

## Executability failures
Places a literal executor would get stuck, guess, or do the wrong thing: a Contract naming
something no task defines, a path or line range that doesn't match the repo, a Verify step
with no command or no expected result, an ambiguous instruction with two reasonable readings.
Quote the plan text.

## Missing traps
Existing behavior an executor would plausibly "clean up" or refactor away that must be
preserved, and that the plan does not warn about. This is the highest-value section — cite
file:line for the code at risk.

## Missed deletions and side effects
Code the change orphans (now-unused modules, dead imports, stale config, obsolete tests)
that the file map doesn't list. Also: callers of a changed signature that no task updates.

## Tag and gate honesty
Any task tagged `auto` that actually touches a live system, costs money, mutates shared
state, or needs human judgment. Any task whose kind tag implies verification the task
doesn't do. Whether the stated autonomy frontier is really the first non-auto task.

## Test adequacy
Named test cases that wouldn't actually catch the failure they imply, cases the spec's
Behavior section describes that no test covers, and mock seams chosen so shallow the test
asserts nothing real.

If the plan is solid, say so plainly. Don't manufacture concerns to look thorough.
```

## Escalation reviewers (opt-in)

Add a second, cross-family reviewer when the work is genuinely high-stakes. The point isn't "two opinions beat one" — it's that **independent failure modes beat redundant ones**. Agreement between families is a strong signal; disagreement is where the interesting reconciliation happens, and it goes in `decisions.md`.

Either escalation reviewer can target the spec or the plan; swap the document paths and use the matching lens from the prompts above.

### Codex MCP

**Usage gate — check first:** `test -f ~/.claude/state/blueprint-codex.off`. If the flag is present, codex is off; either escalate with LM Studio instead or proceed with the single sonnet reviewer, and record it in the provenance stamp. Deleting the flag re-enables codex.

When available, send the `Agent` call and the `mcp__codex__codex` call **in the same message** — both are remote, so they run concurrently. Pin model and effort so codex doesn't inherit a frontier default:

```
model: "gpt-5.4"
config: { model_reasoning_effort: "high" }
sandbox: "read-only"
prompt: <prompt below>
```

```
Review the engineering document at <path>.

The approved spec it must satisfy is at <path to spec.v<N>.md>. The change targets a
codebase rooted at <repo root>. You may read any files the document references; do not
explore the whole repo.

Find specific, actionable problems. Not style commentary, not "consider also X"
speculation. For each concern:

1. State the concern in one sentence.
2. Quote the document text (or the source-file text) that's the problem.
3. State what it should say instead, concretely.

Cover, in this order:
- Architectural soundness: does the design actually solve the stated goal? Do well-known
  patterns fit better? Is any component doing too much?
- Contract correctness: do the proposed contracts compose with existing code at the
  integration points? Cite file:line for every claim about existing code.
- Failure modes and edge cases: what's uncovered? Retry semantics, partial failures,
  concurrent calls, empty / oversized inputs, auth edges.
- Data integrity: if persisted state is touched, is the migration / backfill safe under
  concurrent writes? Are invariants preserved? Is it reversible?
- Observability and operability: at 3am in production, what does the on-call engineer see?
  Is it enough?

Cap output at 800 words. If the document is solid, say so — don't pad.
```

### LM Studio MCP

A local model — free and private, weaker than codex on deep code-grounded analysis. Useful when codex is gated off and the work still warrants a cross-family look. Weight its findings lower in reconciliation.

**Never dispatch it in the same message as the sonnet Agent call or any other local inference.** It runs on the user's machine and concurrent local inference risks resource contention — a hard constraint, not a style preference. Send it in its own message, before or after the sonnet call.

Verify the server first: `mcp__llm-studio__model_list`. If it errors or shows no loaded model, treat it as a reviewer failure and record that in the provenance stamp rather than retrying blind.

```
mcp__llm-studio__ask
model: <whatever model_list shows loaded — don't hardcode>
reasoning: "high"
prompt: <prompt below>
```

`mcp__llm-studio__ask` has **no filesystem access** — it sees only the prompt string. Read the document, the spec, and any needed source excerpts yourself and inline them, clearly delimited.

```
Review this engineering document for a codebase change. You cannot read any files beyond
what's pasted below — do not reference files by path, only comment on what's shown to you.

Find specific, actionable problems. Not style commentary, not "consider also X"
speculation. For each concern:

1. State the concern in one sentence.
2. Quote the text that's the problem.
3. State what it should say instead, concretely.

Cover, in this order:
- Architectural soundness: does the design actually solve the stated goal?
- Contract correctness: do the contracts make sense given the excerpted existing code below?
- Failure modes and edge cases: what's uncovered? Retry semantics, partial failures,
  concurrent calls, empty / oversized inputs, auth edges.
- Data integrity: if persisted state is touched, is the migration safe under concurrent
  writes? Is it reversible?
- Observability: at 3am in production, what does the on-call engineer see?

Cap output at 500 words. If the document is solid, say so — don't pad.

--- APPROVED SPEC (the contract) ---
<full contents of spec.v<N>.md>

--- DOCUMENT UNDER REVIEW ---
<full contents of the document>

--- RELEVANT EXISTING CODE ---
<inlined excerpts, file:line headers, only what's needed>
```

## Reconciliation (orchestrator's job, opus session)

Same procedure at both gates:

1. **Union the concerns.** Anything either reviewer raised is on the table.
2. **Dedupe.** Agreement between reviewers is high-confidence; note it in `decisions.md`.
3. **Filter against constraints.** Drop anything contradicting a user-stated constraint in `handoff.md` and note why in `decisions.md`.
4. **At the plan gate, filter against the approved spec.** A plan reviewer arguing for a different architecture is out of bounds — that gate closed. If the argument is strong enough to matter, surface it to the human as a *spec* concern rather than silently reworking the plan around it.
5. **Apply changes directly to the current document.** Don't ask the user to mediate reviewer feedback; that's the orchestrator's job. Reconciliation does not bump the version number — it's part of producing the current version.
6. **Write the provenance stamp** and append the substantive-changes bullet list.
7. **Log every non-obvious resolution in `decisions.md`**, especially reviewer disagreements.

The user reviews the post-reconciliation document, not raw reviewer output. They're the gatekeeper, not the referee.
