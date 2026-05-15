---
name: finish-branch
description: Use this skill whenever the user says "make the PR", "open a pull request", "open the PR", "let's ship it", "ready for review", "create the PR", "push for review", or "PR it". Also trigger automatically when verify-before-done emits a passing run in the same session, unless the user says "I'll open the PR myself", "just push the branch", or "no PR yet". When blueprint Phase 7 hands off and the user picks "PR it" at the execution-mode prompt, trigger immediately. Default bias is to run — if the user is talking about shipping work on a branch, this skill is the right one.
---

# finish-branch

Turn a green branch into a PR — title generated from spec/handoff, body drawn from the blueprint workspace, state verified clean, ticket linked — without the user typing a single line of the PR description.

**Announce at start:** "Using finish-branch to open the PR — verifying clean state and drafting the body from your spec/decisions."

## When to trigger

Auto-trigger after a passing verify-before-done in the same session, or on any of the phrases in the frontmatter. Explicit opt-outs: "I'll open the PR myself", "just push the branch", "no PR yet".

**Scope:** open a PR (or update the one already open). Not in scope: merging, interactive rebase, branch cleanup after merge, multi-mode branch routing.

## In-session tracking

Use `TodoWrite` to track the 5 pre-flight checks as they run. Update each item to done/blocked as the gate resolves.

## Active-workspace resolution

1. If `WORKSPACE_PATH` is passed as a context parameter, use it — no discovery.
2. Enumerate `.claude-plans/*/` in repo root (or cwd), filter to dirs containing `plan.md` or `spec.md`.
3. If one match, use it. If multiple, prefer the slug containing the current branch's ticket key; break ties by mtime of `plan.md`.
4. If zero matches: ad-hoc mode — generate PR body from git log alone, note "_No blueprint workspace found — summary generated from commits._"

## Pre-flight gates

Run in order. Each must pass before continuing.

**1. Dirty working tree** — `git status --porcelain`. Non-empty: list dirty files and stop.

> Working tree is dirty — cannot open PR. Please commit, stash, or discard these before running finish-branch.

Never stage, stash, or commit on the user's behalf. This is not an oversight.

**2. Untracked files (non-fatal)** — Warn: "Untracked files present: [list]. These won't be in the PR but may represent forgotten work. Continue anyway?" Proceed on confirmation.

**3. verify.json freshness**
Read `.claude-plans/<active>/verify.json` (schema owned by verify-before-done; relevant fields: `commit_sha`, `result`, `timestamp`). Gate fails if: file absent, `commit_sha != HEAD`, or `result != "pass"`.

> verify-before-done hasn't passed against the current HEAD. Run it first, or confirm explicitly that you want to skip this gate.

If user says "skip the gate" / "I've already verified this": proceed, but add a visible warning to the PR body: "_Note: verify-before-done was not run against the HEAD included in this PR._"

**Also check progress.json (advisory only):** if `.claude-plans/<active>/progress.json` is present and its `status` field is not `"complete"`, warn:

> progress.json shows status '<value>' — execute-plan may not have finished. Proceeding, but verify your diff is complete.

This does not block. `verify.json` is the authoritative gate; `progress.json` is advisory.

**4. Branch pushed to remote**
If `origin/<branch>` is missing or local HEAD is ahead: `git push -u origin <branch>`. If force-with-lease would be required, confirm first (see Force-push policy).

**5. Branch up-to-date with base**
Run `git merge-base --is-ancestor <base> HEAD`. If base has commits the branch doesn't include:

> Base branch (<base>) has commits your branch doesn't include.
> Options:
>   (a) Rebase my branch onto <base> (then re-run verify-before-done)
>   (b) Proceed anyway — let the PR show the divergence

Do not rebase without explicit user confirmation.

**6. Knowledge-capture reflection (interactive mode only)**

Single batched prompt (skip entirely in auto mode — auto mode relies on debug-loop / execute-plan having queued any captures to `open-questions.md` during execution):

> Anything new worth remembering about this work before opening the PR? (Yes / No / Show suggestions from this session)

If `knowledge-capture` is installed, invoke it with `caller=finish-branch`, `kind=pattern` or `kind=stack-note` (skill asks the user which), and the user's free-form input. If not installed, print "if `knowledge-capture` were installed I'd save that for next time" and continue. If user says No or skips: continue without writing.

Note any deferred captures from `open-questions.md` and surface count: "3 deferred captures from this session — review in `.claude-plans/<active>/open-questions.md` before merging."

## Branch convention enforcement

### MSP detection (triangulated)

The repo is an **MSP project** if ANY of:
1. `git remote get-url origin` contains `nicusa` or `tylertech` (case-insensitive)
2. Current branch name matches `^MSP-\d+/`
3. `git config user.email` ends in `@tylertech.com`

Any single match is sufficient.

### Hard block: PR from main or master

```
Cannot open a PR from 'main'. Switch to a feature branch first.
```

No override. No confirmation prompt.

### MSP repo — branch correctly prefixed (`MSP-XXXX/short-description`)

Proceed. Extract ticket key (e.g. `MSP-7032`) for title formatting and JIRA link generation.

### MSP repo — branch missing prefix

Stop and offer:

> Branch 'add-feature' doesn't follow the MSP convention (MSP-XXXX/short-description).
> Options:
>   (a) Rename — tell me the ticket number and I'll run `git branch -m` + push with `--force-with-lease`
>   (b) Proceed without renaming — PR created without ticket prefix

On rename: re-run pre-flight from step 4. After push succeeds, offer to delete the old remote ref and check for an orphaned open PR on the old branch name.

### Non-MSP repo

Sample merged PRs: `gh pr list --state merged --limit 20 --json headRefName`. If ≥ 60% share a prefix pattern (`PROJ-\d+/`), apply that convention identically to MSP enforcement. If no pattern emerges: skip ticket enforcement; only enforce the main/master hard block.

## PR title generation

Source priority:
1. `spec.md` → `## Goal` section, first sentence
2. `handoff.md` → `**Goal (one sentence):**` line
3. Fallback: `git log --oneline -1`

Format:
- MSP: `MSP-XXXX: <action verb> <object>`
- Non-MSP with ticket: `PROJ-XXXX: <action verb> <object>`
- Generic: `<action verb> <object>` (sentence-case, imperative)

Truncate to 70 characters with ellipsis if the source runs long; embed the full sentence at the top of the PR body's Summary section.

**Show the generated title and wait for confirmation before running `gh pr create`.** This is the one human-in-the-loop checkpoint before the PR is public.

## PR body template

Blueprint workspace files are gitignored and inaccessible to PR reviewers. Everything drawn from them must be embedded inline — never reference `.claude-plans/` paths in the PR body.

### Canonical template

```markdown
## Summary

<1-3 bullet points from spec.md Goal + handoff.md Goal. Imperative voice. What changed, not how.
If spec goal was truncated in the title, the full sentence goes as the first bullet.>

## Architecture context

<1-2 sentences from spec.md Architecture section — the load-bearing design choice, not a file tour.
Omit section entirely if spec has no Architecture section.>

## Test plan

<Checklist from plan.md verification steps, or tests covering the diff. ≤ 8 items.>
- [ ] <step>
- [ ] <step>

## Non-goals / out of scope

<1-3 bullets from spec.md Non-goals, if present. Omit section if absent.>

## Key decisions

<Top 3 entries from decisions.md, each rendered as:>
- **<short title>** — <why in one sentence>

<If decisions.md has > 3 entries: "_N additional decisions logged in .claude-plans workspace._">
<If decisions.md absent: omit section.>

JIRA: https://nicusa.atlassian.net/browse/<MSP-XXXX>
```

Top-3 selection: use the three most recent entries from decisions.md.

### Rendered example

```markdown
## Summary

- Add Datadog Orchestrion for build-time APM instrumentation, replacing manual dd-trace wiring
- Covers all Lambda handlers in the payments and notifications services
- No runtime dependency changes; instrumentation is injected at build time

## Architecture context

Orchestrion operates as a Go build plugin; it rewrites imports at `go build` time rather than at
init(), which removes the need for any `import _ "gopkg.in/DataDog/dd-trace-go.v1/..."` lines.

## Test plan

- [ ] `make build` succeeds with `-toolexec orchestrion` flag
- [ ] `go test ./...` green locally
- [ ] APM traces visible in Datadog dev environment for a sample invocation
- [ ] Lambda cold-start duration within 5% of baseline (see load test in plan step 8)

## Non-goals / out of scope

- Replacing the existing RUM configuration — that is a separate ticket
- Adding custom spans; this ticket only covers automatic instrumentation

## Key decisions

- **Orchestrion over manual tracing** — eliminates 300+ lines of boilerplate across 12 handlers
- **Build-time injection** — safer than init() hooks; no runtime panic if dd-agent unreachable
- **Keep dd-trace-go as a direct dep** — Orchestrion still needs the type definitions at compile time

JIRA: https://nicusa.atlassian.net/browse/MSP-7032
```

Note: `Fixes`/`Closes` GitHub keywords close GitHub issues, not JIRA tickets. Use a plain `JIRA:` line. JIRA Smart Commits (triggered by commit messages prefixed `MSP-XXXX:`) handle the JIRA side independently.

## gh CLI requirements

Run `which gh`, `gh auth status`, `gh repo view` before `gh pr create`.
- **Not installed:** surface `https://cli.github.com/` and stop — never call the GitHub API directly.
- **Not authenticated:** surface `gh auth login` and stop — never capture tokens silently.
- **Wrong account:** print `gh api user --jq .login` and repo org; confirm before proceeding.

Surface the exact fix command and stop on any failure.

## Existing PR handling

Check `gh pr list --head <branch> --json number,url,state` before creating. If a PR already exists: confirm with the user, then `gh pr edit <number> --body "..."` (optionally `--title`). Offer to add a comment summarizing what changed since the PR was opened. If the PR is merged or closed: stop and tell the user.

## Base branch detection

`gh repo view --json defaultBranchRef --jq .defaultBranchRef.name`. Fallback: `git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@'`. If both fail: default to `main`, warn, let the user override at confirmation ("Base branch detected as 'main' — correct? If not, say 'base: develop'"). Pass via `--base <base>` to `gh pr create`.

## Reviewers

Not folded in. Accept override: "make the PR, add @alice as reviewer" → `--reviewer alice` on `gh pr create`. The PR body (summary, test plan, key decisions) serves as the review brief.

## Draft vs ready

| Signal | Default |
|---|---|
| `spec.md` contains "WIP" or "work in progress" | draft |
| `verify.json` `result != "pass"` but gate skipped | draft |
| User phrase contains "draft", "wip", "not ready" | draft |
| All green, user confirmed | ready |

Override at the confirmation checkpoint ("make it a draft" / "ready to review"). When in doubt, ask.

## Force-push policy

`--force-with-lease` only, never bare `--force`. Never to `main` or `master`. Two scenarios only:
1. Branch rename after pre-flight (user accepted rename offer).
2. User explicitly confirmed rebase in the "up-to-date with base" step.

Always print the exact command and wait for confirmation:

> About to run: `git push --force-with-lease origin MSP-7032/add-orchestrion`
> This will rewrite the remote branch. OK? (y/N)

## Anti-patterns

- **Committing dangling changes.** Never stage, stash, or commit on the user's behalf. The pre-flight dirty-tree check is a hard stop, not a suggestion.
- **Opening a PR from main.** Hard block with no confirmation path.
- **AI-cheerleader PR bodies.** Summary bullets must be factual and imperative — what was added/changed/removed. Reject any generated text that evaluates the work ("dramatically improves", "exciting new feature").
- **Scope-drift PRs.** If the diff touches files outside spec.md's stated scope, call it out at the confirmation checkpoint. Don't silently let an oversized diff go to review.
- **Swallowing verify failures.** If the gate was skipped, the draft-PR default and the body warning note are the only safety net. Do not pretend the gate passed.
- **Embedding `.claude-plans/` paths in the PR body.** Gitignored and meaningless to reviewers — inline the content.
- **Becoming a branch router.** finish-branch opens a PR. Merge/discard/keep options belong to git, not this skill.

## Composition

- **Callers:** verify-before-done hands off here on success; blueprint Phase 7 on user's "PR it" choice; direct user invocation after any green session.
- **Reads:** `verify.json`, `progress.json`, `spec.md`, `handoff.md`, `plan.md`, `decisions.md`, `open-questions.md` — all from `<active>/`, all optional; degrades gracefully to git-log body when workspace is absent. `open-questions.md` count is surfaced in the pre-flight summary.
- **Writes:** nothing to repo or workspace directly. Side effects: `git push` and `gh pr create` / `gh pr edit` only. May invoke `knowledge-capture` (which owns its own writes).
- **Calls:** `knowledge-capture` once at pre-flight gate #6 (interactive mode only), passing `caller=finish-branch`. finish-branch does not invoke verify-before-done. verify and finish-branch are separate gates with separate failure modes: verify runs many times during development; finish-branch runs once per PR. The boundary is real.
- **Cycle prevention:** if a future caller opts in to invoking verify-before-done from within this skill, pass `caller=finish-branch` so verify-before-done suppresses its own finish-branch hand-off (no re-entry).
- **Sibling absent:** if verify-before-done isn't installed and `verify.json` is missing, say so once, then proceed per user's explicit confirmation.

## Open questions

- **Top-3 decisions selection:** most recent vs. highest-conflict vs. scope-affecting. Punted to dogfooding (decisions.md deferred #4).
- **Convention detection threshold:** the 60% heuristic for non-MSP repos needs calibration after real non-MSP use.
- **Body refresh on push:** should finish-branch offer to refresh the PR body when new commits are pushed after PR is open? Currently no — explicit invocation only.
