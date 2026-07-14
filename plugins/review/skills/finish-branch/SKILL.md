---
name: finish-branch
description: Use this skill whenever the user says "make the PR", "open a pull request", "open the PR", "let's ship it", "ready for review", "create the PR", "push for review", or "PR it". When verify-before-done emits a passing run in the same session, offer — "verify is green — open the draft PR?" — and trigger on acceptance; do not fire automatically. Skip the offer if the user says "I'll open the PR myself", "just push the branch", or "no PR yet". When blueprint Phase 7 hands off and the user picks "PR it" at the execution-mode prompt, trigger immediately. Default bias is to run — if the user is talking about shipping work on a branch, this skill is the right one.
---

# finish-branch

Turn a green branch into a PR, then shepherd it to genuinely review-ready — title generated from spec/handoff, body drawn from the blueprint workspace, state verified clean, ticket linked. The PR opens as a **draft**, finish-branch watches CI checks and automated reviewers settle, routes anything red to the right fixer, and only promotes the PR to ready-for-review (and pings human reviewers) once it's actually clean — without the user typing a line of the PR description or babysitting the checks tab.

**Announce at start:** "Using finish-branch to open the PR as a draft — verifying clean state, drafting the body from your spec/decisions, then watching checks and bot reviews before promoting it to ready."

## In-session tracking

Use `TodoWrite` to track the pre-flight checks as they run, then the watch-and-promote phase: open draft → watch (per round) → dispatch to triage → re-check → promote to ready. Update each item to done/blocked as it resolves. The watch loop is long-running and backgrounded, so the todo list is the user's window into which round it's on.

## Active-workspace resolution

1. If `WORKSPACE_PATH` is passed as a context parameter, use it — no discovery.
2. Enumerate `.claude-plans/*/` in repo root (or cwd), filter to dirs containing `plan.v*.md` or `spec.v*.md`. Blueprint writes **only versioned** files (`plan.v<N>.md`, `spec.v<N>.md`) — never a bare `plan.md`/`spec.md`. The **current** plan/spec is the highest N (`ls plan.v*.md | sort -V | tail -1`).
3. If one match, use it. If multiple, prefer the slug containing the current branch's ticket key; break ties by mtime of the current (highest-N) plan file.
4. If zero matches: ad-hoc mode — generate PR body from git log alone, note "_No blueprint workspace found — summary generated from commits._"

## Autonomy is granted, never inferred

finish-branch runs **interactive** by default: it confirms the generated PR title before `gh pr create`, runs the knowledge-capture reflection prompt, and surfaces choices to the user. It switches to **auto** (skip those prompts, log to `open-questions.md` instead) ONLY when one of these is literally true *at this moment*. Check them; do not recall them:

1. **The user said so this turn** — "go full auto", "skip the gates", "don't ask, just ship it", or a literal `mode=auto`.
2. **The invocation prompt says so** — a calling skill spawned this run with `mode=auto`.
3. **A pipeline grant exists** — `.claude-plans/<active>/.pipeline.json` is present with `"mode": "auto"`. Confirm with Bash; it's the durable orchestrator signal that survives a subagent boundary.

```bash
test -f .claude-plans/<active>/.pipeline.json && \
  grep -q '"mode"[[:space:]]*:[[:space:]]*"auto"' .claude-plans/<active>/.pipeline.json && \
  echo "GRANT: auto" || echo "GRANT: interactive"
```

If none hold, you are **interactive** — a memory or the user's mood is not a grant.

**Auto never waives a safety gate.** The pre-flight gates below (dirty tree, verify.json freshness, PR-from-main hard block) block in *both* modes — auto means "don't stop to ask permission for the things you'd otherwise ask about", not "skip the checks that protect the branch". The one human-in-the-loop checkpoint that auto *does* skip is the PR-title confirmation; under a grant, use the generated title and note it in `open-questions.md`.

**Stop point under a grant.** If `.pipeline.json` carries `"stop_at": "ready-for-review"` (the `auto-ship` default), finish-branch's normal terminus — promote the draft to ready and ping human reviewers — *is* the stop. Do not merge; merging is always the human's call.

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

**Sequencing after (a):** a rebase produces a new HEAD, which invalidates `verify.json` (gate 3 checks `commit_sha == HEAD`). finish-branch never invokes verify-before-done itself — after the rebase and confirmed force-push, tell the user (or the calling pipeline) to re-run verify-before-done, then re-invoke finish-branch. On that re-run, gate 3 re-fires against the new HEAD and must pass again before the PR opens.

**6. Knowledge-capture reflection (interactive mode only)**

Single batched prompt (skip entirely in auto mode — auto mode relies on debug-loop / execute-plan having queued any captures to `open-questions.md` during execution):

> Anything new worth remembering about this work before opening the PR? (Yes / No / Show suggestions from this session)

If `knowledge-capture` is installed, invoke it with `caller=finish-branch`, `kind=pattern` or `kind=stack-note` (skill asks the user which), and the user's free-form input. If not installed, print "if `knowledge-capture` were installed I'd save that for next time" and continue. If user says No or skips: continue without writing.

Note any deferred captures from `open-questions.md` and surface count: "3 deferred captures from this session — review in `.claude-plans/<active>/open-questions.md` before merging."

## Branch convention enforcement

### Hard block: PR from main or master

```
Cannot open a PR from 'main'. Switch to a feature branch first.
```

No override. No confirmation prompt.

### Ticket-convention detection

This repo's branch convention is **discovered, not assumed**. In precedence order:

1. **Config** — if repo `CLAUDE.md` declares a branch convention (a ticket-key prefix or naming rule), that wins.
2. **Heuristic** — sample merged PRs: `gh pr list --state merged --limit 20 --json headRefName`. If ≥ 60% share a ticket-key prefix matching `^[A-Z][A-Z0-9]+-\d+/`, the repo uses ticket-prefixed branches — enforce it.
3. **No signal** — skip ticket enforcement entirely; only the main/master hard block applies.

### Branch correctly prefixed (convention detected)

Proceed. Extract the ticket key (e.g. `PROJ-1234`) for title formatting and tracker-link generation.

### Branch missing the prefix (convention detected)

Stop and offer:

> Branch 'add-feature' doesn't follow this repo's convention (`<KEY>-XXXX/short-description`).
> Options:
>   (a) Rename — tell me the ticket number and I'll run `git branch -m` + push with `--force-with-lease`
>   (b) Proceed without renaming — PR created without ticket prefix

On rename: re-run pre-flight from step 4. After push succeeds, offer to delete the old remote ref and check for an orphaned open PR on the old branch name.

## PR title generation

Source priority (everywhere below, `spec.md`/`plan.md` mean the **current** artifact — the highest-N `spec.v*.md`/`plan.v*.md` blueprint wrote):
1. `spec.md` → `## Goal` section, first sentence
2. `handoff.md` → `**Goal (one sentence):**` line
3. Fallback: `git log --oneline -1`

Format:
- With detected ticket convention: `<KEY>-XXXX: <action verb> <object>`
- Generic (no ticket convention): `<action verb> <object>` (sentence-case, imperative)

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

<Tracker link — emit ONLY when the repo has a JIRA site configured (cloudId/site in CLAUDE.md)
AND the branch ticket key matches a JIRA-style key. Format: `JIRA: <SITE_URL>/browse/<KEY>-XXXX`.
Omit the line entirely otherwise.>
```

Top-3 selection: use the three most recent entries from decisions.md.

Full rendered example: see `references/pr-body-examples.md`.

Note: `Fixes`/`Closes` GitHub keywords close GitHub issues, not JIRA tickets. When the repo uses JIRA, emit a plain `JIRA:` line — JIRA Smart Commits (triggered by commit messages prefixed `<KEY>-XXXX:`) handle the JIRA side independently. When the repo uses GitHub issues, prefer `Fixes #<n>` instead.

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

Not folded in, and never attached to the draft. If the user names reviewers ("make the PR, add @alice as reviewer"), hold those handles and apply them **at promotion** (`gh pr edit <num> --add-reviewer alice` after `gh pr ready`), so a human is never pinged about a draft that still has red checks. The PR body (summary, test plan, key decisions) serves as the review brief. If the user names no reviewers, offer at promotion (see "Promote to ready").

## Always open as draft

Every PR opens as a draft — `gh pr create --draft`, no exceptions. Draft is the staging state, not a special case: it lets CI and automated reviewers (Copilot, CodeRabbit, etc.) run and comment *before* any human is pinged. (This codifies the sequence users previously hand-drove on every PR — draft, wait for checks and bot review, triage, then ready — replacing an earlier signal-based draft-vs-ready decision.) "Ready for review" is an **earned promotion**, not the default — the PR is flipped to ready only after the watch-and-promote phase below comes back clean. This guarantees the one thing the user cares about: human reviewers are only pinged on work that is genuinely clean.

Do not add human reviewers at creation time. Reviewer assignment happens at promotion (see "Promote to ready"), so a reviewer is never notified about a draft that still has red checks.

The only override is the user opting *out* of the watch entirely ("just open the draft, don't watch it" / "I'll handle review myself") — in that case open the draft, skip the watch phase, and say so. There is no "open it straight to ready" path; if the user insists on skipping straight to ready, open the draft, promote immediately, and warn that checks and bot reviews haven't settled.

## Post-open: watch and promote

After the draft PR is created, finish-branch shepherds it to ready. This phase is a **bounded loop**: watch → route red items to fixers → fixers push → checks re-run → re-evaluate. When everything is clean, promote.

### 1. Detect bot reviewers (cheap, once)

Before starting the watch, check whether this repo has automated reviewers at all — don't burn the 10-minute give-up window on a repo that has no bots:

```bash
gh pr list --state merged --limit 10 --json number,reviews,comments \
  --jq '[.[] | (.reviews[]?.author.login, .comments[]?.author.login)] | map(select(test("\\[bot\\]$|copilot|coderabbit|greptile|sourcery"))) | unique'
```

If the result is empty across ~10 recent merged PRs, no bot reviewer is active: skip the bot-review settle window entirely — the watch settles on checks alone. If bots appear, keep the full settle condition below.

### 2. Background the watch

Checks and automated reviews take minutes, so don't block the session. Background the watch and re-engage when it settles, using `ScheduleWakeup` with a delay matched to how long this repo's checks usually take (start at ~120–270s while checks are actively running; back off to longer idle ticks if a bot review is the only thing outstanding).

**If `ScheduleWakeup` isn't available** (probe the deferred-tool list / ToolSearch for it before assuming), fall back to a background Bash poll: run `gh pr checks <num> --watch` in the background, or an interval loop (`while :; do gh pr checks <num> --json name,bucket,link; sleep 150; done`) as a background command, and re-engage when it exits or reports. The deciding signal is identical in both modes: **no check left in bucket `pending`** (plus the bot-review condition below, when bots are present) — the wake-up mechanism changes, the settle condition does not.

Each wake-up, poll:

```bash
# Status checks — settled when no bucket == "pending"
gh pr checks <num> --json name,bucket,link

# Automated review state — has the bot posted yet?
gh pr view <num> --json reviewDecision,reviewRequests,latestReviews,statusCheckRollup
```

The watch is **settled** when: every check has left `pending` (all are pass/fail/skip/cancel) AND any requested automated reviewer has either posted a review or a give-up timeout has elapsed. Copilot/bot review timing varies and some repos only review on ready — so set a give-up window (default ~10 min of no new review activity after checks settle); if it elapses with checks green, proceed to promote rather than waiting forever.

Tell the user the watch is backgrounded and roughly when you'll check back. They can interrupt anytime.

### 3. Route by type when the watch settles

Evaluate what's outstanding and route — **finish-branch does not fix anything itself**; it dispatches:

- **Failed or cancelled checks** → invoke `ci-check-triage` with `caller=finish-branch` and `PR_NUMBER=<num>`. It classifies (real/flaky/external), delegates real fixes to debug-loop, re-runs flaky ones, pushes.
- **Unresolved review comments** (bot or human) → invoke `pr-review-triage` with `caller=finish-branch` and `PR_NUMBER=<num>`. It grades each, applies approved fixes, pushes, replies.
- **Both** → invoke `ci-check-triage` first (a red build often *causes* review noise; getting the build green first avoids triaging comments on code that's about to change), then `pr-review-triage` on the next settled cycle.

This dispatch is automatic — no confirmation gate before invoking the triage skills. That's safe because **each triage skill has its own hard approval gate** before it edits or pushes anything; finish-branch only auto-*enters* triage, it never auto-applies a fix. (If the user is running finish-branch in an explicitly non-interactive/auto mode, the triage skills' own auto-mode behavior governs from there.)

### 4. Loop, with a cap

A triage skill's push re-triggers the checks. On the next wake-up, re-poll and re-evaluate. Repeat until clean — but **cap at 3 rounds**. If the PR still isn't clean after 3 watch→fix→re-check cycles, stop the loop and hand back to the user with a summary of what's still red and why (likely a real failure that needs human judgment, an escalation from triage, or a genuinely flaky suite). Don't loop forever chasing green.

Also stop and hand back immediately (no further rounds) if: a triage skill reports an `escalate` verdict, a fix can't be applied cleanly, or a push is rejected.

### 5. Promote to ready

When the watch settles with all checks green and no unresolved review threads:

```bash
gh pr ready <num>
```

Then — and only then — add reviewers if the user named any (`gh pr edit <num> --add-reviewer <handle>`), or offer to:

> PR #`<num>` is clean — checks green, no open review threads. Promoted to ready for review. Want me to request reviewers? (name them, or say "no")

Report the final state: PR URL, that it's ready, checks green, reviewers requested (if any), and a one-line trail of what triage handled during the watch.

## Force-push policy

`--force-with-lease` only, never bare `--force`. Never to `main` or `master`. Two scenarios only:
1. Branch rename after pre-flight (user accepted rename offer).
2. User explicitly confirmed rebase in the "up-to-date with base" step.

Always print the exact command and wait for confirmation:

> About to run: `git push --force-with-lease origin PROJ-1234/add-orchestrion`
> This will rewrite the remote branch. OK? (y/N)

## Anti-patterns

- **Committing dangling changes** — never stage, stash, or commit on the user's behalf; the dirty-tree gate is a hard stop.
- **Opening a PR from main** — hard block, no confirmation path.
- **AI-cheerleader PR bodies** — summary bullets are factual and imperative; reject text that evaluates the work ("dramatically improves").
- **Scope-drift PRs** — if the diff touches files outside spec.md's stated scope, call it out at the confirmation checkpoint.
- **Swallowing verify failures** — if the gate was skipped, keep the body warning note; never pretend the gate passed.
- **Embedding `.claude-plans/` paths in the PR body** — gitignored and meaningless to reviewers; inline the content.
- **Becoming a branch router** — finish-branch owns open draft → watch → dispatch → promote; no merge/discard/keep menu, no fixing (checks → `ci-check-triage`, comments → `pr-review-triage`, bugs → `debug-loop`), no merging.
- **Fixing checks or comments inline** — always dispatch; patching directly duplicates the triage skills and skips their approval gates.
- **Promoting to ready while red** — never `gh pr ready` with failing checks or unresolved threads unless the user explicitly overrode the watch (then say so and warn).
- **Looping forever chasing green** — cap at 3 watch→fix→re-check rounds, then hand back to the user.

## Composition

- **Callers:** verify-before-done offers this skill on success ("verify is green — open the draft PR?") and hands off only on the user's yes; blueprint Phase 7 on user's "PR it" choice; direct user invocation after any green session.
- **Reads:** `verify.json`, `progress.json`, current `spec.v*.md`, `handoff.md`, current `plan.v*.md`, `decisions.md`, `open-questions.md` — all from `<active>/`, all optional; degrades gracefully to git-log body when workspace is absent. `open-questions.md` count is surfaced in the pre-flight summary.
- **Writes:** nothing to repo or workspace directly. Side effects: `git push`, `gh pr create --draft`, `gh pr edit`, `gh pr ready`, `gh pr edit --add-reviewer` (at promotion), and `ScheduleWakeup` for the background watch. May invoke `knowledge-capture` (which owns its own writes).
- **Calls:**
  - `knowledge-capture` once at pre-flight gate #6 (interactive mode only), passing `caller=finish-branch`.
  - `ci-check-triage` during the watch phase when checks are red, passing `caller=finish-branch` + `PR_NUMBER`. It owns classification and delegates real fixes to debug-loop.
  - `pr-review-triage` during the watch phase when review comments are unresolved, passing `caller=finish-branch` + `PR_NUMBER`. It owns grading and applies approved fixes.
  - finish-branch does **not** invoke verify-before-done. verify and finish-branch are separate gates with separate failure modes: verify runs many times during development; finish-branch runs once per PR (then watches it). The boundary is real.
- **Cycle prevention:** the watch loop is bounded by the 3-round cap, and the triage skills receive `caller=finish-branch` so they never re-invoke finish-branch. Loop re-entry is driven solely by finish-branch's own wake-ups re-polling the settled checks.
- **Sibling absent:** if verify-before-done isn't installed and `verify.json` is missing, say so once, then proceed per user's explicit confirmation.

## Open questions

- **Top-3 decisions selection:** most recent vs. highest-conflict vs. scope-affecting. Punted to dogfooding (decisions.md deferred #4).
- **Convention detection threshold:** the 60% heuristic for ticket-prefixed repos needs calibration after real use across more repos.
- **Body refresh on push:** should finish-branch offer to refresh the PR body when new commits are pushed after PR is open? Currently no — explicit invocation only.
