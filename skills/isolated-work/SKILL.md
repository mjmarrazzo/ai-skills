---
name: isolated-work
description: Use this skill whenever the user says "sandbox this", "do this in a worktree", "isolated execution", "isolate this change", or whenever execute-plan signals a risky-plan (files changed > 10, root-config or lockfile touched, migrations present, CI/CD config modified, or a task is flagged irreversible). Creates a git worktree so the main checkout stays untouched throughout execution. Skip only when the user explicitly opts out ("just run it", "no worktree", "skip isolation", "I'll merge later").
---

# isolated-work

Run the wrapped operation in a git worktree. Main checkout untouched.

**Announce at start:** "Using isolated-work — creating a worktree so main checkout stays clean."

## When to trigger

Default is to suggest this before any `execute-plan` invocation that meets **one or more** of the following. User must explicitly opt out.

| Signal | Why it matters |
|---|---|
| Files changed in plan > 10 | A single bad edit is hard to chase down without a clean reference |
| Root-config touched: `package.json`, `tsconfig*.json`, `Cargo.toml`, `pyproject.toml`, `poetry.lock`, `go.mod`, `go.sum`, `.nvmrc`, `.node-version` | Affects every developer on the project; revert is painful if other work is stacked on top |
| Lockfile touched: `pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`, `Cargo.lock`, `poetry.lock` | Lockfile churn is easy to commit accidentally and hard to trace |
| Migration files present: `db/migrations/`, `prisma/migrations/`, `alembic/versions/`, `flyway/`, `liquibase/`, `*.migration.{ts,js,sql}` | Migrations are often irreversible; the branch should be reviewed before it lands on main |
| CI/CD config touched: `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/` | A bad CI change blocks everyone; always worth the 10 seconds to isolate |
| Plan contains a task flagged "revert is hard" or "irreversible" | Explicit signal from the planner |

**Mention but don't push** (user opts in explicitly):
- Plan touches 3–10 files with no root-config or lockfile changes
- Plan is purely additive (new files only, no edits to existing)
- User already on a feature branch and comfortable with `git reset` if needed

**Opt-out:** if user says "just run it", "no worktree", "skip isolation", or "I'll merge later" — proceed without a worktree and note it once.

## Plan path resolution

Resolve the plan path **before** entering the worktree. `EnterWorktree` clears CWD-dependent caches, including the `.claude-plans/` directory context. After entry, the worktree has no `.claude-plans/` (gitignored, never committed).

```bash
ORIGINAL_ROOT=$(git rev-parse --show-toplevel)
PLAN_PATH="$ORIGINAL_ROOT/.claude-plans/<active-dir>/plan.md"
```

Pass `PLAN_PATH` explicitly when invoking execute-plan. Do not rely on execute-plan discovering `plan.md` via cwd inference inside the worktree — that resolves to the worktree root, which has nothing.

## Path A — Native tools (preferred)

When `EnterWorktree` / `ExitWorktree` are available, always use them. The harness manages the worktree under `.claude/worktrees/<name>/`, handles gitignore, and switches the session CWD. Do not bypass it with `git worktree add` — that creates state the harness cannot manage.

```
EnterWorktree(name: "<slug>")
```

Default base is `origin/<default-branch>` (fresh start). The user can override this via the `worktree.baseRef` config setting (`head` = branch from current HEAD instead). Do not modify the setting; announce which base was used.

**Re-entry into an existing worktree:**
```
EnterWorktree(path: "<existing-worktree-path>")
```

Use `ExitWorktree(action: "keep")` when exiting a path-based entry.

## Path B — Manual git worktree fallback

Use only when `EnterWorktree` is unavailable.

Default location: `../<repo>-<slug>` (sibling checkout — clean mental model, no gitignore ceremony). Override priority: (1) user-specified, (2) `.worktrees/<slug>` if it already exists and is gitignored, (3) default sibling. For project-local paths, verify gitignore first (`git check-ignore -q .worktrees`); append if missing, with one-line user confirmation.

Always branch from `origin/<default>`, not from HEAD:

```bash
base=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||'); base=${base:-main}
git worktree add "../${repo}-${slug}" -b "${branch_name}" "origin/${base}"
```

## Branch creation

**Branch naming — MSP repos:** detect using any of:
1. Remote URL contains `nicusa` or `tylertech` (case-insensitive)
2. Current branch name matches `^MSP-\d+/`
3. `git config user.email` ends in `@tylertech.com`

Any match → use `MSP-<ticket>/<slug>`. Ticket number from the active workspace slug (e.g., `.claude-plans/2026-05-14-MSP-7032-add-feature/` → ticket `7032`). Otherwise use `<slug>` or whatever the user provides. Path A passes the slug as `name` to `EnterWorktree`; the harness creates the branch. Path B always branches from `origin/<default>`, never HEAD.

**Existing branch:** `git worktree add <path> <existing-branch>` (no `-b`) or `EnterWorktree(path: <existing-worktree-path>)` when the user says "continue work in `MSP-1234/my-feature`".

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

A fresh worktree starts without `node_modules/`, `target/`, `__pycache__/`, `.venv/`, and similar build artifacts.

| Condition | Action |
|---|---|
| Plan touches a lockfile | Fresh install mandatory before handing off to execute-plan. Stale artifacts from the main checkout produce incorrect results. |
| Plan does not touch lockfiles but the wrapped op needs build artifacts to compile/test | Fresh install in worktree. |
| Build artifacts optional (config-only edits, no compile step) | Skip install; let execute-plan handle per-task if needed. |

Auto-detect the package manager from the lockfile present in the worktree: `pnpm-lock.yaml` → `pnpm install`; `package-lock.json` → `npm ci`; `yarn.lock` → `yarn install`; `Cargo.toml` → `cargo build`; `pyproject.toml` → `poetry install`; `go.mod` → `go mod download`. Run it before handing off. If install fails, treat as lifecycle failure — do not proceed.

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

1. Confirm: "This will permanently delete the worktree at `<path>` and branch `<branch-name>`. Any uncommitted work will be lost. Confirm?"
2. On confirmation:
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

- **Using `git worktree add` when `EnterWorktree` is available.** Bypassing the harness creates state it cannot manage. Always check for Path A first — this is the #1 mistake from prior art.
- **Two execute-plan sessions against the same `.claude-plans/<dir>` workspace.** HARD constraint: undefined behavior. `progress.json` races are not handled and locking adds complexity without solving them. One execute-plan session per workspace. If a second session is needed, use a different workspace slug.
- **Worktree-as-a-fork.** This skill wraps a single bounded execution. Long-lived parallel development worktrees belong to the user's direct git workflow, not here.
- **Forgetting `plan.md` lives in the original checkout.** `.claude-plans/` is empty in the worktree. Resolve `PLAN_PATH` before entering; passing the wrong path to execute-plan is a silent failure.
- **Symlinking `node_modules` / `target` / `.venv` across worktrees.** See CI / build artifacts. The 30 seconds saved is not worth the bug class introduced.
- **Copying artifacts out of the worktree by hand.** If you're `cp`ing lockfiles or build outputs back to the main checkout, the plan needed a different structure. Exit is merge or PR, not manual copy.
- **Auto-removing the worktree on failure.** The worktree is the debugging surface. Keep it. Only remove after explicit abandon with user confirmation.
- **Branch deletion without a second confirmation.** Branches are cheap. Always require a second explicit confirmation for branch deletion, separate from worktree removal.

## Composition

- **Callers:** execute-plan (on risky-plan signals), or the user directly ("sandbox this", "do this in a worktree").
- **Wraps:** execute-plan primarily; any invasive operation (large refactor, schema migration) can use this as a wrapper.
- **Calls:** finish-branch on success (reads spec/handoff/decisions from original checkout); debug-loop on failure (optional hand-off).
- **Reads:** `plan.md` from the original checkout's `.claude-plans/<active-dir>/` — resolved before entering the worktree.
- **Writes:** nothing to the original checkout during execution. On Path B, may append to `.gitignore` (one-line user confirmation) if using a project-local worktree path.
- **Sibling fallback:** if a sibling is absent, mention it once and proceed. Surface `gh pr create` if `finish-branch` is missing; surface failure and stop if `debug-loop` is missing. Installed check: `~/.claude/skills/<name>/SKILL.md` OR `~/.claude/plugins/cache/**/skills/<name>/SKILL.md`.

## Open questions

1. **Path A branch naming.** `EnterWorktree(name: "<slug>")` passes the slug to the harness. Does the harness automatically apply the `MSP-XXXX/` convention, or does the skill need to rename the branch post-creation? Until confirmed via dogfooding, document as a constraint: "Path A branch names may not carry the MSP prefix automatically; verify after entry with `git branch --show-current`."
2. **`.claude-plans/` created inside the worktree.** If the user runs blueprint inside the worktree, the new workspace ends up unreachable after `ExitWorktree`. Treat as a user-error constraint for now; consider a warning on entry in a later version.
3. **Baseline test run.** Should isolated-work run baseline tests after setup (prior-art pattern) or delegate to execute-plan's first task? Current lean: delegate — execute-plan has per-task context about what "passing" means.
4. **`ExitWorktree` on Path A failure mid-execution.** If execute-plan fails partway and the user abandons, `discard_changes: true` will drop uncommitted changes. Should the skill list uncommitted files before confirming? Current lean: one confirmation is sufficient given the explicit user trigger.
