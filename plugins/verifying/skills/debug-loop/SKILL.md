---
name: debug-loop
description: Use this skill whenever something is broken — "this is broken", "why is X failing", "debug this", "it's not working", a test is red, a build is failing, a runtime exception appeared, or execute-plan / ui-validation / verify-before-done hands off a failure bundle. Drives a reproduce-localize-hypothesize-fix sequence that confirms root cause before touching code. Skip only if the user says "just revert it", "I'll debug this myself", or "skip the analysis" — or if the failure is obviously a missing environment variable the user already knows they need to set.
---

# Debug Loop

Replace guess-and-patch with disciplined root-cause analysis. Work through a reproducible, evidence-driven sequence that finds the actual cause before touching the fix. The loop terminates either with a confirmed fix and a clean verify pass, or with an honest dossier of what was investigated and what remains unexplained.

**Announce at start:** "Using debug-loop to find the root cause of `<symptom>` before changing anything."

## When to trigger

- "this is broken", "why is X failing", "debug this", "it's not working"
- execute-plan hits a non-zero exit, a test assertion failure, or an unhandled exception during a task
- ui-validation hands off a failure bundle ("UI failure on `/dashboard`. Symptom: …")
- verify-before-done encounters a failing lint/typecheck/test step

Opt-out: "just revert it", "I'll debug this myself", "skip the analysis", or if the failure is an obviously missing environment variable the user already knows they need to set.

## Inputs

The skill needs enough context to reproduce the failure without guessing. In order of preference:

1. **The failure artifact** — full error output, stack trace, or test runner output. Truncated is not enough; ask for the full output if it was cut.
2. **What was being attempted** — the task from the highest-N `plan.v*.md`, or the user's description of what they ran and expected.
3. **What changed recently** — git diff since the last green state, or the task boundary from execute-plan.
4. **The active workspace** — if a `.claude-plans/<active-dir>/` is present (resolved via the algorithm below), read `handoff.md` for repo orientation and `decisions.md` for prior choices that might be relevant.
5. **Caller flag** — when invoked by another skill, accept `caller=<skill-name>` as a parameter. Store it; it gates Phase 6 and is noted in any decision-log entry written in Phase 7.

If any of the first three is missing when invoked from chat, ask for them before starting. If invoked programmatically by execute-plan or ui-validation, those callers are responsible for passing the bundle.

## Active-workspace resolution

**Active-workspace resolution** (canonical, shared across all sibling skills):
1. If the caller passes `WORKSPACE_PATH` (explicit absolute path), use it — no discovery.
2. Otherwise enumerate `.claude-plans/*/` in the repo root (or cwd if not in a git repo).
3. Filter to directories containing `plan.v*.md` or `spec.v*.md` (blueprint writes only versioned artifacts, never bare `plan.md`/`spec.md`). When a skill needs "the plan" or "the spec", use the highest-N version.
4. Exactly one match → use it.
5. Multiple → prefer the one whose slug contains the current branch's ticket key (branch `MSP-7032/foo` → workspace with `MSP-7032` in slug).
6. Still multiple → most recent by mtime of the newest `plan.v*.md` (fall back to dir mtime).
7. Zero → ad-hoc mode, no workspace. Ad-hoc artifacts go under `./.claude-results/<YYYY-MM-DD-HHMMSS>/<skill-name>/` (gitignored).

## Phase 1: Reproduce

Goal: confirm the failure is deterministic before investing in localization. A failure you can't reproduce reliably can't be fixed confidently.

Run the minimal command that should trigger the failure. If it reproduces: proceed. If it doesn't: investigate whether the first failure was environment-dependent (missing env var, stale build artifact, race condition).

**Intermittent failures** are characterized, not punted:

1. Rerun the failing command up to N=5 times within a **90-second total wall-clock budget**, noting the failure rate and any pattern (fails only on iteration 2, only under load, only after another test, etc.). If 90s elapses first, surface partial results: "ran N=`<x>` within 90s budget, observed `<y>` failures, `<z>` passes — proceeding with partial characterization." Do not exceed the budget.
2. Attempt determinization: seed RNG, mock the clock (`Date.now`, `time.time`), disable framework retries, isolate from parallel execution. Rerun under the same 90s budget.
3. If still non-deterministic: surface a characterization report (rate, variance, what you tried, what you suspect) and ask the user how to proceed. A flaky test can falsely confirm a wrong hypothesis — do not move to root-cause work until reproduction is reliable.

## Phase 2: Localize

Goal: narrow to the smallest context in which the failure occurs. The smaller the case, the fewer variables a hypothesis has to explain.

Localization technique depends on the failure class — pick the matching playbook:

- **Playbook T — Test failure:** isolate the failing assertion, check the diff since the last green SHA, run the test file alone before the suite, comment out cases to find the minimal failing one (every disabled/commented-out case gets a `DEBUG-LOOP-TEMP` marker comment — see Phase 6).
- **Playbook B — Build / compile failure:** fix the first error in the output (the rest is cascade), check imports and type signatures at that file. Error *count* is not a severity signal.
- **Playbook R — Runtime exception:** read the stack trace top-to-bottom, find the first frame in code you own, check recent changes to it, trace any value named in the exception message backward to where it was set.
- **Playbook W — Wrong output, no exception:** narrow the input to the smallest one that misbehaves; add a temp observation point (see Phase 6 sentinel) before the output; diff expected vs. actual precisely ("off by one", not "wrong").

Full per-class detail with concrete commands and examples is in `references/playbooks.md`.

## Phase 3: Hypothesize

Goal: articulate the candidate root causes before testing any of them. The discipline here is the most important part of the skill — the natural LLM behavior is to jump to the first plausible explanation and start changing code. That's how you end up with a "fix" that masks the symptom without touching the cause.

**The constraint:** write down all hypotheses before executing any probe. Track hypotheses-in-flight via TodoWrite so the cap is enforceable.

**A hypothesis round** = one hypothesis table (2–3 hypotheses), fully tested — every row confirmed, falsified, or resolved-ambiguous in Phase 4. If a round ends without confirmation, going back to Phase 2 and writing a fresh table starts a new round. Maximum three rounds; after the third, produce the exhaustion report (see Termination conditions) — no fourth table.

Use this table:

```
| # | Hypothesis                              | Cheapest probe                    | Expected if true                        |
|---|---------------------------------------- |-----------------------------------|-----------------------------------------|
| 1 | <root cause candidate>                  | <command, log, read, print>       | <what we'd observe if this is correct>  |
| 2 | <second candidate>                      | <command, log, read, print>       | <what we'd observe if this is correct>  |
| 3 | <third candidate>                       | <command, log, read, print>       | <what we'd observe if this is correct>  |
```

Aim for 2–3 hypotheses. Having only one means you haven't considered alternatives; having five usually means you're speculating without evidence and should localize more before hypothesizing.

**Prediction before observation:** for each hypothesis, write the expected observation *before* running the probe. If you run a probe and the observed output matches neither the "true" column nor an obvious "false" case, the probe was underspecified — you learned nothing. Re-design the probe before proceeding.

The first hypothesis is usually the most tempting to act on. Resist. The cheapest probe is often `read the code` or `print one value` — not `make the change`.

## Phase 4: Test cheapest first

Test in order of cheapest probe first. "Cheap" means: reads and prints before code changes, assertions before deployments, local before remote.

For each hypothesis in order:
1. Run the probe as specified.
2. Compare observed output to the expected prediction.
3. If observed matches "true" expectation: root cause confirmed, proceed to Phase 5.
4. If observed doesn't match "true" expectation: mark hypothesis falsified. Move to the next.
5. If observed is ambiguous (matches neither "true" nor "false" column): the probe was uninformative. Note why, redesign the probe, run again. This is not a free hypothesis skip.

MUST NOT modify production code during hypothesis testing. Temporary observations (prints, logs) are fine — track them with `DEBUG-LOOP-TEMP` (see Phase 6). Code changes before root cause is confirmed introduce new variables and contaminate the signal.

If all hypotheses are exhausted without confirmation, do not generate more hypotheses from thin air. Go back to Phase 2 (localize further) or move to termination (see Termination conditions).

## Phase 5: Fix at root

With root cause confirmed, write a fix that addresses the cause, not the observation point.

- One change at a time. If fixing the root cause requires touching two unrelated files, that's a signal the root cause is at a higher level of abstraction — find it.
- Match the scope of the fix to the scope of the cause. A typo in a config key is a one-line fix. A wrong assumption baked into three call sites is three call sites (not a try/catch wrapper around the caller).
- Do not bundle cleanup, refactoring, or "while I'm in here" improvements into the fix. Those are separate commits with separate context. Mixing them makes the fix diff harder to review and creates risk that a well-intentioned cleanup re-introduces the bug.

## Phase 6: Verify

Run the same reproduction command from Phase 1. The failure must not occur. Then run the broader test suite for the affected module to confirm no regression was introduced.

**Tracking temporary mutations.** Any `print`, `console.log`, `logger.debug`, or debugger statement added during hypothesis testing MUST embed the literal sentinel string `DEBUG-LOOP-TEMP`:

```
print(f"DEBUG-LOOP-TEMP: user_id={user_id}")           # Python
console.log('DEBUG-LOOP-TEMP:', value);                // TypeScript/JavaScript
fmt.Printf("DEBUG-LOOP-TEMP: %v\n", val)               // Go
System.out.println("DEBUG-LOOP-TEMP: " + val);         // Java
```

The same sentinel covers **test mutations**: any test case disabled, skipped, or commented out during localization (Playbook T's minimal-case narrowing, `.skip`, `@pytest.mark.skip`, commented blocks) gets a `DEBUG-LOOP-TEMP` marker comment on the mutated line. Disabled tests must be restored before done.

Before declaring verify complete, grep for `DEBUG-LOOP-TEMP` across all modified files — source AND tests. NEVER declare done while any sentinel is present — it is a verification failure, not a minor omission.

**ui-validation after a frontend fix:**
- If `caller=ui-validation` was passed when debug-loop was invoked: do NOT invoke ui-validation in Phase 6. Surface the fix to the user: "ui-validation called us — not looping back. Please re-run your validation to confirm the fix."
- Otherwise, if a `ui-validation` sibling is installed and the fix touched frontend code: invoke it now against the affected surfaces, passing `caller=debug-loop`. When `caller=debug-loop`, ui-validation runs **headed** (pinned convention — the user is actively debugging and wants to see the browser). If ui-validation is not installed, print: "if `ui-validation` were installed I'd run a browser check here" and continue.

## Phase 7: Log decision

If a `.claude-plans/<active-dir>/` workspace is active (resolved via the canonical active-workspace algorithm), append to `decisions.md`. If not, print the decision entry to chat.

**Write a decision log entry when any of these are true:**
- The fix is in a different module than the symptom (symptom was in the API handler; fix was in the data mapper two layers down).
- More than one hypothesis was needed to find the cause.
- The bug was masked by a prior workaround that had to be unwound.
- A previously trusted assumption turned out to be wrong (e.g., "this value is always an integer" — it wasn't).

The entry follows the same ADR format as blueprint's `decisions.md`:

```markdown
## YYYY-MM-DD — Root cause: <short title>
**Symptom:** <what failed and where>
**Root cause:** <what actually caused it>
**Fix:** <what changed and why that addresses the cause>
**Alternatives rejected:** <any fix approach considered and discarded>
**Why non-obvious:** <why this wouldn't be found by reading the error alone>
**Caller:** <skill that invoked debug-loop, or "chat" if invoked directly>
```

If the failure was obvious (typo, missing import, obvious off-by-one), skip the log entry. The decisions log is for knowledge that would help a future reader understand why the code looks the way it does, not a running tally of every bug closed.

**Propose a knowledge-capture entry** when the decision-log entry was written AND any of:
- The fix was in a different module than the symptom.
- More than one hypothesis was needed.
- A previously trusted assumption turned out to be wrong.

Invoke `knowledge-capture` (if installed) with payload:

```yaml
caller: debug-loop
kind: gotcha
proposed:
  title: <slugified version of the decision-log "Root cause" title, ≤80 chars>
  context: <one sentence — the symptom + where it appeared>
  lesson: <one or two sentences — the takeaway from "Why non-obvious">
  tags: [<extracted from modules/files involved, max 4>]
source:
  files: <list from `git diff --name-only HEAD~..HEAD` over the fix commit>
  commit: <`git rev-parse HEAD`>
  session_marker: "debug-loop-<reproduction-symptom-slug>"
```

knowledge-capture batches these in interactive mode (one prompt at session end) or queues them to `.claude-plans/<active>/open-questions.md` in auto mode. Do NOT prompt the user in this skill — knowledge-capture owns the user interaction. If `knowledge-capture` is not installed, print "if `knowledge-capture` were installed I'd propose saving this gotcha for next time" and continue.

## Termination conditions

**Success:** root cause confirmed, fix applied, Phase 6 verify passed, no `DEBUG-LOOP-TEMP` sentinels remain. The loop ends.

**Out-of-scope cause:** root cause is in a dependency, upstream service, or infrastructure layer the skill can't modify (see Upstream / out-of-scope causes). The loop ends with a handoff dossier.

**Hypothesis exhaustion:** three hypothesis rounds without a confirmed root cause. The skill does not escalate to guessing. Instead, produce an exhaustion report:

```
debug-loop — exhaustion report
────────────────────────────────────
Failure: <one-line description>
Reproduction: <reliable? intermittent at N%?>
Localized to: <narrowest failing case found>

Hypotheses tested:
  H1 [falsified] <statement> — probe: <what we ran> — observed: <what we saw>
  H2 [falsified] <statement> — probe: <what we ran> — observed: <what we saw>
  H3 [ambiguous] <statement> — probe: <what we ran> — observed: <what we saw, why inconclusive>

What we know: <the evidence gathered, as a short bulleted list>
What we don't know: <what would need to be true for this to make sense>
Suggested next steps: <more invasive probe / ask upstream maintainer / open issue>
```

Surface this to the user and stop. Do not append speculative hypotheses to seem helpful. The dossier is the output.

**Architectural signal:** if three or more fix attempts fail in ways that each reveal new coupling or side effects in different parts of the codebase, the bug is likely a symptom of structural debt, not a localized defect. Stop, surface the pattern, and recommend the user run `blueprint` to scope a proper fix.

## Upstream / out-of-scope causes

When localization lands in a library, a dependency, or infrastructure that the skill can't modify:

1. **Confirm it's actually upstream** — reproduce the failure against the library's public API directly, isolated from your code. If you can't reproduce it in isolation, the cause is in how you're calling the library, not the library itself.

2. **Identify a safe workaround vs. an unsafe one.** A workaround is safe if it doesn't change observable behavior for end users, doesn't add tech debt that's hard to remove, and is clearly marked with a comment pointing at the upstream issue. An unsafe workaround is one that silently changes behavior or papers over a data integrity problem.

3. **Produce the handoff dossier:**
   - Exact version of the dependency where the bug appears
   - Minimal reproduction that doesn't involve your application code
   - Which version (if any) doesn't exhibit the bug (from `git blame` or changelog)
   - Safe workaround if one exists
   - Link to the upstream issue tracker or maintainer contact

4. **File or surface the upstream issue** — write the minimal reproduction as a GitHub issue body. If the `mcp__claude_ai_Atlassian__*` tools are available and it's an internal dependency, file it via JIRA instead.

The loop ends after the dossier is produced. The user decides whether to apply the workaround or wait for an upstream fix.

## Anti-patterns

These are the default LLM debugging behaviors — each makes the failure harder to understand and the fix harder to trust.

- **Random fix-and-rerun** — write the hypothesis and expected observation first; a change without a prediction is a coin flip.
- **Patching the test instead of the code** — the test documents a contract; fix the code that returns the wrong value.
- **try/except swallowing** — understand why the exception is thrown; handle it correctly or fix the caller, never `except: pass`.
- **Loosen the assertion** — fix the output; don't widen an exact-match gate to let wrong output through.
- **`git revert` until green without understanding** — bisect to the introducing commit and read that diff instead.
- **Scope creep during debug** — make the surgical fix only; open a new task for cleanup or refactors.
- **First hypothesis is the only hypothesis** — form 2–3 hypotheses before testing any; the table enforces this.
- **"One more fix attempt" after exhaustion** — past three rounds you're guessing; produce the exhaustion report and stop.
- **Catch-and-log instead of fix** — fix the condition or propagate the error; don't convert a loud failure into a silent one.

## Composition

- **Called by:** execute-plan (on task failure), ui-validation (on browser check failure), verify-before-done (on gate failure), ci-check-triage (on a real CI check failure), pr-review-triage (on a verify failure after applying a review fix). Each caller is responsible for passing the failure bundle (error output + what was being attempted + what changed) and a `caller=<skill-name>` parameter.
- **Calls:** ui-validation (at end of Phase 6 if frontend code was modified and ui-validation is installed, passing `caller=debug-loop` — runs headed); `knowledge-capture` (Phase 7, when the conditions for proposing an entry are met, passing `caller=debug-loop`). When a decisions.md entry is written, print it in chat and note the file path so the user can open it.
- **Reads:** `.claude-plans/<active-dir>/handoff.md` and `decisions.md` for repo context; the highest-N `plan.v*.md` for task scope; changed files via git diff.
- **Writes:** `DEBUG-LOOP-TEMP` sentinels during hypothesis testing (removed before verify completes); decision log entry to `.claude-plans/<active-dir>/decisions.md` when applicable; exhaustion report to chat when terminating without resolution. Proposes (but does not write directly) `knowledge-capture` entries — that skill owns the user interaction.

If a sibling is not installed: print a one-line notice ("if `ui-validation` were installed I'd run a browser check here") and continue. Cycle-guard via the standard `caller=<skill-name>` parameter; workspace resolution per the Active-workspace resolution section above.

## Open questions

1. **Hypothesis table format.** Plain markdown table vs. a structured block the skill populates incrementally. The table is easier for the user to read mid-session; a structured block is easier for a downstream subagent to parse. Leaning: markdown table for now; revisit when execute-plan's subagent mode is fully designed.
2. **N for intermittent failure characterization.** Five runs was chosen to balance signal vs. cost. For fast unit tests that's cheap; for slow integration tests it could be expensive. Caller can pass `max_flaky_runs` to override; default N=5.
