---
name: verify-before-done
description: Use this skill whenever the user asks "is this ready?", "verify before I commit", "lgtm check", "run the checks", or "done with this task / ready to merge". Also invoked automatically by execute-plan at the end of plan execution and by finish-branch as a pre-flight gate. Skip only if the user explicitly opts out ("skip checks", "quick commit", "just do it", "I know the tests are broken") or when the diff is docs-only, generated-files-only, or empty against the branch base.
---

# Verify Before Done

Run the cheapest objective checks — format, lint, typecheck, tests, plan verifications, UI — in order. Surface the first concrete failure to the right place. Report green only when every check exits 0.

**Announce at start:** "Using verify-before-done to gate this before it's declared done."

## When to trigger, when to skip

Auto-trigger on: "is this ready?", "verify before I commit", "lgtm check", "run the checks", "done with this task", "ready to merge", end of execute-plan's final task.

Opt-out (genuine, no nagging): "skip checks", "quick commit", "just do it", "I know the tests are broken".

Skip silently when: no diff against branch base; diff is docs-only (`.md`, `.txt`, `.rst`); diff is generated-files-only (lockfiles, `.pb.go`, migration snapshots) with no configured tooling against them.

## Active-workspace resolution

Resolve the active workspace via the shared algorithm: if the caller passes `WORKSPACE_PATH`, use it; otherwise find the newest `.claude-plans/*/` directory containing `plan.md` or `spec.md`, tie-broken by branch ticket key (e.g., `MSP-7032` in slug). If no workspace is found, run in ad-hoc mode — artifacts go to `./.claude-results/<YYYY-MM-DD-HHMMSS>/verify-before-done/`. Ensure `.claude-results/` is in `.gitignore` (idempotent, one-time append).

Use `TodoWrite` to track check progress in-session.

## Tooling detection

Full per-stack detection tables (TS/JS, Python, Go, Rust, JVM/Kotlin, monorepo orchestrators): see `references/tool-detection.md`.

## Order of checks

**format → lint → typecheck → tests → plan verifications → ui-validation**

- **Format** first: fastest (~5s); format failures make lint output noisy.
- **Lint** before typecheck: syntactic errors block type inference; cascading errors obscure the root cause.
- **Typecheck** before tests: a test passing against a type-unsafe call is not meaningful.
- **Tests**: most expensive; only after static checks are clean.
- **Plan verifications**: integration-flavored; always run if `plan.md` has explicit verification steps.
- **ui-validation**: slowest; run only when frontend files appear in the diff (`.tsx`, `.jsx`, `.vue`, `.svelte`, `.css`, `.scss`, HTML templates).

Abort on first failure class within each package. If lint exits non-zero, do not proceed to typecheck — downstream checks on a broken lint are noise, not signal.

`verify --tests-first` skips straight to tests (useful mid-TDD cycle). `verify --full` forces the complete suite regardless of diff scope.

## Auto-fix policy

**Report-only by default.** Formatters run in `--check` mode — Prettier, black, rustfmt, gofmt, ktlint. Output lists files that would change; no file is modified. This preserves a clean working tree, which is required by finish-branch's clean-tree gate.

Opt-in to write mode via explicit user phrase: "fix the formatting" or `--autofix`. In write mode, re-run the formatter, print the diff stat, then continue to lint.

```
Format changes required (report-only — run with --autofix to apply):
  src/auth.ts        (+2/-2 whitespace)
  tests/auth.test.ts (+1/-1 trailing newline)
```

**Linters with `--fix` — never automatic.** `eslint --fix`, `ruff --fix`, `clippy --fix` can change program behavior. Default is report and stop. Opt-in via `verify --autofix-lint`; when set, print the full diff and confirm with the user before continuing.

**Imports and unused vars — never auto-remove.** Too many legitimate patterns look like dead code mid-refactor.

## Relevant tests strategy

Default: changed-file matching + plan verifications. Full suite is opt-in.

1. For each modified source file, run co-located tests (`foo.test.ts`, `foo_test.go`, `test_foo.py`, etc.).
2. If no co-located test exists, run all tests in the same directory.
3. If changed files span more than one package boundary, or the diff touches a file in `utils/`, `lib/`, or `common/` (shared-module heuristic), promote to full suite and print the reason.
4. `verify --full` forces the complete suite.

Target: under 60 seconds on a typical task-sized diff. A verify that takes 8 minutes gets skipped; one that takes 30 seconds gets run every time.

## Polyglot monorepo handling

When no orchestrator is present and multiple independent package manifests exist (`apps/web/package.json` + `apps/api/pyproject.toml`, etc.), run all check classes per-package. Abort within a package at its first failure class, but continue with other packages. Aggregate all failures across packages and report them together — a failure in one package must not hide failures in another.

## Plan verifications

`plan.md` tasks include explicit verification steps:
```
Run: pytest tests/foo/test_bar.py::test_x -v
Expected: PASS
```

Re-run every plan verification on every invocation. Do not trust that execute-plan ran them per task — the final gate confirms the whole set still holds after all tasks complete. Run in listed order, after the test suite. A failing verification is treated as a test failure and handed off to debug-loop.

If `plan.md` is absent or has no verification steps, skip this phase silently.

## Output format

```
verify-before-done — <slug>
─────────────────────────────────────────────────────
✓ format          prettier           2 files would change   0.8s  (advisory)
✓ lint            eslint             0 errors               3.2s
✓ typecheck       tsc --noEmit       0 errors               6.1s
✓ tests           vitest run         14/14 passed           4.9s
  ↳ relevant: src/auth.ts, src/auth.test.ts
✓ plan:verify     pytest test_x -v   PASSED                 1.2s
✓ ui              ui-validation      2/2 surfaces ok        8.4s

6 checks passed — 24.6s total
Ready. Logs: .claude-plans/<dir>/verify/<timestamp>/
```

On failure: first 20 lines of stderr from the failing command, then the log path. Do not dump full logs into chat.

Artifacts: `.claude-plans/<active-dir>/verify/<timestamp>/` (workspace mode) or `./.claude-results/<YYYY-MM-DD-HHMMSS>/verify-before-done/verify/<timestamp>/` (ad-hoc). Each check writes stdout+stderr to a numbered log: `01-format.log`, `02-lint.log`, etc.

## verify.json

Write `.claude-plans/<active>/verify.json` at end of every run — pass or fail. In ad-hoc mode: `./.claude-results/<ts>/verify-before-done/verify.json`. finish-branch reads this file as a pre-flight gate.

```json
{
  "timestamp": "2026-05-14T10:30:00Z",
  "commit_sha": "abc1234...",
  "result": "pass",
  "checks": [
    {"name": "lint", "status": "pass", "duration_ms": 1234, "log": "verify/<ts>/01-lint.log"},
    {"name": "typecheck", "status": "pass", "duration_ms": 4567, "log": "verify/<ts>/02-typecheck.log"}
  ],
  "artifacts_dir": "verify/<ts>/"
}
```

## Failure handling

| Failure class | First action | Handoff |
|---|---|---|
| Format | Report file list as advisory, continue | None |
| Lint — whitespace / import order | Report, suggest `--autofix-lint` | User decides |
| Lint — semantic (unused-vars, unsafe equality) | Report file:line + rule name | "lint error in `src/auth.ts:42` — fix or suppress?" |
| Typecheck | Report file:line:col + message | debug-loop: typecheck failure + log path |
| Test failure | Report failing test name + assertion (first only) | debug-loop: test name + assertion message |
| Plan verification | Report command + exit code + first error line | debug-loop: verification command + log path |
| UI (ui-validation) | ui-validation's own report | ui-validation hands to debug-loop; do not duplicate |

**Cycle prevention.** When invoking ui-validation, pass `caller=verify-before-done`. When invoking debug-loop, pass `caller=verify-before-done`. If invoked with `caller=debug-loop`, do not re-invoke debug-loop on failure — print the handoff payload and stop. If invoked with `caller=ui-validation`, do not re-invoke ui-validation — skip the UI check entirely.

If debug-loop is not installed (probe: `~/.claude/skills/debug-loop/SKILL.md` or `~/.claude/plugins/cache/**/skills/debug-loop/SKILL.md`): print the handoff payload verbatim and stop. One-line notice: "debug-loop not installed — fix the above manually, then re-run verify-before-done."

Never retry a failing check. Flaky tests are a separate problem.

## Why separate from finish-branch

Merging them couples verifying to publishing. Three reasons that's wrong:

1. verify-before-done is called from execute-plan at plan end, not only before a PR. Verification happens whenever a task is declared done.
2. finish-branch invokes verify-before-done as a precondition. A lint failure aborting `gh pr create` before the user chose a title is broken UX.
3. Separation allows re-triggering. After debug-loop fixes a failure, "just re-verify" re-runs this skill without re-entering the PR creation flow.

The call graph is: `execute-plan → verify-before-done → [debug-loop | finish-branch]`. verify-before-done is a gate. finish-branch is a state transition.

## Anti-patterns

- **"Tests passed last run."** The previous run was against a different state. Always fresh.
- **Dumping full logs into chat.** First error + log path. 10KB of test output buries the signal.
- **Auto-fixing lint without confirming.** A fix that removes an import can break a re-export chain. Diff before anything is modified.
- **Running full suite on a 2-line diff.** Relevant-test strategy exists for this. Full suite is opt-in.
- **Continuing past a failure.** Lint fails → stop. Fix the blocker first. Downstream checks on a broken lint are noise.
- **Writing verify.json only on success.** Always write it — pass or fail. finish-branch reads it unconditionally.

## Composition

- **Callers:** execute-plan (end of plan); finish-branch (pre-PR gate); direct user invocation.
- **Calls:** ui-validation (frontend diff, pass `caller=verify-before-done`); debug-loop (any non-format failure, pass `caller=verify-before-done`).
- **Reads:** `plan.md` verification steps; language config files for tooling detection.
- **Writes:** `verify.json`; check logs to `verify/<timestamp>/`; reports format changes as advisory (never modifies files by default). Does not write to `plan.md`, `spec.md`, `handoff.md`.

Loose coupling: if ui-validation is not installed, skip the UI check and note it once. If debug-loop is not installed, print the handoff payload and stop.

## Open questions

1. **Shared-module threshold for full-suite promotion.** Directory name heuristic (`utils/`, `lib/`, `common/`) is a starting point — a concrete importer-count signal may be needed after dogfooding.
2. **Format scope.** `prettier --check .` on 3000 files vs. scoping to `git diff --name-only` output. Faster, but risks missing transitively dirtied files.
3. **ui-validation trigger threshold.** Any CSS/JSX change (aggressive) vs. only changes to rendered route components (conservative). A utility function importing a React component would fire ui-validation under the aggressive rule.
