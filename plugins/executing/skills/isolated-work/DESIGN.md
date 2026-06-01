# isolated-work — DESIGN

Status: draft. Replaces `SKILL.md` once user approves.

## Goal

Run risky execution inside a git worktree so the main checkout stays untouched. If something goes wrong mid-execution — a bad migration, a lockfile rewrite that diverges, a root-config change that breaks other devs — the damage is confined to the worktree branch and cleanup is `ExitWorktree` with `action: "remove"`.

Not in scope: parallel multi-branch development, reviewing PRs in isolation, or persistent multi-task isolation. This skill wraps a single execution (typically `execute-plan`) and tears down cleanly when done.

## When to trigger

Pushy when execution is risky, quiet when it isn't.

### Always suggest (present as default, user must explicitly opt out)

Suggest isolated-work before launching `execute-plan` when the plan meets **any** of these conditions:

| Signal | Why it matters |
|---|---|
| Files changed in plan > 10 | Past that count, a single bad edit is hard to chase down without a clean reference |
| Root-config touched: `package.json`, `tsconfig*.json`, `Cargo.toml`, `pyproject.toml`, `poetry.lock`, `go.mod`, `go.sum`, `.nvmrc`, `.node-version` | Affects every developer on the project; revert is painful if other work is stacked on top |
| Lockfile touched: `pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`, `Cargo.lock`, `poetry.lock` | Lockfile churn is easy to commit accidentally and hard to trace |
| Migration files present: paths matching `db/migrations/`, `prisma/migrations/`, `alembic/versions/`, `flyway/`, `liquibase/`, `*.migration.{ts,js,sql}` | Migrations are often irreversible; the branch should be reviewed before it lands on main |
| CI/CD config touched: `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/` | A bad CI change blocks everyone; always worth the 10 seconds to isolate |
| Plan contains a task flagged "revert is hard" or "irreversible" | Explicit signal from the planner |

**Opt-out phrase:** user says "just run it", "no worktree", "skip isolation", or "I'll merge later" → proceed without a worktree and note it once.

### Mention but don't push (user explicitly opts in)

- Plan touches 3–10 files with no root-config or lockfile changes
- Plan is purely additive (new files only, no edits to existing)
- User already on a feature branch and comfortable with `git reset` if needed

## Worktree path policy

Two execution paths, checked on every invocation in order.

### Path A — Native tools (preferred)

When `EnterWorktree` / `ExitWorktree` are available, use them unconditionally. The harness places the worktree under `.claude/worktrees/<slug>/`, handles gitignore, and switches the session CWD. Do not bypass it with `git worktree add` — that creates state the harness cannot manage.

Branch base is governed by `worktree.baseRef` (`fresh` = origin/<default-branch>, `head` = current HEAD). The skill does not override this; announce which base was used.

**Plans directory:** `EnterWorktree` clears the CWD-dependent plans cache. The worktree has no `.claude-plans/` (gitignored, never committed). Always resolve the plan path before entering:
```bash
ORIGINAL_ROOT=$(git rev-parse --show-toplevel)
PLAN_PATH="$ORIGINAL_ROOT/.claude-plans/<active-dir>/plan.md"
```
Pass `PLAN_PATH` explicitly to execute-plan. If execute-plan infers plan.md from its cwd, it will find nothing in the worktree.

### Path B — Manual git worktree fallback

Use only when `EnterWorktree` is unavailable.

Default path: `../<repo>-<slug>` (sibling checkout — clean mental model, no gitignore ceremony). Override priority: (1) user-specified, (2) `.worktrees/<slug>` if it already exists and is gitignored, (3) default sibling. For project-local paths only, verify gitignore first (`git check-ignore -q .worktrees`); append if missing, with one-line user confirmation.

## Branch creation

**Path A:** pass the slug as `name` to `EnterWorktree`; the harness creates the branch.

**Path B:** always branch from `origin/<default>`, not from HEAD — keeps the worktree clean of in-progress changes from the main checkout.
```bash
base=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||'); base=${base:-main}
git worktree add "../${repo}-${slug}" -b "${branch_name}" "origin/${base}"
```

**Branch naming:** check for MSP context (`git remote get-url origin | grep -q 'nicusa'` or current branch matches `MSP-\d+/`) and apply `MSP-XXXX/<slug>`; otherwise use `<slug>` or whatever the user provides.

**Existing branch:** `git worktree add <path> <existing-branch>` (no `-b`) or `EnterWorktree(path: <existing-worktree-path>)`. Use when the user says "continue work in `MSP-1234/my-feature`".

## Working-directory hand-off

The wrapped operation runs with the worktree as its cwd. The plan path must be resolved before entering — see Worktree path policy above.

Pass `PLAN_PATH` as an explicit context string when invoking execute-plan: "Read your plan from `$PLAN_PATH`." Don't let execute-plan discover `plan.md` via cwd inference inside the worktree — that resolves to the worktree root, which has no `.claude-plans/`.

**Announce at start:** after entering the worktree, print:
```
isolated-work — worktree ready
  Path:   <worktree-path>
  Branch: <branch-name>  (based on origin/<base>)
  Plan:   <PLAN_PATH>
Handing off to execute-plan. Main checkout untouched.
```

## Lifecycle: success / failure / abandon

### Success

The wrapped operation completed, tests are green, user is ready to merge or PR.

Surface a completion block — do not auto-merge, auto-PR, or auto-cleanup:

```
isolated-work — execution complete
  Worktree: <path>   Branch: <branch-name>

To PR:        invoke finish-branch (reads spec/handoff/decisions from original checkout)
              or: cd <path> && gh pr create --base <base>
To clean up:  ExitWorktree(action: "remove")      (Path A)
              git worktree remove <path>           (Path B, after merge)
```

The `finish-branch` skill is the recommended PR path (reads `spec.md`, `handoff.md`, `decisions.md` from the original checkout). If absent, surface the `gh pr create` command directly.

### Failure

The wrapped operation hit something unrecoverable (tests failing, migration error, dependency conflict).

1. Surface the failure output as-is; do not retry.
2. Keep the worktree — it contains the partial state for diagnosis.
3. Offer but do not run: `ExitWorktree(action: "remove", discard_changes: true)` (Path A) or `git worktree remove --force <path>` (Path B).
4. If `debug-loop` is installed, offer to hand off. If not, surface the failure and stop.

### Abandon

User says "scrap this", "forget it", "clean this up", or equivalent.

1. Confirm: "This will permanently delete the worktree at `<path>` and branch `<branch-name>`. Any uncommitted work will be lost. Confirm?"
2. On confirmation:

**Path A:**
```
ExitWorktree(action: "remove", discard_changes: true)
```

**Path B:**
```bash
git worktree remove --force <path>
# Do NOT delete the branch without a second explicit user confirmation:
# "Also delete branch <branch-name>? (y/N)"
```

Branch deletion on abandon is **opt-in, confirmed separately**. The default is to leave the branch in place — it costs nothing and avoids surprise data loss if the user changes their mind.

## Re-entry

If the user returns tomorrow and the worktree still exists on disk:

- **Path A:** the session no longer has `EnterWorktree` context from the previous session. Use `EnterWorktree(path: <existing-worktree-path>)` to re-enter. `ExitWorktree` will not remove this worktree (entering via `path` is treated as an external worktree). Use `action: "keep"` to exit.
- **Path B:** the worktree is just a normal git working tree. `cd <path>` and continue. No skill involvement required.

In both cases, the skill's work is done once the worktree is created and execute-plan has been handed off. Re-entry is the user's normal git workflow — `cd <path>` and continue. Do not imply the skill needs to be re-invoked.

## Concurrent worktrees

Multiple worktrees from the same repo are fully supported by git. The skill must not assume it owns the only worktree.

**Before creating a new worktree:**
```bash
git worktree list --porcelain
```

Check the output for:
1. **Matching slug:** if a worktree path already matches `*-<slug>` or `.worktrees/<slug>`, offer to reuse it rather than create a duplicate. This is the common "I already started this" case.
2. **Name collision:** if the exact target path or branch name exists, append `-2`, `-3`, etc. to the slug until the name is free. Do not silently clobber.
3. **Many existing worktrees (> 3):** surface a brief list so the user can decide if they want to clean any up before adding another.

**Reuse prompt:**
```
A worktree for '<slug>' already exists at <path> on branch <branch-name>.
  (a) Enter the existing worktree and continue
  (b) Create a new worktree with name <slug-2>
  (c) Cancel
```

## CI / build artifacts

A fresh worktree starts without `node_modules/`, `target/`, `__pycache__/`, `.venv/`, and similar build artifacts.

**Default policy: fresh install when needed, otherwise skip.**

| Condition | Action |
|---|---|
| Plan touches a lockfile (any of: `pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`, `Cargo.lock`, `poetry.lock`) | Fresh install mandatory in the worktree. Stale artifacts from the main checkout would produce incorrect results. |
| Plan does NOT touch lockfiles but the wrapped op needs `node_modules` to compile/test | Fresh install in worktree. |
| Build artifacts are optional (e.g., the plan only edits config files, no compile step) | Skip install; let execute-plan handle it per-task if needed. |

**Do not symlink `node_modules/`, `target/`, `.venv/`, or any build artifact directory from the main checkout into the worktree.** Cross-worktree symlinks for binary outputs are a footgun: compiled artifacts may embed paths, platform assumptions, or partial build state from the main checkout's last run. The 30 seconds saved is not worth the class of bugs introduced.

Auto-detect the package manager from the lockfile present in the worktree (`pnpm-lock.yaml` → `pnpm install`; `package-lock.json` → `npm ci`; `yarn.lock` → `yarn install`; `Cargo.toml` → `cargo build`; `pyproject.toml` → `poetry install`; `go.mod` → `go mod download`). Run it before handing off to execute-plan. If install fails, treat as lifecycle failure — do not proceed.

## Cleanup and storage

`git worktree list` is the authoritative source of truth. The skill does not maintain its own registry.

On invocation, run `git worktree list --porcelain` and check for worktrees matching this skill's naming convention (`../<repo>-*` or `.worktrees/*`) that are >14 days old with no uncommitted changes. Surface a one-liner if found:
```
Note: old worktrees detected — <path> (<age>). Clean up: git worktree remove <path>
```

Do not auto-clean. The user may have parked work there intentionally. Path A worktrees (under `.claude/worktrees/`) are managed by the harness — do not touch them. No background scheduling, polling, or hooks.

## Anti-patterns

- **Using `git worktree add` when `EnterWorktree` is available.** Bypassing the harness creates state it cannot manage. Always check for Path A first — it's the #1 mistake from the prior art.
- **Worktree-as-a-fork.** This skill wraps a single bounded execution. Long-lived parallel development worktrees belong to the user's direct git workflow, not here.
- **Copying artifacts out of the worktree by hand.** If you're `cp`ing build outputs or lockfiles back to the main checkout, the plan needed a different structure. Exit is merge or PR, not manual copy.
- **Symlinking `node_modules` / `target` / `.venv` across worktrees.** See CI/Build Artifacts. Don't do it.
- **Forgetting `plan.md` lives in the original checkout.** `.claude-plans/` is empty in the worktree. Resolve `PLAN_PATH` before entering; passing the wrong path to execute-plan is a silent failure.
- **Auto-removing the worktree on failure.** The worktree is the debugging surface. Keep it. Only remove after explicit "abandon" with user confirmation.
- **Branch deletion without a second confirmation.** Branches are cheap. Require explicit confirmation for branch deletion, separate from worktree removal.

## Composition

- **Caller:** execute-plan suggests isolated-work when trigger conditions are met; user can also invoke directly ("do this in a worktree", "sandbox this").
- **Wraps:** execute-plan primarily; any invasive skill (a future `migrate-schema`, a large refactor) can call this as a wrapper.
- **Calls:** finish-branch (on success); debug-loop (on failure, optional hand-off).
- **Reads:** `plan.md` from the original checkout's `.claude-plans/<active-dir>/` — resolved before entering the worktree.
- **Writes:** nothing to the original checkout during execution. On Path B, may append to `.gitignore` (one-line user confirmation) if using a project-local worktree path.
- **Sibling fallback:** if a sibling is absent, mention it once and proceed. Surface `gh pr create` if `finish-branch` is missing; stop and surface failure if `debug-loop` is missing.

## Open questions to resolve before SKILL.md

1. **`worktree.baseRef` surfacing.** The skill currently documents this setting but does not modify it. Should isolated-work prompt the user to confirm the base-ref policy before entering, or trust the harness default silently?
2. **Path A branch naming.** `EnterWorktree(name: "<slug>")` passes the slug to the harness, which names the branch. The harness may or may not apply the `MSP-XXXX/` convention automatically. Verify what the harness produces and whether the skill needs to rename the branch post-creation.
3. **`.claude-plans/` in the worktree.** The harness clears the plans directory context on `EnterWorktree`. If the user creates a new `.claude-plans/` entry while inside the worktree, it ends up unreachable after `ExitWorktree`. Should isolated-work warn about this? Current recommendation: document as a constraint, don't add complexity.
4. **Baseline test run.** The prior art (`using-git-worktrees`) always runs baseline tests after setup. Should isolated-work do the same, or delegate to execute-plan's first task? Leaning: let execute-plan own this — it has per-task context about what "passing" means.
5. **`ExitWorktree` on Path A failure mid-execution.** If execute-plan fails partway and the user abandons, `ExitWorktree(action: "remove", discard_changes: true)` will discard uncommitted changes. The confirm step in the Abandon flow is the safeguard. Is one confirmation sufficient, or should the skill list the uncommitted files first?
