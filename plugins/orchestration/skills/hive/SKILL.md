---
name: hive
description: Use this skill whenever the user requests substantive engineering work — a new feature, a refactor that touches multiple files, an integration, an architectural change, a migration, or anything multi-step or ambiguous. Also trigger on explicit orchestration phrases — "hive this", "take this issue to a PR", "run the whole pipeline", "drive this end to end", "ship it end to end", "auto ship this". Hive sizes the work, picks a depth tier (direct change / plan-only / full spec+plan), asks once how much oversight you want (every step / plan check / auto), then drives lean workers through blueprint → execute-plan → verify-before-done → finish-branch, stopping at a ready-for-review PR. It NEVER merges. Hand off instead of running: when the user is scoping work they will NOT implement themselves ("another team will pull this in", "write up a ticket for X"), route to `draft-ticket`. Do NOT trigger for single-phase asks the user has already named — "execute the plan" is `execute-plan`, "open the PR" is `finish-branch`, "this is broken" is `debug-loop`, "review this PR" is `code-review`, and an explicit "/blueprint" or "plan this with me interactively" is `blueprint`. Skip if the user explicitly opts out ("just do it", "quick fix", "no plan needed") or the task is a single trivial edit (one-line change, rename, typo).
---

# hive

The front door for engineering work. Hive sizes the request with a cheap read-only worker, picks a depth tier, asks **once** how much oversight you want, writes a durable autonomy grant, then relays lean workers through `blueprint` → `execute-plan` → `verify-before-done` → `finish-branch`. It never merges.

Not in scope: document content (that's `blueprint`), task execution (`execute-plan`), PR mechanics (`finish-branch`). Hive owns sizing, the oversight dial, the grant, the relay, the gates, upsize policy, halts, resume, and model selection.

**Announce at start:** "Using hive to size this, then drive it through the spine. I'll ask once how much oversight you want."

## The boundary rule

A subagent cannot prompt the user — but a **stopped** worker can be resumed by message with its context intact (`Agent` + `SendMessage`). So:

- A phase that only **occasionally** needs a human stays **sealed** and asks via the question protocol (§ Worker question protocol).
- A phase that needs **many rapid rounds** with the user runs **inline** in hive's session.
- In practice: spec drafting, plan drafting, the `direct`-tier implementer and reviewer, and `execute-plan` (with its per-task drafters) are sealed at **every** oversight level. **Only the discovery questionnaire runs inline.**

## The relay rule

Read back **only** the fixed-shape report and artifact paths from a worker — never its transcript. That is what keeps a six-phase run inside one context window.

## Autonomy is granted, never inferred

Hive writes `"mode": "auto"` into `.pipeline.json` **only when `oversight == "auto"`.** At `every step` and `plan check` the file says `"mode": "interactive"`. Every **sealed** worker carries `mode=auto` in its invocation prompt at every oversight level — that is grant source 2, and it means "do not stall", not "never ask". An **inline** phase reads the file and stays interactive. `oversight` never overrides `mode`. Full rules and the resolution order: `references/state-files.md`.

## Tiers

| Tier | Sequence | When |
|---|---|---|
| `direct` | one implementer + one reviewer + a run-log line. No workspace, no spec, no plan. | ≤2 files, unambiguous, nothing cross-cutting |
| `plan-only` | discovery → plan → execute | multi-file but well understood; no spec needed |
| `full` | discovery → spec → gate → plan → gate → execute | new infra/contracts, migrations, auth/billing, or ambiguous |

**`direct`:**

1. Implementer worker (`general-purpose`, `sonnet`; `opus` on sensitive paths): the request, the triage `files`, a repo conventions probe, execute-plan's comment-discipline rule by reference, the ticket-prefix line when a key is detected. Under `plan check` / `auto` it commits and returns a commit range as `PATH`; under `every step` it **stages and stops**, and hive commits after the review pause.
2. **Reviewer worker** (`general-purpose`, `sonnet`; `opus` on sensitive paths): task text, `git diff <pre>..HEAD`, and hive's re-run of any obvious repo verification. Returns `ACCEPT` / `CHANGES_REQUESTED` / `ESCALATE`; one re-dispatch round max.
3. `verify-before-done` if installed (it self-skips docs-only and empty diffs).
4. Append the `direct` line to `hive-log.md`.
5. Terminus per oversight.

The reviewer is **not** optional at this tier. `direct` has no spec gate, no plan gate, and no per-task review — the reviewer is the only check between a sonnet worker and a commit.

**`plan-only`:** `blueprint phase=discovery` → `blueprint phase=plan` (runs Phase 5b internally) → `execute-plan`. No spec, no spec gate; the plan is the contract.

**`full`:** `blueprint phase=discovery` → `blueprint phase=spec` → spec gate → `blueprint phase=plan` → plan gate → `execute-plan`.

All three converge on verify gate → terminus. Triage fields, the `fan_in` procedure, the tier-mapping heuristic and its thresholds, user overrides, and the unparseable-output rule: `references/triage-contract.md`. Size from the estimate, never by feel.

## Oversight → concrete behaviour

| | `every step` | `plan check` | `auto` |
|---|---|---|---|
| Grant `mode` in the file | `interactive` | `interactive` | `auto` |
| `mode=auto` in a sealed worker's prompt | yes | yes | yes |
| Tier/oversight ask | yes | yes | yes |
| Discovery | **split** — `phase=discovery, recon_only=true` in a sonnet worker; the structured and free-form questions inline; a second sonnet worker writes `handoff.md` | one sealed worker, `mode=auto`, assumptions logged to `open-questions.md` | same as `plan check` |
| Spec gate (`full`) | hive relays the TL;DR and waits | skipped; logged to `open-questions.md` | skipped; logged |
| Plan gate | hive relays and waits | **the one pause** — hive relays and waits | skipped; logged |
| Execute-plan | **sealed worker**, `per-task` checkpoints | sealed worker, `on-failure-only` | sealed worker, `on-failure-only` |
| `direct` tier | implementer **stages, does not commit**; hive shows the diff + reviewer verdict and pauses; commit on approval | implementer commits; hive commits through to verify | same as `plan check` |
| Verify | inline read of `verify.json` + re-run on staleness | same | same |
| Terminus | verify result + offer `finish-branch` (inline, interactive) | verify result + offer `finish-branch` (inline, interactive) | `finish-branch` sealed worker, `mode=auto` → ready-for-review PR |

Two consequences:

- **Only the discovery questionnaire is inline.** Discovery recon is the heaviest context burn in the run, so it stays in a worker; `handoff.md` is written by a worker, never inline by hive.
- **Every sealed worker carries `mode=auto`**, which means "don't stall", not "don't ask" — asking is the `NEEDS_CONTEXT` return. A `per-task` checkpoint at `every step` is surfaced by the same stop-and-resume mechanic as a question.

## Entry flow

1. **Announce** (one line, above).
2. **Resume check first.** Before creating anything: resolve the active workspace; if it holds `.pipeline.json` with `"orchestrator": "hive"`, go to § Resume.
3. **Triage.** Spawn the `Explore` worker, `model: sonnet`. Cheap, read-only, no user involvement.
4. **Tier decision.** Apply the heuristic on the orchestrator model, against the triage JSON.
5. **One `AskUserQuestion`, batching two questions:**
   - *"How much oversight do you want on this run?"* — `every step` / `plan check` / `auto`, each with its one-line meaning, the last-used choice for this repo highlighted from `.claude-plans/.hive-oversight` (missing/unreadable → highlight `every step`).
   - *"I sized this as `<tier>` — `<one-line why, from the triage facts>`. Keep it?"* — the three tiers, hive's pick highlighted.

   This is the **only unconditional interruption** in the whole run, at every oversight level including `auto`, where it is the moment the user consents to no further pauses. The two questions are independently pre-statable and independently skippable — drop whichever the invocation already answered, log its source, and skip the `AskUserQuestion` entirely only when both are answered.
   - Oversight pre-stated: "go full auto", "skip the gates", a literal `oversight=<level>`, or `mode=auto`.
   - Tier pre-stated: "just make the change" (`direct`), "plan this out first" (`plan-only`), "I want a spec" (`full`).
6. **Grant write** — `tier != direct` only (below).
7. **Branch.** Never work on `main`/`master`/`develop`. If HEAD is a base branch, create `<KEY>/<slug>` or `<slug>`. Re-verify after any phase that might have created one.
8. **Relay** the tier's phase sequence.

Write the resolved oversight to `.claude-plans/.hive-oversight` once the question resolves. It is a highlight, not a default — the question is asked every run regardless.

## State and grant

Schemas, atomic-write pattern, the workspace tree, and `hive-log.md`: `references/state-files.md`.

- The grant is **on disk before any phase worker spawns**. Prose is not a grant.
- `tier != direct`: ensure `.claude-plans/` is gitignored (idempotent), `mkdir -p` the workspace, write `.pipeline.json` and the initial `hive.json`. `direct` writes neither.
- `"mode": "auto"` is written **only** at `oversight == "auto"`.
- `stop_at: ready-for-review`, always. `granted_at` from `date -u +%Y-%m-%dT%H:%M:%SZ`, never fabricated.
- `issue_target` is asked here only when `oversight == "auto"`; otherwise `none`, and finish-branch asks if it needs to.
- `tier` is the only field hive rewrites (on upsize), atomically.

## Worker report and question protocol

The canonical enum, spelled identically here and in every sibling:

```text
STATUS: OK | CHECKPOINT | NEEDS_CONTEXT | NEEDS_UPSIZE | BLOCKED
```

The three non-terminal values: a **`CHECKPOINT`** is a policy boundary (resume with `go`/`stop`, uncounted against the cap); a **`NEEDS_CONTEXT`** is a missing fact (resume with an answer, counted); a **`NEEDS_UPSIZE`** is a wrong plan shape (no resume — apply § Upsize handling). Report shape, per-status required lines, and every dispatch prompt: `references/worker-prompts.md`.

A worker asks by ending its turn with `STATUS: NEEDS_CONTEXT` plus `QUESTION:` / `DEFAULT:` / `IMPACT:`. Resolution:

- `every step`, and `plan check` **before** the plan gate → one `AskUserQuestion`, then `SendMessage` the answer to the **same** worker.
- `auto`, and `plan check` after the plan gate → answer with the worker's own `DEFAULT` unless `IMPACT` names a halt condition, log the call to `open-questions.md`, and resume.

Two invariants at every level: the worker **never redoes completed work**, and hive **never re-dispatches a fresh worker** for a `NEEDS_CONTEXT`. Cap: **three round-trips per worker per phase**; a fourth is treated as `BLOCKED` and surfaces. `CHECKPOINT`s are exempt from the cap.

At a gate, relay `GOAL` / `DECISIONS` / `EYES-ON` **verbatim** plus `PATH`, then offer one `AskUserQuestion`: **approve** / **push back** (free-text, routed to the drafter as a revision → `spec.v<N+1>.md` / `plan.v<N+1>.md`) / **I'll read the file** (print the path and wait). Never paraphrase `EYES-ON`.

## Upsize handling

On `STATUS: NEEDS_UPSIZE — <reason>`: bump one step (`direct` → `plan-only` → `full`), rewrite `tier` + `upsized_at` in `.pipeline.json`, append to `hive.json.upsizes` and `hive-log.md`, and restart from the phase the new tier requires — **never from scratch**. `direct` → `plan-only` creates the workspace and the grant at that point.

| `oversight` | Response |
|---|---|
| `every step` | Stop. Show the worker's reason and the proposed tier. `AskUserQuestion`: upsize / stay at `<tier>` / jump to `full`. |
| `plan check` | Upsize silently **if it arrives at or before the plan gate**. After plan approval → **halt and ask**: the single approval covered a plan that no longer describes the work. |
| `auto` | Log and continue. Surface every upsize in the final report. |

**Cap: 2 upsizes per run.** A third signal — or any upsize signal at `full` — is a halt at every oversight level: the work is not being sized wrong, it is not understood.

## Halt conditions

- A task stays `BLOCKED` after `execute-plan` exhausts its `debug-loop` budget.
- `verify-before-done` fails and `debug-loop` didn't resolve it. Never open a PR on red verification.
- `finish-branch`'s CI watch can't go green within its round cap. Stop at the draft PR.
- A safety gate trips — dirty tree, PR-from-main. `auto` waives permission prompts, never protections.
- A **required** sibling isn't installed for the chosen tier.
- The upsize cap is exceeded, or `full` reports `NEEDS_UPSIZE`.
- The triage worker returns unparseable output twice.
- An upsize arrives after the plan gate under `plan check`.

At a halt, report: the phase, the workspace path, the **one human decision** that would unblock it, and `hive.json.resume_prompt`. Work on disk is durable — nothing is rolled back.

`stop_at: ready-for-review` is the terminus at **every** oversight level. Hive never merges, however clean the PR looks; no grant value in this version permits it.

## Workers and models

Dispatch prompts, per-worker model table, and the sealed-mode preamble: `references/worker-prompts.md`.

- Set `model` **explicitly on every single dispatch**. Omitting it inherits the parent model, and the parent may be Fable — an omission is a violation, not a neutral default.
- **Never Fable, for any worker, ever** — including when the user is running Fable as the orchestrator.
- `sonnet` by default, including for the triage `Explore` worker, the discovery/`handoff.md` writers, and the sealed `execute-plan` / `finish-branch` phase workers — they orchestrate their own sub-workers, so the phase shell needs no depth.
- `opus` for the spec drafter, the plan drafter, and any `direct`-tier worker whose target paths hit execute-plan's sensitive-path set (auth/session/token/crypto/secret, migrations, root config).

## Composition and degradation

| Sibling | Required for | Missing → |
|---|---|---|
| `blueprint` | `plan-only`, `full` | Halt those tiers with "hive needs `blueprint` (plugin `planning`)". `direct` still runs. |
| `execute-plan` | `plan-only`, `full` | Halt those tiers. `direct` still runs. |
| `verify-before-done` | nothing | Proceed; note "no independent verification gate" in the report |
| `finish-branch` | nothing | Stop after verify with the branch ready; say so |
| `debug-loop`, `ci-check-triage`, `pr-review-triage` | nothing | Reduced recovery coverage, noted once |
| `pre-task-research`, `knowledge-capture`, `tech-brief`, `visual-digest`, `isolated-work` | nothing | Used by the phases themselves when present; hive never calls them directly |

Detection is the canonical two-path probe (`~/.claude/skills/<name>/SKILL.md` or `~/.claude/plugins/cache/**/skills/<name>/SKILL.md`), best-effort: if the probe misses, attempt the invocation and treat a routing failure as not-installed.

Every dispatch carries `caller=hive`, plus as applicable `phase=<discovery|spec|plan|all>`, `recon_only=true`, `WORKSPACE_PATH=<abs>`, `PLAN_PATH=<abs>`, `mode=auto`, `oversight=<level>`. No phase skill calls back into hive, so there is no cycle.

## Resume

Detection at entry, in order: active workspace holds `.pipeline.json` with `"orchestrator": "hive"` → read `hive.json` for `phase` / `phase_status`, then **cross-check against artifacts on disk and trust the artifacts** (`spec.v*.md`, `plan.v*.md`, `progress.json` task states, `verify.json` with `commit_sha == HEAD`, `gh pr view`). Resume silently when the grant is still valid — same `task_ref`, same branch, `stop_at` unchanged — and note it in the final report; otherwise confirm the resume point. Never re-run a completed phase; **verify is the sole exception and is always re-run.** Details: `references/state-files.md`.

## Final report

One message, at every oversight level:

- **What shipped** — tier used, tasks done, tasks blocked with notes, commit range, PR URL + state when finish-branch ran.
- **Upsizes** — every one, with reason. This is how the user learns hive's sizing is drifting.
- **Deferred decisions** — `open_questions_count` plus the path to `open-questions.md`; under `plan check` and `auto`, tell the user to skim it before merging.
- **Next step** — "ready for your review and merge; I stopped at ready-for-review by design" (`auto`), or the `finish-branch` offer (`every step`, `plan check`).
- **Resume prompt** — printed once.

## Anti-patterns

- **Merging.** Ready-for-review is the terminus, however clean the PR looks.
- **Inferring the grant instead of writing it.** `.pipeline.json` on disk before any phase runs; prose is not a grant.
- **Reading a worker's transcript back into hive.** Fixed-shape report and artifact paths only.
- **Paraphrasing a worker's `EYES-ON` at a gate.** Relay it verbatim; the smoothing is where the doubt gets lost.
- **Sizing by feel instead of from the triage estimate.** The estimate is cheap and it is what the tier is auditable against.
- **Re-asking after the entry question.** Log judgment calls to `open-questions.md`; per-gate prompts at `plan check` or `auto` are a broken promise.
- **Sealing a phase that needs many rapid rounds.** Only the discovery questionnaire runs inline; everything else asks via `NEEDS_CONTEXT`.
- **Re-dispatching a fresh worker to answer a `NEEDS_CONTEXT`.** `SendMessage` the same worker; a re-dispatch throws the phase away.
- **Omitting `model` on a dispatch.** Inheritance can mean Fable.
- **Barreling through a halt.** A blocked task, red verify, or a post-approval upsize is a stop to surface.
- **Skipping the direct-tier reviewer or the run-log line.** They are the only trail `direct` leaves.
- **Re-running a completed phase on resume.** Verify is the sole exception.
- **Committing the workspace.** `.claude-plans/` is never project documentation.
