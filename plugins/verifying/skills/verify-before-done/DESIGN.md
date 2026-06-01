# verify-before-done — DESIGN

Status: draft. Replaces `SKILL.md` once user approves.

## Goal

Gate the moment when "I made the change" becomes "the change works." LLMs hallucinate
completion because an edit *looks right* — the diff matches the intent, the reasoning is
coherent. The claim of done follows naturally. It is usually wrong in a boring, fixable
way: a lint rule tripped, a type regressed two calls up the stack, one test that touches
the same module broke quietly.

This skill makes the cheapest objective checks non-skippable. It does not fix things. It
does not loop. It runs the checks in order, surfaces the first concrete signal of failure
to the appropriate next step, and reports green only when every check exits 0.

Not in scope: comprehensive visual regression suites (ui-validation), semantic review of
whether the implementation satisfies the spec (human gate in blueprint), security
scanning, or performance testing. Those belong elsewhere.

## When to trigger

Pushy on "done" language, quiet otherwise.

Trigger phrases: end of execute-plan's final task (automatic); "is this ready?", "verify
before I commit", "lgtm check", "run the checks", "done with this task", "ready to
merge".

Opt-out: "skip checks", "quick commit", "just do it", "I know the tests are broken".
Treat these as genuine opt-outs — don't nag.

Skip without prompting when: no diff against the branch base; diff is docs-only (`.md`,
`.txt`, `.rst`); diff is generated-files-only (lockfiles, `.pb.go`, migration snapshots)
with no tooling configured against them.

## Tooling detection

Detection runs once, before any check. Inspect the workspace root and any
packages whose files appear in the diff. Stop at first match per category.

### TypeScript / JavaScript

| Detection signal | Check | Command |
|---|---|---|
| `package.json` `scripts.lint` | Lint | `npm run lint` / `pnpm lint` |
| `package.json` `scripts.typecheck` | Typecheck | `npm run typecheck` |
| `tsconfig.json` (no explicit script) | Typecheck fallback | `npx tsc --noEmit` |
| `vitest.config.*` or `jest.config.*` | Tests | `npx vitest run` / `npx jest` |
| `eslint.config.*` / `.eslintrc*` (no script) | Lint fallback | `npx eslint .` |
| `prettier.config.*` / `.prettierrc*` | Format check | `npx prettier --check .` |

Use the `scripts` field as ground truth; only fall back to direct invocations when
scripts are absent.

### Python

| Detection signal | Check | Command |
|---|---|---|
| `pyproject.toml` `[tool.ruff]` | Lint | `ruff check .` |
| `pyproject.toml` `[tool.mypy]` or `[tool.pyright]` | Typecheck | `mypy .` / `pyright` |
| `pytest.ini`, `pyproject.toml [tool.pytest]`, `conftest.py` | Tests | `pytest` |
| `setup.cfg [flake8]` (no ruff) | Lint legacy | `flake8 .` |

Prefer ruff over flake8 when both present.

### Go

| Detection signal | Check | Command |
|---|---|---|
| `go.mod` | Build + vet | `go build ./...` then `go vet ./...` |
| `go.mod` | Tests | `go test -short ./...` |
| `.golangci-lint.yml` / `.golangci.yml` | Lint | `golangci-lint run` |

### Rust

| Detection signal | Check | Command |
|---|---|---|
| `Cargo.toml` | Check | `cargo check` |
| `Cargo.toml` | Lint | `cargo clippy -- -D warnings` |
| `Cargo.toml` | Tests | `cargo test` |
| `rustfmt.toml` / `.rustfmt.toml` | Format | `cargo fmt -- --check` |

`cargo check` is faster than `cargo build` and still catches type errors; run it
before clippy.

### JVM / Kotlin (Gradle)

| Detection signal | Check | Command |
|---|---|---|
| `build.gradle.kts` / `build.gradle` | Build + tests | `./gradlew build` |
| Gradle build with ktlint plugin | Lint | `./gradlew ktlintCheck` |
| Gradle build with detekt | Static analysis | `./gradlew detekt` |

For MSP repos: check whether `AWS_PROFILE` / `AWS_REGION` are set before running
integration-flavored test tasks. Print a one-line reminder if they're unset.

### Multi-language monorepos

Check for a repo-level orchestrator first:
- **nx**: `nx.json` → `npx nx affected --target=lint,typecheck,test --base=origin/main`
- **Turborepo**: `turbo.json` → `npx turbo run lint typecheck test --filter=...[origin/main]`
- **Lerna**: `lerna.json` → `npx lerna run lint test --since=origin/main`
- **None**: run per-package detection within each package that has a changed file

Prefer the orchestrator's "affected" mode — it avoids rebuilding the whole graph.

## Order of checks

Cheapest first: **format → lint → typecheck → tests → plan verifications → ui-validation**

- **Format** first: fastest check (~5s), and a format failure makes subsequent lint output
  noisy. Formatters auto-fix before continuing (see auto-fix policy).
- **Lint** before typecheck: syntactic errors block type inference; cascading type errors
  obscure the real cause.
- **Typecheck** before tests: a test passing against a type-unsafe call is not meaningful.
- **Tests**: most expensive; only run after static checks are clean.
- **Plan verifications**: integration-flavored, always run if plan.md has them (see below).
- **ui-validation**: browser checks are the slowest; run only when frontend files
  appear in the diff (`.tsx`, `.jsx`, `.vue`, `.svelte`, `.css`, `.scss`, HTML templates).
  If no plan.md surface list is present, infer routes from changed files or ask the user.

Abort on first failure class. If lint exits non-zero, do not proceed to typecheck.
Downstream checks on a broken lint are noise, not signal.

The user may specify `verify --tests-first` to skip straight to tests (useful mid-TDD
cycle). Accept it without argument.

## Relevant tests strategy

Default: **changed-file matching + plan verifications. Full suite is opt-in.**

1. For each modified source file (`src/foo.ts`), run co-located tests: `src/foo.test.ts`,
   `src/foo.spec.ts`, `__tests__/foo.ts`, `tests/foo_test.py`, `foo_test.go`, etc.
2. If no co-located test exists, run all tests in the same directory.
3. If changed files span more than one package boundary, or if the diff touches a file
   imported by multiple modules, promote to full suite and print the reason.
4. `verify --full` forces the complete suite regardless of diff scope.

Target: under 60 seconds on a typical task-sized diff. A verify that takes 8 minutes
gets skipped; one that takes 30 seconds gets run every time.

## Plan verifications integration

Plan.md tasks include explicit verification steps:
```
Run: pytest tests/foo/test_bar.py::test_x -v
Expected: PASS
```

Policy: **re-run every plan verification on every verify-before-done invocation.**

Do not trust that execute-plan ran them per task. Task-level checks give mid-flight
feedback; the final gate confirms the whole set of plan criteria still holds after all
tasks complete. This is the cheapest form of integration testing the plan provides — and
the most likely place that an earlier task's fix quietly breaks a later task's criterion.

Run plan verifications in listed order after the test suite. If any fail, treat as a test
failure and hand off to debug-loop with the exact command and its first-error output.

If plan.md is absent or has no verification steps, skip this phase silently.

## Auto-fix policy

**Formatters — yes, automatically.** Prettier, black, rustfmt, gofmt, ktlint (format
mode) are deterministic and idempotent. If the format check fails, re-run the formatter
in fix mode, print the file list with diff stat, then continue to lint. Never commit the
formatted files — reporting them is enough.

```
Auto-formatted 2 files:
  src/auth.ts        (+2/-2 whitespace)
  tests/auth.test.ts (+1/-1 trailing newline)
```

**Linters with `--fix` — no by default.** `eslint --fix`, `ruff --fix`, `clippy --fix`
can change program behavior: removing an import used via a re-export, rewriting a loop,
eliding a variable wired up in the next commit. The failure mode is silent. Default is
to report errors and hand off.

Opt-in: `verify --autofix-lint`. When set, run autofix, print the full diff, confirm
with the user before continuing to typecheck.

**Imports and unused vars — never auto-remove.** Highest risk-to-benefit ratio; too
many legitimate patterns look like dead code mid-refactor.

## Output format

Single report block, terminal-friendly:

```
verify-before-done — <slug>
─────────────────────────────────────────────────────
✓ format          prettier           2 files fixed      0.8s
✓ lint            eslint             0 errors           3.2s
✓ typecheck       tsc --noEmit       0 errors           6.1s
✓ tests           vitest run         14/14 passed       4.9s
  ↳ relevant: src/auth.ts, src/auth.test.ts
✓ plan:verify     pytest test_x -v   PASSED             1.2s
✓ ui              ui-validation      2/2 surfaces ok    8.4s

6 checks passed — 24.6s total
Ready. Logs: .claude-plans/<dir>/verify/<timestamp>/
```

On failure: first 20 lines of stderr from the failing command, then the log path.
Do not dump full logs into chat. Abort the chain.

Artifacts land under `.claude-plans/<active-dir>/verify/<timestamp>/` when a blueprint
workspace is active, otherwise `./verify-results/<timestamp>/`. Each check writes its
stdout+stderr to a numbered log: `01-format.log`, `02-lint.log`, etc.

## Failure handling

| Failure class | First action | Handoff |
|---|---|---|
| Format | Auto-fix, print file list, continue | None |
| Lint — whitespace / import order | Report, suggest `verify --autofix-lint` | User decides |
| Lint — semantic (unused-vars, unsafe equality) | Report first error: file:line, rule name | User: "lint error in `src/auth.ts:42` — fix or suppress?" |
| Typecheck | Report first error: file:line:col, message | debug-loop: typecheck failure + log path |
| Test failure | Report failing test name + assertion (first failure only) | debug-loop: test name + assertion message |
| Plan verification | Report command + exit code + first error line | debug-loop: verification command + log path |
| UI (ui-validation) | ui-validation's own report | ui-validation hands to debug-loop; do not duplicate |

If debug-loop is not installed: print the handoff payload verbatim and stop. One-line
notice: "debug-loop not installed — fix the above manually, then re-run verify-before-done."

Never retry a failing check. Flaky tests are a separate problem. The gate stops at the
first failure and hands off.

## Worktree awareness

If execute-plan launched via isolated-work (git worktree), verify-before-done runs inside
that worktree — the working directory is already correct. No special handling required.

One edge case: tooling that resolves config files by walking upward (`eslint`, `pyproject`)
will work correctly. Tooling that uses hardcoded paths relative to the main repo root may
not. If any command exits with "config not found" rather than a real lint/type error,
suspect the worktree root before the code.

## Why separate from finish-branch

Merging them couples *verifying* to *publishing*. That coupling is wrong for three
reasons:

1. verify-before-done is called from execute-plan at plan end, not only before a PR.
   Verification happens whenever a task is declared done.
2. finish-branch invokes verify-before-done as a precondition. A lint failure aborting
   the `gh pr create` flow before the user chose a title is a broken UX.
3. Separation allows re-triggering. After debug-loop fixes a failure, "just re-verify"
   re-runs this skill without re-entering the PR creation flow.

The call graph is: `execute-plan → verify-before-done → [debug-loop | finish-branch]`.
verify-before-done is a gate. finish-branch is a state transition. They are different
shapes.

## Anti-patterns

- **"Tests passed last run."** The previous run was against a different state. Always
  fresh. This is the entire point.
- **Dumping full logs into chat.** First error + log path. 10KB of test output buries
  the signal.
- **Auto-fixing lint without reporting what changed.** A fix that removes an import can
  break a re-export chain. Diff before anything is modified.
- **Running full suite on a 2-line diff.** Relevant-test strategy exists for this.
  Full-suite is opt-in; slow verifies get skipped.
- **Continuing past a failure.** Lint fails → stop. Downstream checks on a broken lint
  are noise, not signal. Fix the blocker first.

## Composition

- **Callers:** execute-plan (end of plan execution); finish-branch (pre-PR gate); direct
  user invocation.
- **Calls:** ui-validation when frontend files appear in the diff; debug-loop on any
  non-format failure.
- **Reads:** plan.md verification steps; language config files for tooling detection.
- **Writes:** check logs to `.claude-plans/<active>/verify/<timestamp>/`; formatted
  source files when formatter runs (always announced, never silent). Does not write to
  plan.md, spec.md, handoff.md.

Loose coupling: if ui-validation is not installed, skip the UI check and note it once:
"ui-validation not installed — skipping browser verification for changed frontend files."
If debug-loop is not installed, print the handoff payload and stop.

## Open questions to resolve before SKILL.md

1. **Shared-module threshold for full-suite promotion.** "Diff touches a shared utility"
   is the heuristic — what makes something shared? Number of importers? Directory name
   (`utils/`, `lib/`, `common/`)? A concrete signal is needed.
2. **Format changed-files-only vs whole tree.** Running `prettier --check` on 3000 files
   is slower than formatting the 3 changed ones. Consider scoping the formatter to
   `git diff --name-only` output rather than `.` — faster, but risks missing a file that
   was transitively dirtied.
3. **ui-validation trigger threshold.** Any CSS/JSX change (aggressive) or only changes
   to rendered route components (conservative)? A utility function that imports a React
   component would fire ui-validation under the aggressive rule.
