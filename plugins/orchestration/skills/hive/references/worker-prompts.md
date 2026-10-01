# Worker dispatch prompts

Every worker dispatch hive makes, so `SKILL.md` never inlines a prompt. Register modelled on `execute-plan/references/subagent-prompts.md`: short preamble per worker, then a fenced prompt block. Every worker is dispatched via the `Agent` tool with `model` set explicitly — never omitted, never Fable.

## The fixed-shape report

Every drafting worker (discovery, spec, plan, direct-tier implementer/reviewer, sealed phase workers) returns ONLY this:

```text
GOAL: <one line — what this artifact/change accomplishes>
DECISIONS: <3-5 bullets — choices made unaided, each one line>
EYES-ON: <bullets — what the worker wants the human to check; "nothing" if genuinely none>
PATH: <absolute path to the artifact, or the commit range for the direct tier>
STATUS: OK | CHECKPOINT | NEEDS_CONTEXT | NEEDS_UPSIZE | BLOCKED
LINES: <line count of the artifact; omit for the direct tier>
```

`GOAL`, `DECISIONS`, `EYES-ON`, `PATH` are required. `STATUS` defaults to `OK` when absent. Hard budget: **20 lines total**, one line per bullet, no nested bullets, no prose paragraphs. A worker that needs more than 20 lines has failed to decide something — that belongs in `EYES-ON` as a question, not a longer report.

Hive relays `GOAL` / `DECISIONS` / `EYES-ON` **verbatim** at the gate, plus `PATH`. Never paraphrase `EYES-ON` — paraphrase is where the one thing the worker was unsure about gets smoothed away.

### `STATUS` — the one canonical enum

Spelled identically here, in `hive/SKILL.md`, in blueprint's `SKILL.md`, and in execute-plan's `SKILL.md` and `references/subagent-prompts.md`:

```text
STATUS: OK | CHECKPOINT | NEEDS_CONTEXT | NEEDS_UPSIZE | BLOCKED
```

| value | means | extra required lines |
|---|---|---|
| `OK` | phase complete, artifact on disk. Default when `STATUS` is absent. | — |
| `CHECKPOINT` | a task boundary was reached and checkpoint policy says stop. Not a question, not a failure. | `TASK: <id/name>` · `DIFFSTAT: <git diff --stat one-liner>` · `VERIFY: <pass/fail + command>` |
| `NEEDS_CONTEXT` | a fact is missing; the worker stopped rather than guess. | `QUESTION:` · `DEFAULT:` · `IMPACT:` |
| `NEEDS_UPSIZE` | the plan is wrong about the shape of the work. | one-line reason on the `STATUS` line |
| `BLOCKED` | something is failing, or a cap was exhausted. | the failing output, cited not pasted whole |

`CHECKPOINT` and `NEEDS_CONTEXT` are both resolved by resuming the **same** worker (below). `NEEDS_UPSIZE` and `BLOCKED` end the worker's turn for good.

## The worker question protocol

A sealed worker cannot prompt the user, but it can end its turn and be resumed by message with its context intact. Any worker may end its turn with:

```text
STATUS: NEEDS_CONTEXT
QUESTION: <one question>
DEFAULT: <what the worker will do if told to proceed>
IMPACT: <what changes if the answer differs>
```

Resolution, by oversight level:
- `every step` / `plan check` (pre-plan-gate) → hive raises one `AskUserQuestion`, then `SendMessage`s the answer to the same worker.
- `auto` → hive answers with the worker's own `DEFAULT` unless `IMPACT` names a halt condition, logs the call to `open-questions.md`, and resumes the worker.

Both invariants hold at every oversight level: **the worker never redoes completed work**, and **hive never re-dispatches a fresh worker for a `NEEDS_CONTEXT`.** Cap: **three round-trips per worker per phase**; a fourth is treated as `BLOCKED` and surfaces. All four lines sit inside the 20-line report budget.

`STATUS: CHECKPOINT` uses the identical resume mechanic — hive shows `TASK` / `DIFFSTAT` / `VERIFY`, gets `go` or `stop`, and `SendMessage`s it back — but is **not counted against the three-round-trip cap**: a checkpoint is a policy boundary, not a missing fact. A ten-task plan at `oversight=every step` would otherwise exhaust the cap at task four.

## Sealed mode, always

Every sealed worker's prompt carries `mode=auto` and `caller=hive`, at every oversight level. `mode=auto` means "do not stall waiting for a prompt" — not "never ask": asking is the `NEEDS_CONTEXT` return above. See `references/state-files.md` for why the grant file can simultaneously say `"mode": "interactive"`.

## Dispatch prompts

Every drafting prompt below tells the worker it may end its turn with a `NEEDS_CONTEXT` block rather than guessing, and that it will be resumed by message, not re-dispatched fresh.

### Triage

`Explore`, `model: sonnet`, read-only. Schema deferred to `references/triage-contract.md` — not restated here.

```text
You are the triage worker for a hive run. Read-only; do not edit anything.

Repo root: <abs>
User request: <verbatim>

Gather facts only — do not choose a tier; that judgment stays with the orchestrator. Return ONLY the JSON contract in references/triage-contract.md. If any field is genuinely unknowable from the repo, use its documented default rather than guessing.
```

### Discovery recon

`general-purpose`, `model: sonnet`. Used under `oversight=every step`, where the questionnaire must run inline but recon must not.

```text
You are the discovery-recon stage of a hive run. caller=hive, mode=auto, phase=discovery, recon_only=true, WORKSPACE_PATH=<abs>.

Invoke the `blueprint` skill with these parameters. It will run Phase 1 steps 1-6 (recon, knowledge-capture, tech-brief, pre-task-research, visual-digest) and skip the questionnaire and handoff.md. Return ONLY the recon digest and artifact paths blueprint gives you — nothing else. You may end your turn with STATUS: NEEDS_CONTEXT (QUESTION/DEFAULT/IMPACT) instead of guessing; you will be resumed by message.
```

### `handoff.md` writer

`model: sonnet`. Runs inline (part of the discovery questionnaire), fed the recon digest plus the verbatim inline Q&A. Hive never writes `handoff.md` itself.

```text
You are the handoff-writer stage of a hive run. caller=hive, mode=auto, WORKSPACE_PATH=<abs>.

# Recon digest (from discovery recon)
<verbatim>

# Discovery Q&A (verbatim, asked and answered inline by hive)
<verbatim>

Write handoff.md per blueprint's existing Phase 1 format. Do not re-run recon or re-ask questions — both are already done above. Return the fixed-shape report only.
```

### Full discovery

`model: sonnet`. Used for `plan check` / `auto`, where the questionnaire itself must also run sealed (via the question protocol) rather than inline.

```text
You are the discovery stage of a hive run. caller=hive, mode=auto, phase=discovery, WORKSPACE_PATH=<abs>.

Invoke the `blueprint` skill with these parameters against this work item: <task_ref + detail>. Run Phase 1 in full, including the questionnaire — ask via STATUS: NEEDS_CONTEXT (QUESTION/DEFAULT/IMPACT) rather than guessing; you will be resumed by message with the answer, never re-dispatched fresh. Write handoff.md yourself. Return the fixed-shape report only.
```

### Spec drafter

`model: opus`. The architecture document; hardest reasoning in the run.

```text
You are the spec stage of a hive run. caller=hive, mode=auto, phase=spec, WORKSPACE_PATH=<abs>.

Invoke the `blueprint` skill with these parameters. Run Phase 2 + Phase 3 (draft + review + reconcile), write spec.v<N>.md, and stop — do not advance to planning. If a decision genuinely needs the human, end your turn with STATUS: NEEDS_CONTEXT (QUESTION/DEFAULT/IMPACT) instead of guessing; you will be resumed by message with the answer, keeping this context. Return the fixed-shape report only.
```

### Plan drafter

`model: opus`. Task decomposition and trap-naming.

```text
You are the plan stage of a hive run. caller=hive, mode=auto, phase=plan, WORKSPACE_PATH=<abs>.

Invoke the `blueprint` skill with these parameters. Run Phase 5 + Phase 5b (draft + review + reconcile), write plan.v<N>.md, and stop. If no spec.v*.md exists in the workspace (plan-only tier), ground in handoff.md plus the repo instead. If a decision genuinely needs the human, end your turn with STATUS: NEEDS_CONTEXT (QUESTION/DEFAULT/IMPACT); you will be resumed by message, not re-dispatched. Return the fixed-shape report only.
```

### Direct-tier implementer

`model: sonnet`; escalate to `opus` when any target path matches execute-plan's sensitive-path set (auth/session/token/crypto/secret, migrations, root config).

```text
You are the direct-tier implementer for a hive run.

# Request
<verbatim>

# Triage files
<the triage worker's `files` list>

# Repo conventions
<repo-conventions probe: existing style/lint/test patterns near the touched files>

# Working agreement
- Comment discipline: execute-plan/references/subagent-prompts.md, drafter working agreement — apply it verbatim, do not restate it here.
<!-- ticket-prefix addendum, injected when a ticket key is detected -->
- All commit messages MUST start with `<KEY>: `.

Under plan check / auto: commit your work and return the commit range as PATH. Under every step: stage but do not commit, and return the staged paths as PATH — hive will show the diff and resume you with commit or revise.

If a step is ambiguous and you cannot proceed without guessing, end your turn with STATUS: NEEDS_CONTEXT (QUESTION/DEFAULT/IMPACT); you will be resumed by message, keeping this context. Return the fixed-shape report only.
```

### Direct-tier reviewer

`model: sonnet`; `opus` on the same sensitive paths as the implementer.

```text
You are the direct-tier reviewer for a hive run.

# Task text
<verbatim>

# Diff
<git diff <pre>..HEAD>

# Verification
<hive's own re-run of any obvious repo verification, real output>

Output exactly one of: ACCEPT / CHANGES_REQUESTED (bulleted, specific, file:line) / ESCALATE. One re-dispatch round max on CHANGES_REQUESTED.
```

### Sealed `execute-plan` phase worker

`model: sonnet`. It orchestrates its own sub-workers; the phase shell needs no depth.

```text
You are the execution stage of a hive run. caller=hive, mode=auto, WORKSPACE_PATH=<abs>.

Invoke `execute-plan` with these parameters against plan.v<N>.md. Read `oversight` from .pipeline.json for your checkpoint policy. Hand failures to debug-loop per your own caps; call verify-before-done at the end. If a task needs a design change the plan doesn't authorize, return STATUS: NEEDS_UPSIZE with a one-line reason rather than forcing a fix. At a CHECKPOINT boundary, return STATUS: CHECKPOINT (TASK/DIFFSTAT/VERIFY); you will be resumed by message with go/stop, not re-dispatched. Return the fixed-shape report only.
```

### Sealed `finish-branch` phase worker

`model: sonnet`.

```text
You are the shipping stage of a hive run. caller=hive, mode=auto, WORKSPACE_PATH=<abs>.

Invoke `finish-branch` with these parameters. Open a draft PR, watch CI, triage bot review comments, promote to ready-for-review, ping reviewers. Do NOT merge. Return the fixed-shape report only, PATH carrying the PR URL.
```

## Model selection per worker

Verbatim from `spec.v1.md` § Model selection:

| Worker | Model | Why |
|---|---|---|
| Triage (`Explore`) | `sonnet` | Fact-gathering; the judgment stays on the orchestrator |
| Discovery / `handoff.md` writer | `sonnet` | Transcription of decided facts |
| Spec drafter | `opus` | The architecture document; hardest reasoning in the run |
| Spec reviewer | `sonnet` (blueprint's own high-stakes escalation still applies) | Unchanged from blueprint Phase 3 |
| Plan drafter | `opus` | Task decomposition and trap-naming |
| Plan reviewer | `sonnet` (same escalation) | Unchanged from blueprint Phase 5b |
| Direct implementer / reviewer | `sonnet`; `opus` on sensitive paths | execute-plan's existing escalation rule |
| execute-plan's per-task drafters / reviewers | execute-plan's own rules | Not hive's business |
| Sealed `execute-plan` / `finish-branch` phase workers | `sonnet` | They orchestrate their own sub-workers; the phase shell needs no depth |

Hive sets `model` explicitly on **every** dispatch — omission inherits the parent model, and the parent may be Fable. **Never Fable, ever, for any worker.** No exception, including when the user is running Fable as the orchestrator.
