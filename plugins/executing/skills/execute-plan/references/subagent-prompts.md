# Subagent prompts (Mode 1)

Full prompt structures for the drafter and reviewer subagents in Mode 1 (subagent-per-task). The main session constructs these from the active workspace's artifacts and dispatches via the `Agent` tool with `subagent_type: general-purpose`.

Both subagents are fresh — no shared context with the main session beyond what's injected here. They never read `plan.md` themselves; the main session extracts the task text and injects it. That's deliberate: a drafter that reads the whole plan can drift into neighboring tasks or future complexity, and the reviewer is supposed to check the diff against the task definition, not relitigate architecture.

## Inputs the main session must prepare per task

- **Spec digest** (~500 tokens). Built once at skill init from `spec.md`. Sections kept: goal, contracts/interfaces, data model bullet list, error-handling policy, file map. Prose stripped.
- **Handoff digest** (~300 tokens). Built once from `handoff.md`. Kept: constraints, open-questions-resolved. Discovery narrative dropped.
- **Task text**: full verbatim text of the current task block from `plan.md`, including all `- [ ] **Step N: …**` lines, code blocks, and verification commands.
- **Task file scope**: the `Files:` subsection of the task, with line numbers refreshed against current HEAD.
- **MSP flag**: true when the active workspace is an MSP repo (triangulated check — see `references/msp-detection.md` or apply inline). When true, append the commit-prefix line to the drafter prompt and to the reviewer's checklist.
- **`caller=execute-plan`**: cycle-prevention parameter, passed to any cross-skill invocation the drafter or reviewer ends up triggering downstream. (Drafters and reviewers don't invoke siblings themselves in v1, but the convention applies.)

Digests are rebuilt only if the content hash (sha256) of `spec.md` or `handoff.md` changed since they were built. mtime is not authoritative — re-saves without content change should not bust the cache.

## Drafter prompt

Dispatched at the start of each task. Model: `sonnet` by default. Escalate to `opus` on re-dispatch after a `BLOCKED` status — second-try thinking is worth the extra cost.

```
You are implementing one task from an approved implementation plan.

# Context (read-only)

## Spec digest
<spec digest, prebuilt>

## Handoff digest
<handoff digest, prebuilt>

# Task definition (verbatim from plan.md)

<full task text — all steps, code blocks, verification commands>

# Files in scope for this task

<task's Files section, with line ranges refreshed against current HEAD>

# Working agreement

- Follow each step exactly. The plan's steps are ordered and load-bearing.
- Run the verification commands listed in the task. Report stdout/stderr.
- Commit at the step the plan tells you to commit. Use the commit message the plan specifies.
- If you finish all steps and verifications pass: report `DONE` with the commit SHA.
- If a step is ambiguous and you can't proceed: report `NEEDS_CONTEXT` with the specific question. One round of context augmentation is allowed.
- If a verification fails after one honest attempt to fix what looks like a clear mistake: report `BLOCKED` with the failing command's full output.
- Do not improvise outside the task's file scope. Do not add tests the plan didn't specify.
- Do not modify `plan.md`, `spec.md`, `handoff.md`, or anything under `.claude-plans/`.

<!-- MSP-only addendum, injected when the active workspace is an MSP repo -->
- All commit messages MUST start with `MSP-<ticket>: ` where `<ticket>` is the ticket number extracted from the workspace slug (e.g. `MSP-7032-add-orchestrion` → `MSP-7032`).
```

### Re-dispatch on `CHANGES_REQUESTED`

Same drafter prompt, with an additional block appended after `# Working agreement`:

```
# Reviewer requested changes

The reviewer flagged the following issues with your previous commit (<sha>). Address each, then commit the fix on top of the existing commit (do not amend — create a new commit that the reviewer can re-review).

<verbatim CHANGES_REQUESTED list from the reviewer>
```

One re-dispatch round only. If the reviewer rejects again, escalate to the user.

### Re-dispatch on `NEEDS_CONTEXT`

Same drafter prompt, with the specific question's answer appended after the relevant digest. Do not dump the whole spec or whole handoff — answer the specific question the drafter raised. One augment per task; second `NEEDS_CONTEXT` from the same task converts to `BLOCKED`.

## Reviewer prompt

Dispatched after the drafter reports `DONE`. Model: `sonnet` by default. Override to `opus` when the task touches any of:

- A file whose name contains `auth`, `session`, `token`, `crypto`, or `secret` (case-insensitive)
- Migration files (paths matching `migrations/`, `*.sql`, `schema.prisma`, `alembic/versions/`)
- Root config: `package.json`, `tsconfig.json`, `Cargo.toml`, `pyproject.toml`, `go.mod` at repo root
- Files explicitly tagged `review: opus` in the plan (a task-level annotation the plan author can set)

The reviewer does NOT receive the spec or handoff digests. Bringing the spec in again invites the reviewer to relitigate architecture rather than check the diff against the task definition. The task is the contract; the diff either matches it or it doesn't.

```
You are reviewing one commit against the task that produced it.

# Task definition (what the drafter was told to do)

<full task text>

# What the drafter changed

## Diff stat
<output of `git show --stat <sha>`>

## Diff
<output of `git diff <sha>~ <sha>`>

# Verification output

<stdout/stderr from the task's verification commands, as the drafter reported>

# Your job

Answer two questions:

1. **Spec compliance.** Did the drafter do what the task says? Not less (missing steps, missing files), not more (out-of-scope additions, ad-libbed tests, refactors the task didn't request).
2. **Diff quality.** Is the diff free of obvious problems? Dead code, unhandled errors that the task didn't acknowledge, broken types, off-by-one in code blocks the task pasted verbatim.

Do not propose changes that go beyond the task's scope. If the task says "add endpoint" and lists no tests, do not ask for tests — the plan owns coverage decisions, not you.

Output exactly one of:

- `ACCEPT` — task complete, diff matches task, no concerns.
- `CHANGES_REQUESTED` — followed by a bulleted list of specific, concrete fixes the drafter should make. Cite file paths and line numbers from the diff.
- `ESCALATE` — task definition is incoherent or impossible as written. Surface to main session with reasoning.

<!-- MSP-only addendum -->
Additionally verify: the commit message starts with `MSP-<ticket>: `. If it does not, include this in `CHANGES_REQUESTED`.
```

## Cap summary

These caps live in the main session's task-loop logic; the subagents don't enforce them.

| Drafter status | Action | Cap |
|---|---|---|
| `DONE` + reviewer `ACCEPT` | Mark task done, advance. | — |
| `DONE` + reviewer `CHANGES_REQUESTED` | Re-dispatch drafter with reviewer notes. One re-review round. | 1 round, then escalate. |
| `DONE` + reviewer `ESCALATE` | Pause, surface reviewer reasoning, ask user. | — |
| `NEEDS_CONTEXT` | Augment prompt with answer to specific question, re-dispatch. | 1 augment, then convert to `BLOCKED`. |
| `BLOCKED` | Invoke `debug-loop` with `caller=execute-plan`. | 2 `debug-loop` invocations per task, then hard pause. |

After any cap is hit: hard pause, surface state to the user, do not auto-retry. The user owns the next call.
