# plan.v<N>.md template

The plan is the **executor's** document. The spec settled *what* and *why*; the plan settles *where, in what order, and how we know it worked*.

Optimize for one property: **a weaker model, or you six weeks from now, can execute a task without thinking architecturally and without exploring the repo to figure out what was meant.**

## What that does NOT mean: pasting the implementation

Do not write out finished function bodies, full test files, or complete components. Paste-ready code is the weakest form of executor help:

- **It goes stale.** Code in the plan and code in the spec drift the moment either is revised, and the executor then has to reconcile plan-code against actual repo state — that is *more* thinking, not less.
- **It produces fake TDD.** When the test body and the implementation body are both written up front, the test was shaped to match the implementation instead of constraining it. The red/green run becomes theater.
- **It crowds out the useful part.** Tokens spent re-typing an obvious mapping function are tokens not spent naming the trap that will actually break the executor.

What removes thinking from a weaker executor, in order of value:

1. The **exact path** (and line range when modifying), so it never searches.
2. The **contract** — signature level. Names and types the rest of the plan depends on.
3. The **traps** — what to preserve, what not to collapse, what looks refactorable but isn't.
4. The **verification** — exact command, expected result, expected pre-implementation failure.

Prose describing intent, plus those four, beats a pasted body nearly every time.

### When code IS worth pasting

Heuristic: **if the prose describing it would be longer than the code, paste the code.** In practice that means:

- A regex, format string, or magic constant where exactness matters.
- SQL DDL / a migration statement.
- A config or YAML block that must match an external schema.
- A short (~5 line) algorithm where the description is genuinely harder to follow than the lines.

Everything else: describe it.

### Pasted blocks carry no comments

A code block in the plan is paste-ready, and an executor will paste it verbatim — comments and all. So the plan's *why* goes in the plan's prose, in `Preserve:` lines, and in `decisions.md` — never as comment text baked into a block to paste. A four-line rationale that reads well in the plan lands in the PR as comment noise on a file whose own idiom is one terse line, and it goes stale the moment the code moves.

Two failure shapes to watch for, both from real plans: a comment warning against an approach nobody took (planner voice, meaningless at the code site), and a comment that names the very flag or string a `Verify:` step greps for (the plan's own comment breaks the plan's own check).

When a rationale genuinely is load-bearing *at the code site*, instruct rather than pre-write: `Add a one-line comment noting the tenant namespace is separate from the distribution.` The executor writes it in the file's voice, at the file's density.

## Header

```markdown
# <Slug> — Implementation Plan

> Spec: `spec.v<N>.md` (current highest). Decisions: `decisions.md`.

**Goal:** <one sentence>
**Approach:** <2-3 sentences summarizing the architecture from the spec>
**Stack / verify:** <key libraries, plus the commands that gate this repo — e.g. `npm run typecheck && npm run lint`>

**Autonomy frontier: Tasks 1–<K> run unattended. Task <K+1> needs you (<gate reason>).**

---
```

The **autonomy frontier** is the first task whose gate is not `auto`. State it once, up top, in plain language. It is the line that tells the human how far they can walk away — it is the most-read sentence in the document.

Order tasks so the frontier sits as late as possible: pure work first, then I/O, then anything needing eyes, credentials, or money. Where dependencies allow it, this is free; where they don't, say so rather than faking the order.

## File map

Every file the plan creates, modifies, or deletes — before any task detail. Locks in decomposition, and carries the **contracts** so later tasks can reference names without redefining them.

```markdown
## Files

- Create `src/auth/refresh.ts` — `classifyRefresh(status, errorCode?) → "refreshed"|"terminal"|"transient"` (pure)
- Create `src/auth/refresh.client.ts` — `refreshSession(): Promise<{outcome}>`, single-flight, bounded retry
- Modify `src/api/fetch.client.ts:18-34` — 401 branch → refresh / replay / terminal / transient
- Delete `src/api/legacy-retry.ts` — superseded by `refreshSession`; confirm no importers first
- Test   `src/auth/refresh.test.ts` — classifier cases
```

`Delete` is a first-class row. Deletions are the most commonly missed part of a change; if nothing is deleted, write `- Delete <none>` so the reader knows it was considered.

## Task tags

Every task carries a **kind** and a **gate**.

```markdown
### Task 4 — apiFetch 401 branch  `[io]` `[gate: auto]`
```

**Kind** — what the work *is*. Determines how it gets verified:

| kind | what it covers | verification | default gate |
|---|---|---|---|
| `pure` | no I/O; deterministic input → output | unit tests | `auto` |
| `io` | network, filesystem, DB, process boundary | unit tests with the boundary mocked, plus a named integration check | `auto` |
| `ui` | rendering, styling, layout, interaction | component test where meaningful + `ui-validation` screenshots | `eyes` |
| `infra` | IaC, CI YAML, Dockerfile, IAM, build config | plan/dry-run diff, or a lint/validate command | `review` |
| `migration` | schema change, backfill, one-shot script | dry-run against a copy; state the reversibility story | `live` |
| `codegen` | generated output | regenerate and confirm a clean diff | `auto` |

**Gate** — who has to look, and when execution stops:

| gate | behavior |
|---|---|
| `auto` | execute, verify, continue. No stop. |
| `review` | execute, then stop and show the diff before continuing. |
| `eyes` | execute, then stop with screenshots / output for human judgment. |
| `live` | stop **before** executing. Touches a real account, costs money, or mutates shared state. |

The kind implies a default gate. Override it when the specific task warrants — a `pure` task rewriting a security-critical predicate can be `[gate: review]` — and say why on the same line. Never silently downgrade a `live` or `migration` task to `auto`.

Because the kind already declares what verification applies, a task tagged `[infra]` or `[migration]` does not need to argue that unit tests don't fit. The tag says it.

## Task shape

Each task is one coherent unit — one module, one endpoint, one migration. Aim for something an executor finishes and commits in one sitting.

````markdown
### Task 4 — apiFetch 401 branch  `[io]` `[gate: auto]`

**Modify** `src/api/fetch.client.ts:18-34` (the 401 branch)

Replace the unconditional `invalidateQueries(["me"])` with: `refreshSession()` →
`refreshed` = replay the original request once (a second 401 is terminal, never
re-refresh) · `terminal` = `markSessionExpired()`, invalidate `["me"]`, throw
`"Session expired"` · `transient` = throw `"Session refresh unavailable"` with no
mark and no invalidate.

**Preserve:** `credentials: "include"` stays AFTER the `init` spread — a caller must
not be able to drop the cookie.

**Contract:** `refreshSession(): Promise<{outcome: RefreshOutcome}>` (Task 2).

**Test** `src/api/fetch.client.test.ts` — cases:
- refreshed → original request replayed exactly once
- replay returns 401 → treated as terminal, no second refresh
- terminal → marks expired, invalidates `["me"]`, throws
- transient → throws without marking or invalidating

Mock `refreshSession`, not `fetch` — the point is the branch logic, not the network.

**Verify:** `npx vitest run src/api/fetch.client.test.ts` → 4 pass.
Before implementing, the same command fails with `TypeError: refreshSession is not a function`.

**Commit:** `PROJ-XXXX: route apiFetch 401s through session refresh`
````

Sections, in order: the file line, the intent prose, `Preserve:` (when there are traps), `Contract:` (when later tasks depend on names), `Test:` (file + cases), `Verify:` (command + expected pass and expected pre-implementation failure), `Commit:`.

Drop any section that genuinely doesn't apply. Don't pad with headings.

## Test discipline

Tests come **before** the implementation. That rule is unchanged; only the verbosity is.

- **Name the test file and the cases.** One line per case, phrased as the assertion it makes. Four sharp case lines beat forty lines of pasted test body.
- **Name the seam.** What gets mocked, faked, or stubbed — and, when it's not obvious, why that seam and not a deeper one.
- **The expected pre-implementation failure is required.** Not "expect failure" — the actual failure (`TypeError: x is not a function`, `AssertionError`, HTTP 404). The executor needs to distinguish the *right* red from a broken setup.
- **Write the tests, run them red, then implement, then run them green.** One commit per red→green cycle unless tasks are tightly coupled.
- **Refactor comes after green**, never before.

Tasks tagged `infra`, `migration`, `codegen`, or `ui` (styling-only) verify per the kind table instead. State the concrete check — the dry-run command, the regenerate-and-diff, the screenshot surface. Never invent a unit test that doesn't actually exercise the change.

## No placeholders

Plan failures — never ship a plan containing them:

- "TBD", "TODO", "fill in later", "see spec"
- "Add appropriate error handling" without saying which errors and what happens
- "Write tests for the above" without naming the cases
- "Similar to Task N" — restate it; tasks get read out of order
- A `Contract:` referencing a name no earlier task defines
- A `Verify:` step with no command, or a command with no expected result

## Self-review

After drafting, read it once with fresh eyes:

1. **Spec coverage.** Walk each spec section; point at the task that implements it. Add tasks for gaps.
2. **Placeholder scan.** Grep the patterns above.
3. **Name consistency.** Every `Contract:` name matches what the defining task declared, and matches the spec.
4. **File map completeness.** Every path touched by a task appears in the map, including deletions.
5. **Frontier honesty.** Is the stated frontier actually the first non-`auto` task? Is any task tagged `auto` that really touches a live system, costs money, or needs a human eye?
6. **Test ordering.** Every behavioral task names its cases before its implementation prose, and every `Verify:` carries an expected pre-implementation failure.
7. **Trap coverage.** For each modified file: is there anything an executor would plausibly "clean up" that must not change? If yes, it needs a `Preserve:` line.

Fix inline. No second pass.

## Auto-mode notes

In autonomous mode, every non-trivial decision the executor rolls with instead of pausing goes to `.claude-plans/<active>/open-questions.md`. The plan doesn't enumerate these — they emerge during execution.

Auto mode does **not** override gates. A `live` task stops even in auto mode; the run reports that it stopped and why. Gates are a property of the work, not of the operator's patience.
