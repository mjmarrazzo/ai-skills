---
name: execute-plan
description: Use this skill whenever the user wants to execute, implement, or run through a `plan.md` produced by `blueprint` — phrases like "execute the plan", "implement plan.md", "run the implementation", "work through the plan", "go ahead and build it", or any blueprint Phase 7 handoff that picks execute-now or subagent-driven execution. Walks the plan task by task in either a subagent-per-task or inline-batch mode, handing off to `debug-loop` on failure, `ui-validation` on frontend touches, and `verify-before-done` at the end. Skip only if the user explicitly says "just do step N" / "skim and pick", asks to do it by hand, or the plan has one trivial task.
---

# Execute-plan

Turn an approved `plan.md` into committed code — task by task — without losing context, drifting from the spec, or thrashing on failures. The user picks one of two execution modes at start: **subagent-per-task** for high-stakes work, or **inline batch** for self-contained changes where velocity beats isolation.

**Announce at start:** "Using execute-plan to work through plan.md task by task."

Not in scope: writing the plan (that's `blueprint`), the final pre-commit gate (`verify-before-done`), or PR creation (`finish-branch`). This is the middle stretch — from "plan approved" to "ready for the wrap-up gate".

## When to trigger

```dot
digraph trigger {
    "Request received" [shape=box];
    "Plan handoff or 'execute'?" [shape=diamond];
    "Surgical ask?" [shape=diamond];
    "Run execute-plan" [shape=doublecircle];
    "Proceed directly" [shape=doublecircle];

    "Request received" -> "Plan handoff or 'execute'?";
    "Plan handoff or 'execute'?" -> "Proceed directly" [label="no"];
    "Plan handoff or 'execute'?" -> "Surgical ask?" [label="yes"];
    "Surgical ask?" -> "Proceed directly" [label="'just step N' / 'I'll do it myself'"];
    "Surgical ask?" -> "Run execute-plan" [label="no — full execution"];
}
```

Pushy on plan handoff, quiet on surgical asks. The default bias is end-to-end execution — if the user wanted to babysit each step they'd have asked for that.

## Pre-flight

Every invocation runs these in order before touching code. The first failure stops the skill and surfaces to the user.

### 1. Worktree-already-inside check (run FIRST)

If `execute-plan` was invoked by `isolated-work`, we're already inside a worktree and must not suggest setting up another one. Detect via either probe:

```bash
test -f .git && grep -q "gitdir:.*\.git/worktrees/" .git
# or
[ "$(git rev-parse --git-common-dir)" != "$(git rev-parse --git-dir)" ]
```

If either is true, set `inside_worktree=true` and skip the isolated-work suggestion (see § Isolated-work suggestion) regardless of risky-plan signals later. Without this guard, the wrapped invocation would re-suggest isolated-work and loop.

### 2. Locate the plan

Resolution order — stop at the first match:

1. **Caller-supplied `PLAN_PATH=<absolute-path>`** in the invocation message. `isolated-work` and any other wrapping skill passes this in. Discovery skipped.
2. **Explicit user path** typed in chat.
3. **Active-workspace algorithm** (canonical, shared with siblings):
   - If `WORKSPACE_PATH=<absolute-path>` is in the invocation message, use `<that>/plan.md`.
   - Otherwise enumerate `.claude-plans/*/` in repo root (or cwd if not a git repo), filter to directories containing `plan.md` or `spec.md`.
   - One match → use it. Multiple → prefer the slug containing the current branch's ticket key (branch `MSP-7032/foo` → slug with `MSP-7032`). Still multiple → most recent `plan.md` mtime.
   - Zero matches → refuse with "no plan.md found; run blueprint first or pass `PLAN_PATH=`".

Print the resolved path before doing anything else so the user can catch a wrong pick.

### 3. Load companion artifacts

From the same workspace directory:

- `spec.md` — **required**. Refuse without it: a plan without a spec means we can't review for spec compliance.
- `handoff.md` — **required**. Discovery dossier.
- `decisions.md` — optional. Loaded only for the end-of-plan handoff message, not into per-task prompts.
- `progress.json` — optional. If present, this is a resumed run (see § Progress & resume).

### 4. Freshness check

A plan written against a codebase that has since moved is a liability. Source of truth for "when was the plan first executed" is `progress.json.plan_sha` (written on first run; blueprint does not stamp a Plan-SHA into `plan.md`). On a fresh run with no `progress.json`, treat HEAD as the plan SHA and write it on first save.

For each file under the plan's `## Files` section, check whether it moved since `plan_sha`:

```bash
git log <plan_sha>..HEAD --format=%H -- <path>
```

Note: this is `git log <plan_sha>..HEAD`, not `git log -1`. The latter returns the last-touch regardless of time and silently passes drifted plans.

Outcomes:

- **Clean** (HEAD == plan SHA, no files moved): proceed.
- **Minor drift** (HEAD moved but none of the plan's target files changed): one-line warning, proceed. (`Plan was written at abc1234, HEAD is now def5678. None of the plan's target files were modified — proceeding.`)
- **Material drift** (any plan-target file changed): stop. List the changed files. Ask the user to accept-and-continue, refresh the plan via blueprint, or cancel. Don't auto-proceed — the plan's code blocks may now apply at wrong line numbers.

### 5. Mode selection

Ask once via `AskUserQuestion`:

> How do you want to execute this plan?
>
> 1. **Subagent-per-task** — Fresh subagent drafts each task; sonnet reviewer checks the diff against the task definition. Slower, isolated, less context contamination. Best for plans with >5 tasks or sensitive code.
> 2. **Inline batch** — I execute each task in this session, pausing at task boundaries. Faster, more context overlap. Best for tight plans where you want to read my reasoning live.

Default highlight: subagent-per-task if `Files` count > 10 or any risky-plan signal fires (see § Isolated-work suggestion); inline batch otherwise.

### 6. Branch check

If on `main` / `master` / `develop`, refuse and ask the user to switch. If the plan's slug starts with `MSP-NNNN`, suggest `git checkout -b MSP-NNNN/<short>`.

### 7. MSP repo detection

Triangulated — any one is sufficient:

1. Remote URL contains `nicusa` or `tylertech` (case-insensitive).
2. Current branch matches `^MSP-\d+/`.
3. Git config `user.email` ends `@tylertech.com`.

When MSP-detected, the commit-prefix line gets injected into every drafter prompt (Mode 1) and every inline commit step (Mode 2): _All commit messages MUST start with `MSP-<ticket>: ` where `<ticket>` is extracted from the workspace slug._

## Mode 1: Subagent-per-task

### Per-task lifecycle

```dot
digraph task_lifecycle {
    "Drafter dispatched" -> "Drafter reports status";
    "Drafter reports status" -> "Reviewer dispatched" [label="DONE"];
    "Drafter reports status" -> "Augment context, re-dispatch" [label="NEEDS_CONTEXT"];
    "Drafter reports status" -> "Invoke debug-loop" [label="BLOCKED"];
    "Reviewer dispatched" -> "Decision";
    "Decision" -> "Mark task done in progress.json" [label="ACCEPT"];
    "Decision" -> "Re-dispatch drafter with notes" [label="CHANGES_REQUESTED (one round)"];
    "Decision" -> "Pause, surface to user" [label="ESCALATE"];
    "Re-dispatch drafter with notes" -> "Reviewer dispatched (final)";
}
```

One drafter, one reviewer, at most one re-review round per task. Caps are load-bearing — they prevent the "reviewer drift" antipattern where each round invents new concerns.

### Drafter

Fresh `general-purpose` agent per task. Never reads `plan.md` itself — the main session extracts the task text and injects it. Model `sonnet` by default, `opus` on re-dispatch after `BLOCKED`.

Drafter prompt structure: see `references/subagent-prompts.md`. The prompt carries the spec digest, the handoff digest, the verbatim task text, the task's file scope, a working agreement (DONE/NEEDS_CONTEXT/BLOCKED status protocol, no out-of-scope edits, no plan mutation), and the MSP commit-prefix line when applicable.

### Reviewer

Separate fresh agent per task. Receives the task text, `git show --stat <sha>`, `git diff <sha>~ <sha>`, and the drafter's verification output. Does **not** receive the spec or handoff digests — that would invite relitigating architecture instead of checking the diff against the task definition.

Outputs `ACCEPT`, `CHANGES_REQUESTED` (with line-cited concrete fixes), or `ESCALATE`. Full prompt: `references/subagent-prompts.md`.

**Reviewer model — default `sonnet`. Override to `opus` when the task touches any of:**

- A file whose name contains `auth`, `session`, `token`, `crypto`, or `secret` (case-insensitive).
- Migration files (`migrations/`, `*.sql`, `schema.prisma`, `alembic/versions/`).
- Root config: `package.json`, `tsconfig.json`, `Cargo.toml`, `pyproject.toml`, `go.mod` at repo root.
- A task tagged `review: opus` in the plan.

The override exists because the original "sonnet on cost grounds" rationale dismissed the same Claude-on-Claude bias risk this skill set was built to mitigate. High-stakes paths warrant the deeper reviewer.

### Accept / reject flow

| Reviewer output | Action | Cap |
|---|---|---|
| `ACCEPT` | Mark task `done` in `progress.json` with commit SHA, advance. | — |
| `CHANGES_REQUESTED` (first time) | Re-dispatch the drafter with the reviewer's notes appended verbatim. Re-run the reviewer **once**. | One re-review round, then escalate. |
| `CHANGES_REQUESTED` (second time) | Pause, surface state to user. | — |
| `ESCALATE` | Pause, surface reviewer reasoning, ask the user whether to fix the task (likely via blueprint) or override. | — |

### Failures during drafting

| Drafter status | Action | Cap |
|---|---|---|
| `NEEDS_CONTEXT` | Answer the specific question (do not dump the whole spec); re-dispatch with the augmented prompt. | One augment per task; second `NEEDS_CONTEXT` converts to `BLOCKED`. |
| `BLOCKED` | Invoke `debug-loop` with the failing output, task definition, diff if any, and `caller=execute-plan`. | 2 `debug-loop` invocations per task. |

After any cap is hit: hard pause, surface state, do not auto-retry. The user owns the next call.

## Mode 2: Inline batch

The main session walks the plan top to bottom. For each task:

1. Surface a one-liner: `Task N/M: <name> — <files>`. No "starting", no "now I will". Brevity respects scrollback.
2. Use `TodoWrite` to register the task's steps as in-session todos so the user can see progress.
3. Execute each step. Run the verification commands the task specifies. Capture output.
4. On step success: mark the todo done, advance.
5. On step failure: see § Failure handling.
6. At task end (all steps passed): commit per the task's commit step (with MSP prefix when MSP-detected), update `progress.json`, and either pause (per checkpoint policy) or continue.

### Checkpoint policy

Default `per-task`. Set via the mode-selection question or by the user saying so explicitly.

| Policy | Behavior |
|---|---|
| `per-task` (default) | Pause after each task. Show diff stat + verification result, wait for "go" or "stop". |
| `per-N` | Pause after every N tasks. N capped at 5 so the user doesn't lose the plot. |
| `on-failure-only` | Don't pause unless a step or verification fails. |

**Implicit pause** (overrides any policy): always pause on test failure, lint failure, or any non-zero exit from a verification command. The user can re-engage and let the skill hand to `debug-loop`.

Over-configurable is a smell. We stop here. The user can interrupt mid-execution and redirect.

## Context loading

Loading `spec.md`, `handoff.md`, and `decisions.md` into every subagent prompt costs tokens and pollutes the drafter's attention with material the plan already distilled. The plan is the contract.

**Build digests once at skill init, reuse across tasks:**

1. **Spec digest** (~500 tokens) — goal, contracts/interfaces, data model bullet list, error-handling policy, file map. Strip prose. Drafter gets this; reviewer does not.
2. **Handoff digest** (~300 tokens) — constraints + open-questions-resolved only. Drop the discovery narrative.
3. **Per-task file context** — read the files the task touches **at task start** (not at init — they may have changed). Include only the line ranges named in the task's `Files` section.

**`decisions.md` is not loaded into per-task prompts.** Its decisions were already baked into the spec, hence already in the spec digest. The decisions log surfaces in the end-of-plan handoff and in `finish-branch`'s PR body, not here.

**Cache invalidation by content hash (`sha256`), not mtime.** A re-save without content change should not bust the cache; mtime can also be spoofed. Recompute the spec/handoff digest only when the file's sha256 changes between task starts.

## Per-task verification and UI handoff

Every task's verification commands run after its implementation steps. The plan specifies them — the skill does not invent extras. That's `verify-before-done`'s job at the end.

**One exception: UI-touching tasks.** If the task's diff includes any of:

- `.tsx`, `.jsx`, `.vue`, `.svelte`, `.css`, `.scss`, `.html`
- Files matching a route file pattern (Next.js `app/**/page.*`, Remix `routes/**`)

…then after the task's own verifications pass, invoke `ui-validation` with:

```
caller=execute-plan
surfaces=<routes inferred from this task's diff>
viewports=['mobile', 'desktop']
headless=true
screenshots_dir=.claude-plans/<active>/screenshots/task-<N>/
```

Narrow scope: just the routes this task touched, not the full plan's surface list. The full sweep is `verify-before-done`'s job. The `caller=execute-plan` parameter prevents `ui-validation` from invoking `execute-plan` or `debug-loop` back in a way that re-enters this skill.

If `ui-validation` isn't installed (no `~/.claude/skills/ui-validation/SKILL.md` and no `~/.claude/plugins/cache/**/skills/ui-validation/SKILL.md`), print one line and continue: `If ui-validation were installed, I'd run a per-task browser smoke check on <routes>. Skipping.`

## Failure handling

Thrashing prevention is load-bearing. The cheap thing — re-running the same failing command — is the worst thing.

### Mode 2 (inline) failures

1. **First failure of a step:** retry once **only if the failure is plausibly transient** (network flake, port already in use). Never retry compile errors or assertion failures — those don't fix themselves.
2. **Persistent failure:** invoke `debug-loop` with the failing command, step text, relevant file slices, and `caller=execute-plan`. Mode 2 has stronger context for debugging than Mode 1 because the session has been working in the same code.
3. **`debug-loop` returns "fixed":** re-run the verification. Pass → continue. Fail → second `debug-loop` invocation.
4. **Hard cap: 2 `debug-loop` invocations per task.** After that, stop and ask the user.

### Anti-thrash invariants (both modes)

- Never re-run the exact same command after a non-flake failure without changing something first.
- Never silently mark a failed verification done.
- Never edit `plan.md` to make a verification pass. The plan is read-only.

## Progress & resume

`TodoWrite` is the in-session UI; it's ephemeral and dies with the session. For durable resume, the skill writes `progress.json` under the active workspace:

```
.claude-plans/<active-dir>/progress.json
```

Schema:

```json
{
  "plan_sha": "abc1234",
  "started_at": "2026-05-14T15:32:00Z",
  "mode": "subagent-per-task",
  "checkpoint_policy": "per-task",
  "status": "in_progress",
  "tasks": [
    { "id": "task-1", "name": "Hook installation", "status": "done", "commit": "def5678", "completed_at": "..." },
    { "id": "task-2", "name": "Recovery modes",     "status": "in_progress" },
    { "id": "task-3", "name": "Progress reporting", "status": "pending" }
  ],
  "last_event": "task-2 dispatched to drafter at 2026-05-14T15:48:00Z"
}
```

**Atomic write.** Always write via tmpfile + rename:

```bash
tmp="$workspace/.progress.json.$$"
printf '%s\n' "$json" > "$tmp" && mv "$tmp" "$workspace/progress.json"
```

A concurrent-session crash mid-write must not produce a half-baked `progress.json`.

`plan_sha` is populated at first run from `git rev-parse HEAD`. Blueprint does **not** stamp a Plan-SHA into `plan.md`.

This does not violate the "no plan.md mutation" constraint. `plan.md` is read-only; `progress.json` is a separate gitignored file.

### Resume

On skill start, if `progress.json` exists:

1. Read it. Cross-check `plan_sha` against current HEAD's distance from it. If the plan was regenerated (the plan's file map no longer matches), archive `progress.json` as `progress.v1.json` and start fresh.
2. Verify each `done` task's commit is still in git history. If a commit was rebased away, mark that task `unknown` and ask the user.
3. Tell the user: `Resuming plan at task N/M. Tasks 1..N-1 marked done. Continue or restart?`

Default to resume. Git history is the ground truth — `progress.json` is the breadcrumb, not the contract.

### Ad-hoc fallback

`execute-plan` almost always runs inside a blueprint workspace, but if for some reason it needs to write artifacts without one (e.g. caller passed only `PLAN_PATH=` to a plan outside `.claude-plans/`), the fallback root is:

```
./.claude-results/<YYYY-MM-DD-HHMMSS>/execute-plan/
```

Same shape as the other skills in the composition set. Add `.claude-results/` to `.gitignore` if not already present.

## Isolated-work suggestion

Once per invocation, before mode selection, on risky plans only — **and only if the pre-flight `inside_worktree` check returned false**. If we're already in a worktree, skip this section entirely.

Risky signals (any one triggers the suggestion):

- **File count**: plan's `Files` section lists > 15 distinct files.
- **Root config touched**: `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `tsconfig.json`, `next.config.*`, `vite.config.*`, `tailwind.config.*` at repo root.
- **Migration present**: any path matching `migrations/`, `*.sql`, `schema.prisma`, `alembic/versions/`.
- **Auth/security paths**: paths under `auth/`, `security/`, `middleware/`, anything matching `*permission*` or `*authz*`.
- **Architectural verbs in plan goal**: `rename`, `extract`, `consolidate`, `rewrite`, `migrate`, `deprecate` in the plan header's `**Goal:**` line.
- **Deletion-heavy**: more `Delete:` than `Create:` entries in the file map.

Prompt:

> This plan touches `<N>` files including `<signal>`. Consider running this in a git worktree so the branch can be thrown away cleanly if it goes sideways. The `isolated-work` skill can set one up. Want me to invoke it now? (yes / no / show-me-the-command)

User accepts → invoke `isolated-work` with `caller=execute-plan` and `PLAN_PATH=<resolved-path>`; it sets up the worktree and re-invokes `execute-plan` inside it. User declines → proceed.

If `isolated-work` isn't installed, print the heuristic match plus the manual command (`git worktree add ../<slug> -b <branch>`) and continue.

## End-of-plan handoff

When the last task is `done` in `progress.json`:

1. Update `progress.json` with `status: "complete"` and the final commit SHA.
2. Print a summary block:

   ```
   execute-plan — <slug> complete
   ─────────────────────────────────────
   Mode:     subagent-per-task
   Tasks:    8/8 done
   Commits:  <abc1234..def5678>
   UI smoke: 3 routes checked, all green
   Drift:    none

   Next: verify-before-done
   ```

3. **Pre-handoff state check.** Required state before invoking `verify-before-done`:
   - Working tree clean (no uncommitted changes).
   - All task commits land on the current branch.
   - Every task in `progress.json` is `done`.
   - `spec.md`, `handoff.md`, `decisions.md` still readable at the workspace paths.

   If any are not satisfied, do not invoke. Surface the gap and ask the user.

4. **Propose knowledge-capture entries for blocked or over-budget tasks.** For each task whose final status was `BLOCKED` during execution OR which exceeded its time budget, invoke `knowledge-capture` (if installed) with `caller=execute-plan`, `kind=gotcha`, and a `proposed` block derived from the task's blocker notes. `source.files` from `git diff --name-only` over the task's commit range; `source.commit` from the task's terminal SHA; `source.session_marker = "execute-plan-task-<N>"`. `knowledge-capture` batches in interactive mode (one prompt now) or queues to `open-questions.md` in auto mode. If the skill isn't installed, print "if `knowledge-capture` were installed I'd propose saving these gotchas for next time" and continue.

5. Invoke `verify-before-done` with `caller=execute-plan` and the active workspace path.

If `verify-before-done` isn't installed, print:

> Plan executed. The `verify-before-done` skill would run final checks (lint, typecheck, full test suite, UI surface sweep). Run them by hand before finishing.

## Anti-patterns

- **One session per workspace, period.** Two `execute-plan` sessions against the same `.claude-plans/<dir>` is undefined behavior — `progress.json` races are not handled and the skill does not lock. For parallel work, use `isolated-work` to set up a separate worktree with its own workspace.
- **Don't read `plan.md` inside drafter subagents.** The main session extracts and injects the task text. Plan files include neighboring tasks and review history — distracting noise for a single-task drafter.
- **Don't load spec/handoff/decisions into every drafter prompt.** Build the digests once at init, reuse them. Trust the task text to carry per-task intent.
- **Don't write progress checkboxes back into `plan.md`.** Plan is read-only after blueprint produces it. Use `progress.json` + `TodoWrite`.
- **Don't auto-promote past a reviewer-requested change.** "Mostly looks fine" is how regressions ship. One re-review round, then escalate.
- **Don't run the full `ui-validation` surface list per task.** Per-task UI is a smoke check on the routes the task touched; the full sweep belongs to `verify-before-done`.
- **Don't retry the same failing command in a loop.** Change something or hand to `debug-loop` — re-running a real failure with no change is wasted tokens.
- **Don't skip the freshness check because the plan "feels recent".** A plan written against an already-shifted codebase is worse than no plan; its code blocks look authoritative.
- **Don't pick subagent-per-task as the default just because it sounds rigorous.** It's slow and tokens-heavy. Default to inline batch unless the plan is large or risky.
- **Don't invent verification commands the plan didn't specify.** The plan author chose them deliberately; extras belong in `verify-before-done`.
- **Don't treat `BLOCKED` as a retry signal.** It means "this task as defined can't proceed." Fix the context, fix the plan, or escalate — don't loop.

## Composition

- **Callers:** `blueprint` Phase 7 (execute-now / subagent-driven); `isolated-work` after worktree setup (passes `PLAN_PATH=` verbatim); direct user invocation ("execute the plan", "implement plan.md", "run the plan").
- **Calls** — all pass `caller=execute-plan`:
  - `debug-loop` on failure. Cap: 2 per task.
  - `ui-validation` after any task touching frontend files (narrow per-task scope).
  - `knowledge-capture` at end-of-plan for any task that finished `BLOCKED` or over-budget.
  - `verify-before-done` once at end of plan.
  - `isolated-work` optionally, before execution, when risky signals fire and the worktree-guard returned false.
- **Sibling-installed check:** `~/.claude/skills/<name>/SKILL.md` OR `~/.claude/plugins/cache/**/skills/<name>/SKILL.md`. Missing → one-line graceful-degradation note, continue.
- **Reads:** `.claude-plans/<active>/{plan,spec,handoff,decisions}.md` (all read-only), `.claude-plans/<active>/progress.json` (resume; rewritten as execution advances), git history (`git log <plan_sha>..HEAD`, `git show`, etc.).
- **Writes:** `.claude-plans/<active>/progress.json` (atomic via tmpfile + rename); commits to the current branch (via subagents in Mode 1, directly in Mode 2). Screenshots under `.claude-plans/<active>/screenshots/task-<N>/` are written **only via `ui-validation`** — this skill never writes them directly.

## Open questions

Carried forward to dogfooding, not resolved here.

1. **Drafter model floor for sensitive paths.** Reviewer escalates to opus on auth/migration/root-config; should the **drafter** also escalate to opus for those, or trust the plan to have distilled the hard thinking such that the drafter task is mechanical? Currently leaning no — escalating only on `BLOCKED` re-dispatch.
2. **"Frontend file" heuristic.** The current list (`.tsx`, `.jsx`, `.vue`, `.svelte`, `.css`, `.scss`, `.html` + route patterns) covers SPA stacks but not SSR templates (Jinja, ERB, Blade). False-positive risk if widened; false-negative risk if not. Leaning: SPA + `.html` only.
3. **Headed vs headless Playwright default.** Per-task UI smoke defaults to headless. The user may want headed for visual debugging during a long execution; currently no surface for that.
4. **Reviewer ambiguity on task scope.** Reviewer is told not to ask for things outside scope — but plan tasks vary in tightness. If a task says "add the endpoint" without listing tests, reviewer stays silent. This trusts plan quality more than may be safe.
