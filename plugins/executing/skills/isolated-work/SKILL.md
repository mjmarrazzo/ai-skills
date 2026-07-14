---
name: isolated-work
description: Use this skill whenever the user says "sandbox this", "do this in a worktree", "isolated execution", "isolate this change", "don't touch my checkout", or when invoked by execute-plan with caller=execute-plan on a risky plan (the risky-signal table lives in the body). Creates a git worktree so the main checkout stays untouched throughout execution. Skip only when the user explicitly opts out ("just run it", "no worktree", "skip isolation", "I'll merge later").
---

# isolated-work

Run the wrapped operation in a git worktree. Main checkout untouched.

**Announce at start:** "Using isolated-work — creating a worktree so main checkout stays clean."

## When to trigger

Default is to suggest this before any `execute-plan` invocation that meets **one or more** of the following. User must explicitly opt out. This table is the canonical risky-signal list — `execute-plan` points here rather than carrying its own copy.

| Signal | Why it matters |
|---|---|
| Files changed in plan > 10 | A single bad edit is hard to chase down without a clean reference |
| Root-config touched: `package.json`, `tsconfig*.json`, `Cargo.toml`, `pyproject.toml`, `poetry.lock`, `go.mod`, `go.sum`, `.nvmrc`, `.node-version` | Affects every developer on the project; revert is painful if other work is stacked on top |
| Lockfile touched: `pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`, `Cargo.lock`, `poetry.lock` | Lockfile churn is easy to commit accidentally and hard to trace |
| Migration files present: `db/migrations/`, `prisma/migrations/`, `alembic/versions/`, `flyway/`, `liquibase/`, `*.migration.{ts,js,sql}` | Migrations are often irreversible; the branch should be reviewed before it lands on main |
| CI/CD config touched: `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/` | A bad CI change blocks everyone; always worth the 10 seconds to isolate |
| Auth/security paths: `auth/`, `security/`, `middleware/`, or paths matching `*permission*` / `*authz*` | High blast radius; mistakes here warrant a clean reference checkout |
| Architectural verbs in the plan's `**Goal:**` line: `rename`, `extract`, `consolidate`, `rewrite`, `migrate`, `deprecate` | Structural changes ripple beyond the named files |
| Deletion-heavy: more `Delete:` than `Create:` entries in the plan's file map | Deletions are the hardest edits to recover from a dirty checkout |
| Plan contains a task flagged "revert is hard" or "irreversible" | Explicit signal from the planner |

After matching, surface the specific signal in the suggestion (e.g. "This plan touches 18 files including `package.json` at repo root").

**Mention but don't push** (user opts in explicitly):
- Plan touches 3–10 files with no root-config or lockfile changes
- Plan is purely additive (new files only, no edits to existing)
- User already on a feature branch and comfortable with `git reset` if needed

**Opt-out:** if user says "just run it", "no worktree", "skip isolation", or "I'll merge later" — proceed without a worktree and note it once.

## Plan path resolution

Resolve the plan path **before** entering the worktree. Expect that `EnterWorktree` clears CWD-dependent state, including the `.claude-plans/` directory context. After entry, the worktree has no `.claude-plans/` (gitignored, never committed).

```bash
ORIGINAL_ROOT=$(git rev-parse --show-toplevel)
PLAN_PATH="$ORIGINAL_ROOT/.claude-plans/<active-dir>/$(ls "$ORIGINAL_ROOT/.claude-plans/<active-dir>" | grep '^plan\.v.*\.md$' | sort -V | tail -1)"
```

Pass `PLAN_PATH` explicitly when invoking execute-plan. Do not rely on execute-plan discovering the plan via cwd inference inside the worktree — that resolves to the worktree root, which has nothing.

## Path A — Native tools (preferred)

When `EnterWorktree` / `ExitWorktree` are available, always use them. If they appear as deferred tools, load them via `ToolSearch` (`select:EnterWorktree,ExitWorktree`) before calling. The harness manages the worktree under `.claude/worktrees/<name>/`, handles gitignore, and switches the session CWD.

```
EnterWorktree(name: "<slug>")          # new worktree
EnterWorktree(path: "<existing-path>") # re-entry; exit with action: "keep"
```

Default base is `origin/<default-branch>`. The user can override via `worktree.baseRef` config (`head` = branch from current HEAD). Do not modify the setting; announce which base was used.

## Path B — Manual git worktree fallback

Use only when `EnterWorktree` is unavailable.

Default location: `../<repo>-<slug>` (sibling checkout — clean mental model, no gitignore ceremony). Override priority: (1) user-specified, (2) `.worktrees/<slug>` if it already exists and is gitignored, (3) default sibling. For project-local paths, verify gitignore first (`git check-ignore -q .worktrees`); append if missing, with one-line user confirmation.

Always branch from `origin/<default>`, not from HEAD:

```bash
base=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||'); base=${base:-main}
git worktree add "../${repo}-${slug}" -b "${branch_name}" "origin/${base}"
```

## Branch creation

**Branch naming — repos with a ticket convention:** A ticket key is detected from the workspace slug or a branch prefix matching `^[A-Z][A-Z0-9]+-\d+`, or from a `CLAUDE.md` convention. When detected, use `<KEY>/<slug>`; the ticket key comes from the active workspace slug (e.g., `.claude-plans/2026-05-14-PROJ-1234-add-feature/` → key `PROJ-1234`). Otherwise use `<slug>` or whatever the user provides. Path A passes the slug as `name` to `EnterWorktree`; the harness creates the branch — expect that the harness may not apply the ticket-prefix convention automatically, so verify after entry with `git branch --show-current`. Path B always branches from `origin/<default>`, never HEAD.

**Existing branch:** `git worktree add <path> <existing-branch>` (no `-b`) or `EnterWorktree(path: <existing-worktree-path>)` when the user says "continue work in `PROJ-1234/my-feature`".

## Working-directory hand-off

After entering the worktree, print:

```
isolated-work — worktree ready
  Path:   <worktree-path>
  Branch: <branch-name>  (based on origin/<base>)
  Plan:   <PLAN_PATH>
Handing off to execute-plan. Main checkout untouched.
```

Then invoke execute-plan with the resolved plan path:

> "Read your plan from `$PLAN_PATH`. caller=isolated-work"

The `caller=isolated-work` flag tells execute-plan not to re-suggest isolated-work (its "already inside worktree" guard handles the cycle; pass the flag for consistency).

Use `TodoWrite` to track the three phases — enter, handoff, exit — so progress is visible if the session is long-running.

## CI / build artifacts

A fresh worktree starts without `node_modules/`, `target/`, `__pycache__/`, `.venv/`, and similar build artifacts. Run a fresh install before handing off to execute-plan whenever the plan touches a lockfile OR the wrapped operation needs build artifacts to compile/test. Skip install only for config-only edits with no compile step (let execute-plan handle per-task).

Auto-detect package manager from the lockfile present: `pnpm-lock.yaml` → `pnpm install`; `package-lock.json` → `npm ci`; `yarn.lock` → `yarn install`; `Cargo.toml` → `cargo build`; `pyproject.toml` → `poetry install`; `go.mod` → `go mod download`. If install fails, treat as lifecycle failure — do not proceed.

**NEVER symlink `node_modules/`, `target/`, `.venv/`, or any build artifact directory** from the main checkout into the worktree. Cross-worktree symlinks embed paths and platform assumptions from the main checkout's last run; the 30 seconds saved is not worth the class of bugs introduced.

## Lifecycle: success / failure / abandon

### Success

Surface a completion block — do not auto-merge, auto-PR, or auto-cleanup:

```
isolated-work — execution complete
  Worktree: <path>   Branch: <branch-name>

To PR:        invoke finish-branch (reads spec/handoff/decisions from original checkout)
              or: cd <path> && gh pr create --base <base>
To clean up:  ExitWorktree(action: "remove")      (Path A)
              git worktree remove <path>           (Path B, after merge)
```

### Failure

1. Surface the failure output as-is. Do not retry.
2. Keep the worktree — it contains partial state for diagnosis.
3. Offer but do not run: `ExitWorktree(action: "remove", discard_changes: true)` (Path A) or `git worktree remove --force <path>` (Path B).
4. If `debug-loop` is installed, offer to hand off. If not, surface the failure and stop.

### Abandon

User says "scrap this", "forget it", "clean this up", or equivalent.

1. Run `git status --short` in the worktree and show the output, so "uncommitted work will be lost" is concrete rather than hypothetical.
2. Confirm: "This will permanently delete the worktree at `<path>` and branch `<branch-name>`. The uncommitted changes listed above will be lost. Confirm?"
3. On confirmation:
   - **Path A:** `ExitWorktree(action: "remove", discard_changes: true)`
   - **Path B:** `git worktree remove --force <path>` — then ask separately: "Also delete branch `<branch-name>`? (y/N)"

Branch deletion on abandon is **opt-in, confirmed separately**. The default is to leave the branch — it costs nothing and avoids surprise data loss if the user changes their mind.

## Re-entry

If the user returns and the worktree still exists: Path A — `EnterWorktree(path: <existing-worktree-path>)`, exit with `action: "keep"`. Path B — `cd <path>` and continue as normal git workflow. The skill's work is done once the worktree is created and execute-plan has been handed off — do not imply this skill needs to be re-invoked.

## Concurrent worktrees

Multiple worktrees from the same repo are fully supported by git. Before creating a new one:

```bash
git worktree list --porcelain
```

Check for:
1. **Matching slug:** if a worktree path already matches `*-<slug>` or `.worktrees/<slug>`, offer to reuse rather than duplicate.
2. **Name collision:** if the exact target path or branch name exists, append `-2`, `-3`, etc. until the name is free. Do not silently clobber.
3. **Many existing worktrees (> 3):** surface a brief list so the user can decide whether to clean up before adding another.

```
A worktree for '<slug>' already exists at <path> on branch <branch-name>.
  (a) Enter the existing worktree and continue
  (b) Create a new worktree with name <slug-2>
  (c) Cancel
```

## Cleanup

`git worktree list` is the authoritative source of truth. This skill does not maintain its own registry.

On invocation, run `git worktree list --porcelain` and check for worktrees matching `../<repo>-*` or `.worktrees/*` that are >14 days old with no uncommitted changes. Surface a one-liner if found:

```
Note: old worktree detected — <path> (<age>). Clean up: git worktree remove <path>
```

Do not auto-clean. The user may have parked work there intentionally. Path A worktrees (under `.claude/worktrees/`) are managed by the harness — do not touch them.

## Anti-patterns

- **Using `git worktree add` when `EnterWorktree` is available.** Always check for Path A first; bypassing the harness creates state it cannot manage.
- **Two execute-plan sessions against the same `.claude-plans/<dir>` workspace.** HARD constraint — `progress.json` races are unhandled; a second session needs a different workspace slug.
- **Worktree-as-a-fork.** This skill wraps a single bounded execution; long-lived parallel worktrees belong to the user's direct git workflow.
- **Forgetting the plan lives in the original checkout.** `.claude-plans/` is empty in the worktree; resolve `PLAN_PATH` before entering.
- **Symlinking `node_modules` / `target` / `.venv` across worktrees.** Run a fresh install instead (see CI / build artifacts).
- **Copying artifacts out of the worktree by hand.** Exit is merge or PR, not manual copy.
- **Auto-removing the worktree on failure.** The worktree is the debugging surface; only remove after explicit abandon with user confirmation.
- **Branch deletion without a second confirmation.** Always confirm branch deletion separately from worktree removal.

## Composition

- **Callers:** execute-plan (on risky-plan signals), or the user directly ("sandbox this", "do this in a worktree").
- **Wraps:** execute-plan primarily; any invasive operation (large refactor, schema migration) can use this as a wrapper.
- **Calls:** finish-branch on success (reads spec/handoff/decisions from original checkout); debug-loop on failure (optional hand-off).
- **Reads:** the current plan (highest-N `plan.v*.md`) from the original checkout's `.claude-plans/<active-dir>/` — resolved before entering the worktree.
- **Writes:** nothing to the original checkout during execution. On Path B, may append to `.gitignore` (one-line user confirmation) if using a project-local worktree path.
- **Sibling fallback:** if a sibling is absent, mention it once and proceed. Surface `gh pr create` if `finish-branch` is missing; surface failure and stop if `debug-loop` is missing. Installed check: `~/.claude/skills/<name>/SKILL.md` OR `~/.claude/plugins/cache/**/skills/<name>/SKILL.md`.
