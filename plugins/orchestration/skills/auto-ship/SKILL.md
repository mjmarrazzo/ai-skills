---
name: auto-ship
description: Use this skill ONLY when the user explicitly wants the full engineering pipeline run end-to-end and autonomously — phrases like "auto-ship this", "auto-ship issue #123", "take this issue to a PR", "run the whole pipeline autonomously", "drive this to a ready PR without me", "ship it end to end". auto-ship is the orchestrator: it grants autonomy to the spine, then relays sealed subagents through blueprint → execute-plan → verify-before-done → finish-branch, stopping at a ready-for-review draft PR. It NEVER merges. Do NOT trigger for ordinary single-phase work — a plain feature request belongs to `blueprint`, a plan execution to `execute-plan`, a PR to `finish-branch`. Trigger only when the user is asking for the *autonomous chaining of all of them*. Skip if the user wants to stay in the loop ("let's plan this together", "I'll review each step").
---

# auto-ship

Take a work item from nothing to a ready-for-review pull request, autonomously, and stop there. auto-ship is the **architect**: it doesn't do the planning, coding, or PR work itself — it grants autonomy, then relays a chain of sealed subagents through the spine, carrying only artifact *paths* and short status between them so its own context stays lean from end to end.

**Announce at start:** "Using auto-ship to run the full pipeline autonomously — I'll confirm a few setup choices, then drive blueprint → execute → verify → PR to a ready-for-review draft. I won't merge; that stays your call."

## What this is, and why it's built this way

The friction this skill removes: a long, multi-phase run where the human re-greenlights every gate. auto-ship is the deliberate, *pointed-to* grant of autonomy — the one place where "yes, run without asking" is made explicit and durable, rather than something a downstream skill guesses from memory.

Two design commitments make it composable:

1. **Autonomy is a written grant, not a vibe.** auto-ship writes `.pipeline.json` into the workspace. Every spine skill (`blueprint`, `execute-plan`, `finish-branch`) reads that file under its own "Autonomy is granted, never inferred" rule and goes auto *because the grant is on disk* — not because it recalls that the user "likes auto". A bare `/blueprint` with no grant stays interactive. This is what lets the same skills be safe solo and autonomous in a pipeline.

2. **The architect relays sealed subagents.** Each phase runs in its own subagent that does the heavy lifting (repo reads, reviewer fan-out, per-task drafting). The architect reads back only a small structured status + the artifact paths, then hands those paths to the next phase's subagent. The architect never inherits a phase's full transcript. This is how a six-phase run fits in one context window.

## Stop point: ready-for-review, never merge

auto-ship drives to a **draft PR promoted to ready-for-review, with CI green and bot review comments triaged**. It pings human reviewers and stops. Merging is always the human's decision. The grant records `"stop_at": "ready-for-review"`; `finish-branch` reads it and treats its own promote-to-ready terminus as the stop.

(If a future version is allowed to merge, that's a new explicit grant value — not a default. Don't merge on this version regardless of how clean the PR looks.)

## Phase 0 — Setup (the one interactive moment)

auto-ship is autonomous, but three things are expensive to get wrong and genuinely project-dependent, so confirm them once up front. Batch into a single `AskUserQuestion` where possible:

1. **The work item.** An issue number/URL, or a free-form task description. If the user already named it in the invocation, skip asking.
2. **Where issues/tickets get filed.** Projects differ — some track work as GitHub issues on the repo, some in a JIRA/service tracker, some not at all. Ask: "Where should any follow-up issues or the PR's tracker link point — GitHub issues on this repo / a JIRA project / nowhere (off the books)?" Record the answer in the grant as `issue_target`.
3. **Confirm the autonomy + stop point.** One line: "I'll run to a ready-for-review PR without pausing at the normal gates, logging any judgment calls to `open-questions.md`. I will not merge. Good to go?"

After Phase 0, do not ask again unless a **halt condition** (below) trips. This is the contract: the user spent their attention here so they don't have to spend it per-gate.

## Phase 1 — Grant + workspace

1. Resolve the repo root: `git rev-parse --show-toplevel 2>/dev/null || pwd`. Ensure `.claude-plans/` is gitignored (idempotent append).
2. Derive the slug: a ticket key if the work item carries one (`^[A-Z][A-Z0-9]+-\d+`), else a 3–5 word kebab summary. Prefix with today's date.
3. Create the workspace: `mkdir -p .claude-plans/<YYYY-MM-DD>-<slug>/`.
4. Write the grant to `.claude-plans/<active>/.pipeline.json`:

```json
{
  "orchestrator": "auto-ship",
  "mode": "auto",
  "stop_at": "ready-for-review",
  "issue_target": "github | jira | none",
  "task_ref": "<issue number/URL or short task description>",
  "granted_at": "<output of `date -u +%Y-%m-%dT%H:%M:%SZ` via Bash — never fabricate a timestamp>"
}
```

The grant is the load-bearing artifact. Everything downstream keys off it. Write it before spawning any phase subagent.

## Resuming an interrupted run (idempotent re-invocation)

Before creating anything in Phase 1, check whether this pipeline already ran partway. Detection, in order:

1. Resolve the active workspace; if it contains `.pipeline.json` with `"orchestrator": "auto-ship"`, this is a resume candidate.
2. Inventory the artifacts to find the last completed phase: `spec.v*.md`/`plan.v*.md` present → P1 done; `progress.json` task states → how far P2 got; `verify.json` with `commit_sha == HEAD` and `pass` → P3 done; `gh pr view --json url,isDraft,statusCheckRollup` on the current branch → whether P4 started (draft) or finished (ready).
3. Confirm with the user before resuming — "found a partial auto-ship run at `<workspace>`, last completed phase `<N>`; resume from `<N+1>`?" — unless the existing grant is still valid (same `task_ref`, same branch, `stop_at` unchanged), in which case resume silently and note the resume in the final report.

Then continue from the first incomplete phase. Never re-run a completed phase from scratch: don't re-plan over an existing plan, don't re-execute `done` tasks (execute-plan's `progress.json` already makes tasks skippable), don't open a second PR when `gh pr view` finds one. Re-verify (P3) is the exception — it's cheap and staleness-prone, so always re-check it on resume.

## Phase 2 — Relay through the spine

Each phase is a subagent spawned with the `Agent` tool. Give every subagent: the workspace path, `caller=auto-ship` (so nothing re-enters this skill), and an instruction to invoke its skill in auto mode. Require each to return ONLY a compact structured status — not its working transcript.

### P1 · Plan (blueprint)

Spawn a subagent:

> You are the planning stage of an auto-ship pipeline. Use the exact workspace `<abs>/.claude-plans/<active>/` — it already exists and contains a `.pipeline.json` grant with `mode=auto`; do NOT create a new workspace. Invoke the `blueprint` skill with `caller=auto-ship`, `mode=auto`, `WORKSPACE_PATH=<abs>/.claude-plans/<active>/`, against this work item: `<task_ref + any detail>`. Blueprint will run its questionnaire reasoning itself and log every assumption it would have asked about to `open-questions.md`. When done return ONLY: `plan_path`, `spec_version`, `open_questions_count`, and a one-line `summary`.

Architect reads back those fields. Does not read spec/plan contents.

### P2 · Branch

Ensure a feature branch exists; never work on `main`/`master`/`develop`. If the current branch is a base branch, create one: `<KEY>/<slug>` when a ticket key is present, else `<slug>`. (If `execute-plan` would create the branch itself given the plan slug, let it — but verify afterward that HEAD is not a base branch.)

### P2 · Execute (execute-plan)

Spawn a subagent:

> You are the execution stage of an auto-ship pipeline. Workspace: `<abs>/.claude-plans/<active>/` with a `mode=auto` grant in `.pipeline.json`. Invoke `execute-plan` with `caller=auto-ship`, `mode=auto`, `PLAN_PATH=<plan_path>`. It will run subagent-per-task with on-failure-only checkpoints, hand failures to `debug-loop`, and call `verify-before-done` at the end. If a ticket key was detected (Phase 1 step 2), prefix every commit message with it (`KEY-123: <message>`) per execute-plan's own ticket-convention detection. When done return ONLY: `tasks_total`, `tasks_done`, `tasks_blocked`, `verify_result` (pass/fail/absent), and a one-line `summary` plus any blocked-task notes.

### P3 · Verify (gate)

Read `.claude-plans/<active>/verify.json` directly (architect-side, cheap). Gate: file present, `commit_sha == HEAD`, `result == "pass"`. If execute-plan already ran it and it passed AND `commit_sha == HEAD`, proceed. **Staleness is the common case here**: the Branch step or a late execute-plan commit can advance HEAD *after* execute-plan's internal verify wrote `verify.json`, so re-check `commit_sha` against `git rev-parse HEAD` and, if it moved (or the file is absent), spawn a `verify-before-done` subagent (`caller=auto-ship`) and re-read. Re-verifying here means a failure halts at *this* gate rather than surfacing later as finish-branch's stale-verify safety block. A `fail` that execute-plan + debug-loop couldn't resolve is a **halt condition**.

### P4 · Ship (finish-branch)

Spawn a subagent:

> You are the shipping stage of an auto-ship pipeline. Workspace: `<abs>/.claude-plans/<active>/` with a `mode=auto`, `stop_at=ready-for-review` grant. Invoke `finish-branch` with `caller=auto-ship`, `mode=auto`, `WORKSPACE_PATH=<abs>/.claude-plans/<active>/`. It will open a draft PR, watch CI (routing red checks to `ci-check-triage`), triage bot review comments (`pr-review-triage`), and promote to ready-for-review, pinging human reviewers. Do NOT merge. When done return ONLY: `pr_url`, `pr_state` (draft/ready), `checks` (green/red/pending), `unresolved_comments`, and a one-line `summary`.

## Phase 3 — Report

Surface to the human, in one message:

- **PR**: URL + state (should be ready-for-review).
- **Shipped vs deferred**: tasks done; tasks blocked (with notes); the `open_questions_count` and a pointer to `.claude-plans/<active>/open-questions.md` — this is the decision log of everything auto mode rolled with instead of asking. Tell the user to skim it before merging.
- **Next step**: "Ready for your review and merge — I stopped at ready-for-review by design."

## Halt conditions — when auto stops and surfaces

Auto means "don't stop to ask permission for decisions you can make." It does NOT mean "never stop." Halt the pipeline, surface state clearly, and wait for the human when:

- **A task stays `BLOCKED`** after `execute-plan` exhausted its `debug-loop` budget. Don't thrash; surface the blocker.
- **`verify-before-done` fails** and the failure isn't resolved by debug-loop. Never open a PR on red verification.
- **`finish-branch`'s CI watch can't go green** within its round cap. Stop at the draft PR; report which checks are stuck.
- **A safety gate trips** — dirty tree, PR-from-main block. These block in auto too; auto never waives them.
- **A required spine skill isn't installed** (see Composition). Report what to install.

At a halt: report exactly where the pipeline stopped, the workspace path, and what a human decision would unblock. The work done so far is durable on disk — the user (or a re-invocation) can resume.

## Composition & degradation

Required: `blueprint`, `execute-plan`, `finish-branch`. Strongly recommended: `verify-before-done` (the P3 gate), `debug-loop` (failure recovery), `ci-check-triage` + `pr-review-triage` (the finish-branch watch). Optional: `pre-task-research`, `knowledge-capture`, `isolated-work` — used by the phases themselves when present.

Probe each via file existence (`~/.claude/skills/<name>/SKILL.md` or `~/.claude/plugins/cache/**/skills/<name>/SKILL.md`). The probe is best-effort — install layouts vary — so if it misses, attempt the skill invocation anyway and treat a routing failure ("skill not found") as not-installed; don't declare a sibling missing on the glob alone. If a **required** skill is missing, halt at Phase 1 with: "auto-ship needs `<name>` installed (plugin `<group>`) to run the pipeline." If a **recommended** skill is missing, proceed but note the reduced coverage in the final report (e.g. "no verify-before-done — opened the PR without an independent verification gate").

Every spawned subagent carries `caller=auto-ship`; no phase skill calls back into auto-ship, so there's no cycle.

## Anti-patterns

- **Merging** — never, on this version; ready-for-review is the terminus.
- **Inferring the grant instead of writing it** — `.pipeline.json` on disk before any phase runs is the durable signal, not "you're in auto" in prose.
- **Reading subagent transcripts back into the architect** — take the structured status and artifact paths only; anything more defeats the lean-context relay.
- **Skipping Phase 0 to look fast** — the setup questions are the user's one chance to steer, and the issue target is unguessable.
- **Barreling through a halt condition** — a blocked task or red verification is a stop to surface, not paper over.
- **Re-asking per gate after Phase 0** — log judgment calls to `open-questions.md` and keep moving; per-gate prompts defeat the autonomy grant.

## Inputs accepted

- Work item: issue number/URL or free-form task (Phase 0, or parsed from the invocation).
- `issue_target` override ("file issues on GitHub", "use JIRA").
- Standard pass-throughs the phases understand: `WORKSPACE_PATH`, `PLAN_PATH`.

## Outputs

- A workspace under `.claude-plans/<YYYY-MM-DD>-<slug>/` with handoff, spec, plan, decisions, open-questions, verify.json, progress.json, and `.pipeline.json`.
- A feature branch with the implemented work, verified green.
- A ready-for-review draft PR with a generated body, CI green, bot comments triaged, human reviewers pinged.
- A final report: PR URL, shipped-vs-deferred, decision log pointer.
