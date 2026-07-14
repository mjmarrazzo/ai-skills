---
name: ci-check-triage
description: Use this skill whenever CI is red on a PR — "why is CI failing", "the build is broken", "triage the failed checks", "fix the failing CI", "status checks are red", "the pipeline failed", "github actions failed", "the checks won't pass", or "look at the CI failures". Also trigger automatically when finish-branch's watch detects failed status checks on a PR (caller=finish-branch, PR_NUMBER passed). Pulls failed checks via gh, pulls the failing logs, classifies each as real-failure / flaky-or-infra / external-blocker, proposes an action per check, gets user approval, hands real failures to debug-loop for the fix, offers a re-run for flaky ones, then pushes and reports. Skip only on explicit opt-out: "I'll fix CI myself", "ignore the checks", "it's just flaky, skip it", or a single check the user already named and diagnosed.
---

# ci-check-triage

Turn a red checks list on a PR into a single approvable table, then drive each failure to resolution — real failures handed to debug-loop for a root-cause fix, flaky/infra failures re-run, external blockers surfaced — without the user squinting at raw CI logs. This is the status-check mirror of `pr-review-triage`: same shape, different input. Comments are one source of "things wrong on this PR"; failed checks are the other.

**Announce at start:** "Using ci-check-triage to pull the failed checks on PR #`<num>`, read their logs, and classify each one."

## When to trigger

Trigger phrases and opt-outs are in the frontmatter. One additional case: the user names a single specific check they've already diagnosed ("the lint job failed because of the unused import on line 12") — fix that one directly; skip the full flow.

**Scope:** classify and resolve failed status checks on one PR. In scope: reading check logs, classifying, reproducing locally, delegating fixes to debug-loop, re-running flaky checks, committing and pushing fixes. Not in scope: writing new CI config from scratch, merging, marking the PR ready (that's finish-branch), or grading review comments (that's pr-review-triage).

## In-session tracking

Use `TodoWrite` to track:
1. Locate PR
2. Fetch checks + filter to failed
3. Pull logs for each failed check
4. Classify each check
5. Present table + get approval
6. Resolve each approved item (one per check: debug-loop / re-run / surface)
7. Commit + push fixes
8. Report

## Pre-flight

### 1. Locate the PR

Resolution order (identical to pr-review-triage so the two compose predictably): caller-passed `PR_NUMBER`/`PR_URL` verbatim → number/URL in the user's message → `gh pr view --json url,number,state,headRefName,baseRefName`. No open PR on the branch → "No open PR found on branch `<name>`. Push the branch and open the PR first (or pass the PR number)." and stop. PR `MERGED`/`CLOSED` → unusual; confirm before proceeding.

### 2. Verify gh availability

`which gh && gh auth status` before any API call; on failure surface the fix (`https://cli.github.com/` / `gh auth login`) and stop. Never fall back to raw `curl` — auth handling diverges and credentials leak.

### 3. Fetch checks

```bash
gh pr checks <num> --json name,state,bucket,link,workflow,description,completedAt
```

The `bucket` field collapses GitHub's many states into `pass | fail | pending | skipping | cancel`. Filter to `bucket == "fail"` (and `cancel`, which is usually an infra abort worth a re-run).

**If checks are still `pending`:** do not classify a not-yet-finished run as a failure. Report which checks are still running and stop, unless the caller explicitly asked to wait. finish-branch owns the watch loop; this skill acts on a *settled* checks list.

**If after filtering the failed list is empty:**

> No failed checks on PR #`<num>`. Nothing to triage.

Stop. Don't manufacture work.

### 4. Pull logs for each failed check

A check name alone isn't enough to classify — the log is. Invocations live in `references/gh-checks.md`; the common path:

```bash
# GitHub Actions checks: run id parsed from the check's link field
# (https://github.com/OWNER/REPO/actions/runs/<run-id>/job/...), then:
gh run view <run-id> --log-failed
```

Resolve the run id from the check's `link` field first; fall back to matching `workflowName` + `headSha` via `gh run list` only when the link doesn't carry a run id (see `references/gh-checks.md`).

For non-Actions checks (external CI, status contexts with only a `link`), there's no log to pull via `gh` — capture the check name, description, and `link`, and classify it as an external blocker for the user to open.

## Classification

For each failed check, read the failing log and assign one verdict:

| Verdict | When | Action |
|---|---|---|
| **real failure** | The log shows a genuine code problem: a failing assertion, a compile/build error, a type error, a lint rule violation with a clear locus. Reproducible from the diff. | Hand to debug-loop (real bug) or fix directly (mechanical lint). |
| **flaky / infra** | Timeout, network blip, runner OOM, a known-intermittent test, "could not reach registry". The code is not implicated. | Offer to re-run the check. Never touch code. |
| **coverage / quality gate** | A coverage-threshold or quality-gate check fails on a metric shortfall (coverage below N%, code-smell budget exceeded) — not a bug with a locus. | Never hand to debug-loop. Surface the shortfall to the user (metric, threshold, actual) and suggest planning the coverage/quality work via `blueprint` rather than patching blind. |
| **external blocker** | A required status from a system `gh` can't drive — a deploy gate, a third-party scanner, a check awaiting an approval. No local reproduction possible. | Surface the `link`; the user resolves it outside this skill. |
| **cancelled run** | The run was cancelled rather than failed. If superseded by a newer push (the run's `headSha` is no longer HEAD) → treat as **stale**. Otherwise (infra abort, concurrency-group kill) → treat as **flaky / infra**. | Stale path: don't act. Flaky path: re-run, same single re-run cap. |
| **stale** | The check ran against a commit that's no longer HEAD (a newer push is already queued). | Note it; let the in-flight run supersede it. Don't act. |

Tag each verdict `high` / `medium` / `low` confidence. The flaky-vs-real call is the load-bearing judgment — a confident "flaky" that's actually a real intermittent bug masks a defect, so when a "test failure" *could* be either, grade it **real failure, low confidence** and let the table flag it for explicit review rather than defaulting to a re-run. Re-running is the move you reach for last, not first.

### Reading workspace context

Apply the canonical active-workspace resolution (same as pr-review-triage and finish-branch): `WORKSPACE_PATH` param → enumerate `.claude-plans/*/` for `plan.v*.md`/`spec.v*.md` (blueprint writes only versioned artifacts; use the highest-N version) → one match use it, multiple prefer the branch's ticket key, zero → ad-hoc. When present, the current plan and spec help judge whether a failing test is testing in-scope behavior. In ad-hoc mode, classify from the log + diff alone and lower confidence one notch.

## User-approval gate

Present a single table:

```
PR #1234 — 3 failed checks (branch PROJ-1234/add-orchestrion)
Workspace: .claude-plans/2026-05-14-PROJ-1234-orchestrion/

  # | Check                | Verdict         | Conf   | Action
 ---|----------------------|-----------------|--------|--------------------------------
  1 | unit-tests (go)      | real failure    | high   | debug-loop: TestMapper nil deref
  2 | integration-tests    | flaky / infra   | medium | re-run (DB container timeout)
  3 | lint                 | real failure    | high   | fix: remove unused import (lint inline)
  4 | deploy-preview        | external block  | -      | open the link — awaiting deploy gate

Choose:
  (a) Approve all
  (b) Approve subset (comma-separated numbers): e.g. 1,3
  (c) Override a verdict: "override 2: real failure"
  (d) Skip — I'll handle CI manually
```

When the failed-check count is ≤ 4, you may use `AskUserQuestion` (one question per check). Above 4, use the inline table + free-form confirmation.

**Always stop here. Never hand a check to debug-loop, re-run anything, or edit code without explicit approval.** Even on `(a) Approve all`, restate the plan and confirm:

> Handing `<N>` failures to debug-loop, re-running `<M>` flaky checks, surfacing `<K>` external blockers. Proceed?

Wait for `y` / "yes" / "go" / "do it". Anything else: re-prompt or stop.

## Auto mode (granted, never inferred)

Same rule as finish-branch: auto only when the user said so **this turn**, the invocation carries `mode=auto`, or a pipeline grant exists in the active workspace. Probe with Bash:

```bash
test -f .claude-plans/<active>/.pipeline.json && \
  grep -q '"mode"[[:space:]]*:[[:space:]]*"auto"' .claude-plans/<active>/.pipeline.json && \
  echo "GRANT: auto" || echo "GRANT: interactive"
```

Under a grant:
- Proceed without approval for **`real failure` → debug-loop** handoffs and for the **single allowed re-run** of a `flaky / infra` check.
- `external blocker`, `coverage / quality gate`, and anything that hits a cap (second failure after re-run, unappliable fix) → halt and surface; these are never auto-actioned.
- Log every auto decision to the workspace `open-questions.md`.

Safety gates (dirty tree, cap breaches, rejected pushes) still block in auto mode — auto waives permission prompts, never protection.

## Execution

After approval, in order:

### 1. Real failures → reproduce, then debug-loop

For each `real failure`:
- **Reproduce locally first.** Pull the failing command from the log (the test invocation, the build step, the lint command) and run it locally. This confirms the failure isn't environment-specific to CI before any fix is attempted.
- **Mechanical lint/format** (unused import, missing newline, gofmt) with a single obvious fix and no behavioral change: fix it directly with `Edit`. Don't spin up debug-loop for a one-line lint nit.
- **Everything else** (failing assertion, build error, type error, logic bug): hand to `debug-loop` with `caller=ci-check-triage` and a failure bundle — the failing command, its output, the check name, and the diff under review. debug-loop owns reproduce-localize-hypothesize-fix; this skill does not reimplement it. If debug-loop isn't installed, surface the failing command + log and stop before committing (see Composition).

If a reproduction *doesn't* fail locally, the check may actually be flaky or environment-specific — kick it back to the table as `flaky / infra, low confidence` and tell the user rather than guessing at a fix.

### 2. Flaky / infra → re-run

For each `flaky / infra` the user approved:

```bash
gh run rerun <run-id> --failed   # re-run only the failed jobs
```

Re-running mutates nothing in the repo. Report the re-run was kicked off; the new result lands in the watch loop (finish-branch) or on the user's next check.

**Do not re-run blindly to chase green.** A check that fails twice in a row is not flaky — re-classify it as a real failure and surface it. Cap automatic re-runs at **one** per check; a second failure goes back to the user.

### 3. Commit + push fixes

If any code changed (debug-loop fixes or inline lint fixes):

Ticket key detected (same rule as pr-review-triage) from the workspace slug, a branch prefix matching `^[A-Z][A-Z0-9]+-\d+`, or a `CLAUDE.md` convention. Single commit by default: `<KEY>-XXXX: fix failing CI checks` with a ticket key, `Fix failing CI checks` without; body lists `- <check>: <one-line summary>` per fix.

`git push origin <branch>` — plain push, never force, never rebase; the new commit re-triggers the checks. Rejected push (remote moved): surface, don't force, tell the user to pull and re-run.

## Report

After execution:

```
ci-check-triage — done
─────────────────────────
PR #1234 — branch PROJ-1234/add-orchestrion

Fixed:    2 checks → commit a1b2c3d (pushed; checks will re-run)
  - lint: removed unused import in mapper.go
  - unit-tests (go): TestMapper nil deref (via debug-loop, root cause: unguarded map access)
Re-ran:   1 flaky check (integration-tests — DB container timeout)
Surfaced: 1 external blocker (deploy-preview — open https://… to clear the deploy gate)

Verified: debug-loop verified its fix against HEAD a1b2c3d; inline lint fix re-checked locally (lint command green)
```

The `Verified:` line reports only verification that actually happened — debug-loop's own end-of-fix verification, or the local re-run of a lint command for inline fixes. This skill never invokes verify-before-done, so never claim a verify-before-done pass. If nothing was verified (e.g. only re-runs and surfaced blockers), drop the line.

If invoked by finish-branch, control returns to its watch loop, which re-evaluates once the re-triggered checks settle. If invoked standalone, offer to watch the re-run:

> Pushed a1b2c3d — checks are re-running. Want me to watch and report when they settle?

## Composition

- **Called by:** the user directly; `finish-branch` automatically when its watch detects failed checks (passing `caller=finish-branch` + `PR_NUMBER`).
- **Calls:** `debug-loop` for every non-trivial real failure (`caller=ci-check-triage` + failure bundle). debug-loop's caller-guard means it won't loop back here. `verify-before-done` is **not** called directly — debug-loop runs its own verify at the end of a fix; for inline lint fixes, re-running the lint command locally is sufficient.
- **Reads:** `handoff.md`, current `spec.v*.md`, current `plan.v*.md`, `decisions.md` (all optional) for scope context; check logs + diff via `gh` and git.
- **Writes:** code edits (only the mechanical inline fixes — debug-loop owns its own edits); git commit(s); `git push`. Triggers `gh run rerun` for flaky checks. Never marks the PR ready — that's finish-branch's call after the watch comes back clean.
- **Caller flag:** pass `caller=ci-check-triage` to all sibling invocations (cycle-prevention convention).
- **Sibling absent:** debug-loop not installed → surface the failing command + log and stop before committing; don't guess at a fix. finish-branch not installed → run standalone and offer to watch the re-run yourself.

## Anti-patterns

These are the failure modes specific to this skill.

**Re-running until it goes green.** A check that fails, gets re-run, and fails again is a real failure wearing a flaky costume. Chasing green by re-running masks defects and is the single most damaging thing this skill could do. One re-run, then it's a real failure.

**Weakening the test to make it pass.** Deleting an assertion, loosening a tolerance, or adding a `skip` to silence a red check is not a fix — it's hiding the failure. If the test is genuinely wrong, that's a real change with its own rationale that the user must approve explicitly; the default is "the test caught something."

**Fixing CI config to route around the failure.** Disabling a job, dropping it from the required set, or `continue-on-error` to get a green checkmark defeats the entire point of the gate. Out of scope; surface to the user.

**Classifying as flaky without reading the log.** "Tests fail sometimes" is not a classification. Every `flaky / infra` verdict cites the specific log evidence (the timeout line, the OOM, the network error). No evidence → it's a real failure, low confidence.

**Acting on pending checks.** A check that's still running hasn't failed. Wait for the run to settle; don't classify in-flight jobs.

**Reimplementing debug-loop.** This skill triages and reproduces; debug-loop fixes. Don't write a parallel reproduce-localize-fix loop here — hand the bundle over and let the fix engine do its job.

**Force-pushing over CI history.** New commits append; the sequence of "failed → fixed" is the audit trail. Never force-push to chase a clean checks history.

## Open questions

1. **Re-run cap.** One automatic re-run, then surface. Some genuinely flaky integration suites need two. Revisit after dogfooding; could expose `max_reruns` as a caller param like debug-loop's `max_flaky_runs`.
2. **Required vs optional checks.** Currently triages every failed check. Could filter to *required* checks only (those that block merge) and treat optional failures as advisory. Punt until we see how noisy optional checks are in practice.
3. **Non-Actions CI (CircleCI, Jenkins, Buildkite).** Log-pulling via `gh run view` only works for GitHub Actions. Other providers expose only a status context + link. Currently those are "external blockers." Could add provider-specific log fetching later if the user's repos need it.
