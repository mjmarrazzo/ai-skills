# ci-check-triage — DESIGN

Lean design rationale. Operational form lives in `SKILL.md`.

## Purpose

After a PR is opened, CI runs status checks (GitHub Actions jobs, external CI contexts, quality gates). When one goes red, the user does the same ritual every time: open the run, scroll the logs, figure out whether it's a real failure or a flake, fix the real ones, re-run the flakes, push. That ritual is mechanical *except* the classify step (real vs flaky vs external) and the fix step. This skill automates the mechanics and delegates the fix to debug-loop.

It is deliberately the **mirror of pr-review-triage**. That skill triages review *comments*; this one triages failed *checks*. Same locate-PR algorithm, same fetch→classify→approve→execute→report arc, same approval gate, same debug-loop delegation, same caller-flag cycle guard. A user who knows one knows the other. Keeping them symmetric is the whole reason this is a separate skill rather than logic stuffed into finish-branch.

## Why a separate skill (not finish-branch routing straight to debug-loop)

debug-loop is a fix engine — it expects a concrete failing command it can run locally. "A check went red on the PR" is not that yet. Something has to list the failed checks, pull the logs, and *classify* — only real, reproducible failures should reach debug-loop; flakes get re-run, external gates get surfaced. If finish-branch did that work, finish-branch would stop being a watcher and become a fixer (its explicit anti-pattern). If we routed every red check straight to debug-loop, debug-loop would choke on flakes and external gates it can't reproduce. The triage layer is real work with a real home: here.

## Boundary

In scope:
- Pull failed checks for one PR; pull their failing logs.
- Classify each: real failure / flaky-or-infra / external blocker / stale.
- Reproduce real failures locally; hand non-trivial ones to debug-loop; fix mechanical lint inline.
- Re-run flaky checks (capped at one automatic re-run).
- Commit + push fixes.
- Report.

Out of scope:
- Writing or repairing CI config (disabling jobs, `continue-on-error`, dropping required checks) — that routes *around* the gate.
- Marking the PR ready — finish-branch owns promotion.
- Grading review comments — pr-review-triage.
- Reimplementing reproduce-localize-fix — debug-loop owns it.

## A. Locating the PR

Identical resolution order to pr-review-triage (caller param → user message → `gh pr view`). Symmetry is intentional: finish-branch hands both skills the same `PR_NUMBER`, and a user invoking either standalone gets the same behavior. Merged/closed → confirm before proceeding.

## B. Fetching and filtering checks

`gh pr checks <num> --json …` exposes a `bucket` field that collapses GitHub's many states into `pass|fail|pending|skipping|cancel`. We act on `fail` and `cancel` (cancel is usually an infra abort worth a re-run). The critical guard: **never classify a `pending` check as a failure.** The watch loop (finish-branch) is responsible for waiting; this skill acts on a settled list. `--watch` blocks, so it belongs to the watcher, not here.

## C. Pulling logs

A check name doesn't classify itself — the log does. `gh run view <run-id> --log-failed` prints only failing steps (vs `--log` dumping the whole run). For non-Actions checks there's no `gh run` backing, so they can only be surfaced as external blockers with their `link`. Commands live in `references/gh-checks.md`.

## D. Classification

Four verdicts: real failure / flaky-or-infra / external blocker / stale. Each gets a confidence tag. The load-bearing judgment is real-vs-flaky, and the bias is deliberately **toward "real."** A confident "flaky" that's actually an intermittent bug masks a defect — the worst outcome. So when a test failure could be either, it's graded `real failure, low confidence`, which flags it for explicit review rather than silently re-running. Re-running is the last resort, not the reflex.

Workspace context (`plan.md`/`spec.md`) helps judge whether a failing test covers in-scope behavior. Same active-workspace resolution as the sibling skills; ad-hoc mode lowers confidence a notch.

## E. Approval gate

Single table, same ergonomics as pr-review-triage: `AskUserQuestion` at ≤ 4 checks, inline table + free-form above. Always stop here; even `(a) Approve all` restates the plan and gets one final confirm. Nothing — not a debug-loop handoff, not a re-run, not an edit — happens without explicit approval.

## F. Execution

1. **Real failures.** Reproduce locally first (confirms it's not CI-environment-specific). Mechanical lint with an obvious one-line fix → `Edit` directly (spinning up debug-loop for an unused import is overkill). Everything substantive → debug-loop with `caller=ci-check-triage` + failure bundle (failing command, output, check name, diff). If a local repro *passes*, it's probably flaky → kick back to the table, don't guess.
2. **Flaky / infra.** `gh run rerun <run-id> --failed`. Mutates no code. Cap: one automatic re-run. Twice red = real failure, re-classify.
3. **External blockers.** Surface the link. Can't drive them via `gh`.
4. **Commit + push.** Single commit, ticket-prefixed if a key is detected, body lists each fix. Plain push — the new commit re-triggers checks. Never force.

## G. Report

Summarize fixed / re-ran / surfaced, with the commit SHA and (from debug-loop) the root cause. If finish-branch called us, control returns to its watch loop. Standalone, offer to watch the re-run.

## H. Composition

- **Called by:** user directly; finish-branch (auto, on red checks, `caller=finish-branch` + `PR_NUMBER`).
- **Calls:** debug-loop (`caller=ci-check-triage` + failure bundle) for real, non-trivial failures. debug-loop's caller-guard prevents loop-back. Does not call verify-before-done directly — debug-loop runs verify at the end of its own loop.
- **Cycle guard:** standard `caller=` convention.
- **Sibling absent:** debug-loop missing → surface failing command + log, stop before committing. finish-branch missing → standalone, offer to watch the re-run.
- **Relationship to the watch loop:** this skill is one-shot per invocation. It fixes/pushes/re-runs and returns. The *loop* (re-check after push, decide clean-or-not) lives in finish-branch. Keeping the loop in one place (the watcher) avoids two skills both polling the same checks.

## I. Anti-patterns

- **Re-running until green.** Twice red ≠ flaky. One re-run cap.
- **Weakening tests / skipping / loosening tolerances** to silence a check. That's hiding the failure, not fixing it.
- **Editing CI config to route around the gate.** Out of scope; surface it.
- **"Flaky" without log evidence.** No cited timeout/OOM/network line → it's real, low confidence.
- **Acting on pending checks.** Wait for settle.
- **Reimplementing debug-loop.** Triage + reproduce here; fix there.
- **Force-pushing over CI history.** Append commits.

## Open questions

1. **Re-run cap** — one, then surface. Some integration suites are genuinely 2-flaky. Could expose `max_reruns`. Dogfood first.
2. **Required vs optional checks** — currently triages all failed checks. Could scope to required (merge-blocking) only. Punt.
3. **Non-Actions CI providers** — only Actions logs are pullable via `gh`. Others are external blockers. Add provider-specific fetch later if needed.
4. **Coverage / quality gates** — a failing threshold needs *new tests*, closer to scope-expansion than a bug fix. debug-loop may bounce it. Watch the pattern.
