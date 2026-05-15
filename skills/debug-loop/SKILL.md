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
2. **What was being attempted** — the task from `plan.md`, or the user's description of what they ran and expected.
3. **What changed recently** — git diff since the last green state, or the task boundary from execute-plan.
4. **The active workspace** — if a `.claude-plans/<active-dir>/` is present (resolved via the canonical active-workspace algorithm), read `handoff.md` for repo orientation and `decisions.md` for prior choices that might be relevant.
5. **Caller flag** — when invoked by another skill, accept `caller=<skill-name>` as a parameter. Store it; it gates Phase 6 and is noted in any decision-log entry written in Phase 7.

If any of the first three is missing when invoked from chat, ask for them before starting. If invoked programmatically by execute-plan or ui-validation, those callers are responsible for passing the bundle.

## Phase 1: Reproduce

Goal: confirm the failure is deterministic before investing in localization. A failure you can't reproduce reliably can't be fixed confidently.

Run the minimal command that should trigger the failure. If it reproduces: proceed. If it doesn't: investigate whether the first failure was environment-dependent (missing env var, stale build artifact, race condition).

**Intermittent failures** are handled explicitly rather than punted. Default path:

1. Run the failing test or command up to N=5 times, noting the failure rate and any pattern (always fails on iteration 2, only fails under load, fails if run after another test, etc.). The entire rerun sequence wraps a **90-second total wall-clock budget**. If 90 seconds elapse before N=5 completes, surface partial results immediately: "ran N=`<x>` within 90s budget, observed `<y>` failures, `<z>` passes — proceeding with partial characterization." Do not keep running past the budget.
2. Attempt determinization: seed known RNG sources, mock the clock if time-dependent (`Date.now`, `time.time`), disable retries if the test framework has them, isolate the test from parallel execution. Run again (same 90s budget for any further reruns).
3. If still non-deterministic after determinization attempts: surface a characterization report — failure rate, observed variance, what you tried, what you suspect (shared state, timing window, external service call) — and ask the user how to proceed. Do not continue hypothesizing about root cause until reproduction is reliable; a flaky test that sometimes passes can falsely confirm a wrong hypothesis.

## Phase 2: Localize

Goal: narrow to the smallest context in which the failure occurs. The smaller the case, the fewer variables a hypothesis has to explain.

Localization technique depends on the failure class:

**Playbook T — Test failure**
- Identify the specific assertion that failed. A test with ten assertions that fails on the third one doesn't require reading the other seven.
- Check the diff since the last passing state (`git diff <last-green-sha>`). Failures that appear right after a change are usually caused by that change.
- Run the test file in isolation before running the full suite. A test that only fails in the full suite has a state-pollution bug, not the bug you think it has.
- If the test file is large, comment out test cases until you have the minimal failing case.

**Playbook B — Build / compile failure**
- Find the first error in the compiler output. Everything after it is a cascade and will auto-resolve once the root is fixed.
- Check imports and type signatures of the file the first error points to; build failures are usually missing dependencies, signature mismatches, or a type change that propagated.
- Do not read the error count as a measure of problem severity — 47 TypeScript errors from one bad interface change is still one problem.

**Playbook R — Runtime exception**
- Read the stack trace from the top (throw site) to the bottom (entry point). Find the frame in code you own — skip library internals.
- Check recent changes to the files named in that frame (`git log -p -- <file>`).
- If the exception message contains a value (e.g. "Cannot read properties of undefined (reading 'id')"), find where that value is supposed to be set and trace backward.

**Playbook W — Wrong output, no exception**
- Narrow the input: find the smallest input that produces the wrong output.
- Narrow the code path: add a temporary observation point (see Phase 6 on tracking temp logging) just before the output is produced. If the value entering the final step is already wrong, the bug is upstream; repeat.
- Diff expected vs. actual precisely — "wrong" is not useful, "off by one in the count" or "missing the last record" is.

## Phase 3: Hypothesize

Goal: articulate the candidate root causes before testing any of them. The discipline here is the most important part of the skill — the natural LLM behavior is to jump to the first plausible explanation and start changing code. That's how you end up with a "fix" that masks the symptom without touching the cause.

**The constraint:** write down all hypotheses before executing any probe. Track hypotheses-in-flight via TodoWrite so the cap is enforceable. Use this table:

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

**Tracking temporary logging.** Any `print`, `console.log`, `logger.debug`, or debugger statement added during hypothesis testing MUST be marked with a sentinel comment:

```python
print(f"DEBUG-LOOP-TEMP: user_id={user_id}")  # Python
```
```typescript
console.log('DEBUG-LOOP-TEMP:', value);  // TypeScript/JavaScript
```
```go
fmt.Printf("DEBUG-LOOP-TEMP: %v\n", val)  // Go
```
```java
System.out.println("DEBUG-LOOP-TEMP: " + val);  // Java
```

Before declaring verify complete, grep for `DEBUG-LOOP-TEMP` across all modified files. NEVER declare done while any sentinel is present — it is a verification failure, not a minor omission.

**ui-validation after a frontend fix:**
- If `caller=ui-validation` was passed when debug-loop was invoked: do NOT invoke ui-validation in Phase 6. Surface the fix to the user: "ui-validation called us — not looping back. Please re-run your validation to confirm the fix."
- Otherwise, if a `ui-validation` sibling is installed and the fix touched frontend code: invoke it now against the affected surfaces, passing `caller=debug-loop`. If ui-validation is not installed, print: "if `ui-validation` were installed I'd run a browser check here" and continue.

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

These are the default LLM debugging behaviors. Each one makes the failure harder to understand and the fix harder to trust.

**Random fix-and-rerun**
> Example: "Let me try changing this to `!= null` and see if that helps."
> The rerun *is* your hypothesis. If you don't know what you expect to observe, you don't have a hypothesis — you have a coin flip. Every random change adds noise to the signal.
> Correct: write the hypothesis and prediction first; then make the change.

**Patching the test instead of the code**
> Example: Test expects `[1, 2, 3]`, code returns `[1, 2]`, so change the assertion to `[1, 2]`.
> The test was documenting a contract. Changing expected values to match wrong output deletes the evidence.
> Correct: fix the code that returns the wrong value; the test stays.

**try/except swallowing**
> Example: Wrapping the failing call in `try: ... except Exception: pass` so the test suite goes green.
> You've hidden the failure, not fixed it. The next person to debug this has less information than you do right now.
> Correct: understand why the exception is thrown; either handle it correctly or fix the caller.

**Loosen the assertion**
> Example: Test is asserting an exact match; change it to `assertIn` or `assertTrue(len(result) > 0)`.
> Weaker assertions hide regressions. If the exact match was right before, it's still right.
> Correct: fix the output; don't widen the gate to let the wrong output through.

**`git revert` until green without understanding**
> Example: Reverting three commits one by one until tests pass, then declaring done.
> You've undone work without understanding what in that work caused the failure. The next implementation will hit the same bug.
> Correct: bisect to find the introducing commit, then read that diff to understand the cause.

**Scope creep during debug**
> Example: "While I'm in this file, I'll also refactor this unrelated method."
> Every change during a debug session is a new variable. An incidental refactor can introduce a regression and make it impossible to isolate what fixed what.
> Correct: make the surgical fix only; open a new task for the cleanup.

**First hypothesis is the only hypothesis**
> Example: "This is probably a null check issue" — immediately adds null check — runs test.
> The first plausible explanation is often wrong or incomplete. Confirming it without alternatives means you may have addressed a symptom, not the cause.
> Correct: form 2–3 hypotheses before testing any; the table enforces this.

**"One more fix attempt" after exhaustion**
> Example: H1 falsified, H2 falsified, H3 ambiguous — "let me just try one more thing."
> Past three failed hypotheses, you're guessing. Guesses compound. Surface the dossier and stop.
> Correct: produce the exhaustion report; let the user redirect.

**Catch-and-log instead of fix**
> Example: Wrapping the error site in a try/catch that logs the exception and returns a default value.
> This converts a loud failure (visible, debuggable) into a silent one (logs you'll forget to read).
> Correct: fix the condition that causes the exception, or propagate the error to the caller who can handle it with context.

## Composition

- **Called by:** execute-plan (on task failure), ui-validation (on browser check failure), verify-before-done (on gate failure). Each caller is responsible for passing the failure bundle (error output + what was being attempted + what changed) and a `caller=<skill-name>` parameter.
- **Calls:** ui-validation (at end of Phase 6 if frontend code was modified and ui-validation is installed, passing `caller=debug-loop`); `knowledge-capture` (Phase 7, when the conditions for proposing an entry are met, passing `caller=debug-loop`); vscode-preview (to display the decisions.md entry if the sibling is installed — optional).
- **Reads:** `.claude-plans/<active-dir>/handoff.md` and `decisions.md` for repo context; `plan.md` for task scope; changed files via git diff.
- **Writes:** `DEBUG-LOOP-TEMP` sentinels during hypothesis testing (removed before verify completes); decision log entry to `.claude-plans/<active-dir>/decisions.md` when applicable; exhaustion report to chat when terminating without resolution. Proposes (but does not write directly) `knowledge-capture` entries — that skill owns the user interaction.

If a sibling is not installed: print a one-line notice ("if `ui-validation` were installed I'd run a browser check here") and continue. Sibling-installed check: `~/.claude/skills/<name>/SKILL.md` OR `~/.claude/plugins/cache/**/skills/<name>/SKILL.md`.

## Open questions

1. **Headed vs headless when invoked from debug-loop.** ui-validation defaults to headless; when debug-loop triggers it after a visual failure, headed mode is probably more useful. Leaning: debug-loop requests `headed: true` explicitly when calling ui-validation after a visual failure, since the user is actively debugging.
2. **Hypothesis table format.** Plain markdown table vs. a structured block the skill populates incrementally. The table is easier for the user to read mid-session; a structured block is easier for a downstream subagent to parse. Leaning: markdown table for now; revisit when execute-plan's subagent mode is fully designed.
3. **N for intermittent failure characterization.** Five runs was chosen to balance signal vs. cost. For fast unit tests that's cheap; for slow integration tests it could be expensive. Caller can pass `max_flaky_runs` to override; default N=5.
