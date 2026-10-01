# State files and the grant rule

Every file hive reads or writes, and the one autonomy rule that makes the whole design work.

## `.pipeline.json` — the grant

Per workspace, at `.claude-plans/<active>/.pipeline.json`.

```json
{
  "orchestrator": "hive",
  "oversight": "every step | plan check | auto",
  "tier": "direct | plan-only | full",
  "mode": "interactive | auto",
  "stop_at": "ready-for-review",
  "issue_target": "github | jira | none",
  "task_ref": "<issue number/URL or short task description>",
  "granted_at": "<date -u +%Y-%m-%dT%H:%M:%SZ — never fabricated>",
  "upsized_at": "<same format; present only after an upsize rewrote tier>"
}
```

New fields: `oversight`, `tier`, `upsized_at`. `tier` is the only field hive rewrites, and it does so atomically (tmpfile + `mv`, the pattern at `execute-plan/SKILL.md:280-287`). `granted_at` comes from `date -u +%Y-%m-%dT%H:%M:%SZ` and is never fabricated.

### The one autonomy rule

> Hive writes `"mode": "auto"` into `.pipeline.json` **only when `oversight == "auto"`.** At `every step` and at `plan check` the file says `"mode": "interactive"`.
>
> A **sealed worker** gets its autonomy from grant source 2 — hive puts `mode=auto` in that worker's invocation prompt, because a worker cannot ask a question and a worker that goes interactive just stalls.
>
> An **inline phase** gets its autonomy from grant source 3 — it reads the file, and outside `oversight=auto` the file says interactive, so it stays interactive.
>
> `oversight` never overrides `mode`. Readers resolve interactive-vs-auto by blueprint's existing three sources, unchanged, and read `oversight` only to refine *how* they behave once that is settled.

Resolution order for every reader (`blueprint`, `execute-plan`, `finish-branch`), unchanged from today:

1. The user said so this turn.
2. The invocation prompt carries `mode=auto`.
3. `.pipeline.json` carries `"mode": "auto"`.

None of the three → interactive. This is verbatim in meaning from `blueprint/SKILL.md:24-41`. `oversight` and `tier` are additive, advisory, and never required — a reader who has never heard of them behaves correctly on a hive grant.

### Direct tier writes no grant and no workspace

There is no spec, plan, or progress state to protect, and the run is one worker plus one reviewer. Both its workers are sealed, so they carry `mode=auto` at every oversight level (grant source 2); the `every step` pause lives in hive, between the reviewer's verdict and the commit, never inside a worker. A direct run that upsizes creates the workspace and the grant at that moment.

## `hive.json` — the run cursor

New, per workspace: `.claude-plans/<active>/hive.json`. Written atomically after every phase transition.

```json
{
  "orchestrator": "hive",
  "run_id": "2026-09-09T22:39:05Z",
  "tier": "full",
  "oversight": "plan check",
  "phase": "triage | discovery | spec | plan | execute | verify | ship | done",
  "phase_status": "in_progress | complete | halted",
  "triage": { "...": "the estimate below, verbatim" },
  "upsizes": [
    { "at": "<ts>", "from": "plan-only", "to": "full", "phase": "plan", "reason": "<worker's one-line reason>" }
  ],
  "workers": [
    { "phase": "spec", "model": "opus", "artifact": "/abs/spec.v1.md", "at": "<ts>" }
  ],
  "halt": { "at": "<ts>", "condition": "<name>", "detail": "<one line>" },
  "resume_prompt": "<verbatim paste-able text for a fresh session>",
  "last_event": "<one line>"
}
```

**Two-files rationale.** The grant is durable evidence and is read-cached. The cursor is rewritten constantly — it mirrors `progress.json` being "the breadcrumb, not the contract."

## `.claude-plans/.hive-oversight`

Per repo, one line: `<oversight>\t<ISO ts>`. Written after the entry question resolves; read only to pick the highlighted option. Missing, unreadable, or unrecognised → default `every step`. It is a **highlight, not a default**: the question is asked every run.

## `.claude-plans/hive-log.md`

At the `.claude-plans/` root, not inside a workspace — direct-tier runs create no workspace. Append-only, created with a `# hive run log` header on first use.

```text
- 2026-09-09T22:41:03Z · direct · branch=MSP-1234/add-retry · a1b2c3d · files=2 · reviewer=ACCEPT · verify=pass · "add retry to the webhook client"
- 2026-09-09T22:45:11Z · upsize · plan-only→full · phase=plan · reason="task needs a new SQS queue"
```

Fields are ` · `-separated `key=value` pairs after the timestamp and event kind, ending with the quoted task one-liner. `upsize` events are written from **every** tier, which makes this the record of hive's sizing accuracy. Nothing else writes here.

## The workspace tree

```text
.claude-plans/
├── .hive-oversight                   # NEW — per-repo last oversight choice, one line
├── hive-log.md                       # NEW — append-only; direct-tier runs + all upsizes
└── <YYYY-MM-DD>-<slug>/              # plan-only and full tiers only
    ├── .pipeline.json                # EXTENDED — grant + tier (tier rewritable)
    ├── hive.json                     # NEW — run cursor, upsizes, resume prompt
    ├── handoff.md                    # blueprint, unchanged
    ├── spec.v<N>.md                  # blueprint, unchanged; absent at plan-only tier
    ├── plan.v<N>.md                  # blueprint, unchanged
    ├── decisions.md                  # blueprint, unchanged
    ├── open-questions.md             # blueprint, unchanged; hive appends upsizes + skipped gates
    ├── progress.json                 # execute-plan; gains `upsize_requested` task status
    └── verify.json                   # verify-before-done, unchanged
```

Invariants:

- `.pipeline.json` exists before any phase worker is spawned.
- `hive.json.phase` is monotonic except on upsize, which may move it backward to the phase the new tier restarts from.
- A workspace has at most one live hive run.
- Slug derivation: ticket key if the work item carries one (`^[A-Z][A-Z0-9]+-\d+`), else a 3–5 word kebab summary, always date-prefixed.

## Resume and crash recovery

Detection at entry, in order:

1. Active workspace holds `.pipeline.json` with `"orchestrator": "hive"` → resume candidate.
2. Read `hive.json` for `phase` / `phase_status`. **Cross-check against artifacts on disk, and trust the artifacts** — `hive.json` is a breadcrumb: `spec.v*.md` / `plan.v*.md` present → those phases landed; `progress.json` task states → how far execution got; `verify.json` with `commit_sha == HEAD` and `pass` → verify landed; `gh pr view --json url,isDraft,statusCheckRollup` → whether ship started or finished.
3. Resume silently when the grant is still valid — same `task_ref`, same branch, `stop_at` unchanged — and note the resume in the final report. Otherwise confirm: *"found a partial hive run at `<workspace>`, tier `<t>`, last completed phase `<p>`; resume from `<next>`?"*

Never re-run a completed phase: no re-planning over an existing plan, no re-executing `done` tasks, no second PR. **Verify is the sole exception — always re-run it on resume**, cheap and staleness-prone.

`hive.json.resume_prompt` is regenerated on every phase transition and holds a paste-able instruction for a fresh session: the workspace absolute path, the tier, the oversight level, the phase to resume from, and the artifacts already on disk. It is printed once at the end of a run and once at any halt — **never as a mid-run gate**.

## Source of truth

The three-source grant rule above is quoted from `blueprint/SKILL.md:24-41` and `execute-plan/SKILL.md:18-34`, reproduced, not improved. Hive adds no fourth way to become autonomous — see spec § Security.
