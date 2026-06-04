# finish-branch — DESIGN

Status: draft. Replaces `SKILL.md` once user approves.

## Goal

Turn a green branch into a PR and shepherd it to genuinely review-ready — title generated from
spec/handoff, body drawn from the blueprint workspace, ticket linked, state verified clean — without the
user typing a single line of the PR description or babysitting the checks tab. Owns the "did you mean to
ship exactly this?" moment before the PR is visible to anyone else, AND the "is this actually clean
enough to ping a human?" moment before reviewers are notified.

The PR always opens as a draft. finish-branch then watches CI checks and automated reviewers settle,
dispatches anything red to the right fixer (`ci-check-triage` for checks, `pr-review-triage` for
comments), and promotes the PR to ready-for-review only once it comes back clean.

Not in scope: merging, rebasing interactively, closing the branch after merge, routing the user through
a menu of merge-vs-keep-vs-discard options, and — critically — *fixing* anything itself. finish-branch
dispatches; the triage skills and debug-loop fix. The lifecycle it owns is: open draft → watch →
dispatch → promote.

## Why always-draft (the 2026-06 rework)

Originally finish-branch opened draft *or* ready based on signals (WIP markers, skipped verify). The user
kept hand-steering the same sequence every PR: open a draft, wait for checks and the Copilot review, then
triage whatever popped up before marking ready. Persisting that: draft becomes the unconditional staging
state, "ready" becomes an earned promotion, and the watch+dispatch loop is built in. The payoff the user
cares about — human reviewers are pinged *only* on work that's actually clean — falls out of making
"ready" something the PR has to earn rather than the default.

## When to trigger

Pushy after green verify-before-done, quiet otherwise.

Trigger phrases:
- "make the PR", "open a pull request", "let's ship it", "create the PR"
- After verify-before-done emits a passing run in the same session
- Blueprint Phase 7 hand-off if the user says "PR it" at the execution-mode prompt

Opt-out: "I'll open the PR myself", "just push the branch", "no PR yet".

The skill does NOT re-run verify-before-done for you. It expects to be called after the gate passes.
If verify-before-done hasn't run (or its state artifact is stale), the skill says so and stops until
you either run it or confirm explicitly.

## Pre-flight: clean state

Checks run in this exact order. Each gate must pass before continuing.

**1. Dirty working tree**
```bash
git status --porcelain
```
If output is non-empty: list the dirty files and stop.

> Working tree is dirty — cannot open PR. Please commit, stash, or discard the following changes
> before running finish-branch:
>   M src/foo.ts
>   ?? scratch.txt

The skill does NOT stage or commit on your behalf. NEVER. This is not an oversight — committing on
the user's behalf is explicitly prohibited by CLAUDE.md.

**2. Untracked files (non-fatal)**
Warn but proceed if the user confirms. A one-time prompt:

> Untracked files present: [list]. These won't be in the PR but may represent forgotten work. Continue anyway?

**3. Verify-before-done freshness**
Look for `.claude-plans/<slug>/verify.json` (written by verify-before-done):
```json
{ "timestamp": "...", "commit_sha": "abc123", "result": "pass" }
```
If the file is absent, or `commit_sha != HEAD`, or `result != "pass"`: warn and stop.

> verify-before-done hasn't passed against the current HEAD. Run it first, or confirm explicitly
> that you want to skip this gate.

If the user says "skip the gate" / "I've already verified this": proceed with a visible warning in
the PR body ("_Note: verify-before-done was not run against the HEAD included in this PR._").

**4. Branch pushed to remote**
```bash
git rev-parse HEAD
git rev-parse origin/<branch> 2>/dev/null
```
If remote ref is absent, or local HEAD is ahead: push.
```bash
git push -u origin <branch>
```
Confirm with the user before pushing if force-with-lease would be required (see Force-push policy).

**5. Branch up-to-date with base**
```bash
git merge-base --is-ancestor <base> HEAD
```
If base has commits the branch doesn't have: surface it.

> Base branch (<base>) has commits your branch doesn't include.
> Options:
>   (a) Rebase my branch onto <base> (then re-run verify-before-done)
>   (b) Proceed anyway — let the PR show the divergence

Do not rebase without explicit user confirmation. Do not rebase silently. Rebasing changes history
and may require force-push, both of which are user decisions.

## Branch convention enforcement

Detection order:

1. Parse `git remote get-url origin`. If the URL contains `nicusa` or `tylertech`: **MSP project**.
2. Otherwise: sample merged PRs via `gh pr list --state merged --limit 20 --json headRefName`. If
   ≥ 60% share a prefix pattern (`PROJ-\d+/`), infer that pattern. If no pattern emerges: generic
   (no ticket enforcement, only the `main`/`master` hard block).

### Hard block: PR from main or master
```
Cannot open a PR from 'main'. Switch to a feature branch first.
```
No override. No confirmation prompt. This is not a "are you sure?" situation.

### MSP repo — branch is correctly prefixed (`MSP-XXXX/short-description`)
Proceed. Extract the ticket key (`MSP-7032`) for title formatting and JIRA link generation.

### MSP repo — branch is missing the prefix (e.g. `add-feature`)
Stop and offer:
> Branch 'add-feature' doesn't follow the MSP convention (MSP-XXXX/short-description).
> Options:
>   (a) Rename the branch to MSP-XXXX/add-feature — I'll git branch -m + git push --force-with-lease
>       with your confirmation. Tell me the ticket number.
>   (b) Proceed without renaming — PR will be created without ticket prefix.

If the user gives a ticket number, rename: `git branch -m MSP-7032/add-feature`, then push with
`--force-with-lease` (see Force-push policy). Re-run pre-flight checks from step 4 after rename.
After the push succeeds, offer to delete the old remote ref (`git push origin --delete add-feature`)
and check whether a PR was open on the old branch name — leaving an orphan remote branch open is
the kind of thing that bites later.

### Non-MSP repo with a detected prefix pattern
Apply the detected convention the same way. Missing prefix → same offer (rename or proceed).

### Non-MSP repo, no detectable pattern
Skip ticket enforcement. Only enforce the hard block on `main`/`master`.

## PR title generation

**Source priority:**
1. `spec.md` → `## Goal` section, first sentence
2. `handoff.md` → `**Goal (one sentence):**` line
3. Fallback: `git log --oneline -1` (last commit message)

**Format by project:**
- MSP: `MSP-XXXX: <action verb> <object>`
- Non-MSP with ticket: `PROJ-XXXX: <action verb> <object>`
- Generic: `<action verb> <object>` (sentence-case, imperative)

**Length enforcement:**
Truncate the title to 70 characters with an ellipsis if the source goal runs long. Embed the full
first sentence from the spec/handoff goal at the top of the PR body's Summary section so nothing
is lost.

Example: `MSP-7032: Add Datadog Orchestrion build-time APM instrumenta…` → truncated; the body
opens with the full sentence.

**Show the user the generated title before running `gh pr create` and wait for a thumbs-up or edit.**
This is the one human-in-the-loop checkpoint before the PR is public.

## PR body generation

The blueprint workspace files are gitignored and not accessible to PR reviewers. Everything drawn
from them must be embedded inline — no "see `.claude-plans/...`" references in the PR body.

**Workspace lookup:**
Parse ticket key from branch name (e.g. `MSP-7032` from `MSP-7032/add-orchestrion`). Glob
`.claude-plans/*-MSP-7032-*/`. If multiple matches, use the most recent date prefix. If no match:
generate body from git log alone, with a one-line note: "_No blueprint workspace found — summary
generated from commits._"

### Canonical body template

```markdown
## Summary

<1-3 bullet points drawn from spec.md Goal + handoff.md Goal. Imperative voice. What changed, not
how it was implemented. If spec goal was truncated in the title, the full sentence goes as the first
bullet.>

## Architecture context

<1-2 sentences from spec.md Architecture section — the load-bearing design choice, not a tour of
every file. Omit this section entirely if the spec has no Architecture section.>

## Test plan

<Checklist from plan.md verification steps. If no plan.md, list tests that cover the change
(grep for test file names in the diff). Keep it to ≤ 8 items.>
- [ ] <step>
- [ ] <step>

## Non-goals / out of scope

<1-3 bullets from spec.md Non-goals, if present. Helps reviewers understand what not to comment on.
Omit section if spec has no Non-goals.>

## Key decisions

<Top 3 entries from decisions.md, each rendered as:>
- **<short title>** — <why in one sentence>

<If decisions.md has > 3 entries, note: "_N additional decisions logged in .claude-plans workspace._">
<If decisions.md is absent, omit section.>

JIRA: https://nicusa.atlassian.net/browse/<MSP-XXXX>
```

**Rendered example** (MSP-7032/add-orchestrion with a full workspace):

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

Note on JIRA linking: `Fixes`/`Closes` GitHub keywords only close GitHub issues, not JIRA tickets.
Use a plain `JIRA:` reference line. JIRA Smart Commits (triggered by commit messages) handle the
JIRA side independently.

## gh CLI requirements and failures

Before running `gh pr create`, verify:

```bash
which gh          # installed?
gh auth status    # authenticated?
gh repo view      # can access the repo?
```

**gh not installed:**
> `gh` is not installed. Install it: https://cli.github.com/. Then run `gh auth login`.
Stop. Don't try to open the PR via API calls.

**Not authenticated:**
> Not authenticated with gh. Run: `gh auth login`
Stop. Don't capture tokens silently.

**Wrong account / org:**
Print the active account (`gh api user --jq .login`) and the repo org so the user can verify:
> Active gh account: mattm — is this the account that should own the PR for nicusa/msp-payments?
Proceed only if the user confirms.

If any check fails: surface the exact fix command, explain what's missing, stop. Do not attempt to
authenticate on the user's behalf, call the GitHub API directly, or silently retry.

## Existing PR handling

Before calling `gh pr create`, check:
```bash
gh pr list --head <branch> --json number,url,state
```

**PR already exists:**
Update it instead of creating a duplicate.
- Re-generate the body from the current workspace state (spec/handoff/decisions may have been
  updated since the PR was opened).
- Confirm with the user: "PR #42 already open for this branch. Update its body with the current
  spec/decisions? (Y/n)"
- If yes: `gh pr edit <number> --body "$(cat <generated-body>)"` and optionally `--title <title>`.
- If the PR is already merged or closed: stop and tell the user. Don't re-open or create a new one.

Adding a comment summarizing what changed since the last push is useful but optional. Offer it:
> Want me to add a comment summarizing what changed since the PR was opened? (Y/n)

## Base branch detection

```bash
gh repo view --json defaultBranchRef --jq .defaultBranchRef.name
```

Fallback (if `gh` fails or no remote):
```bash
git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@'
```

If both fail: default to `main`, warn the user, and let them override at the confirmation prompt
("Base branch detected as 'main' — correct? If not, say 'base: develop'").

Pass the base branch to `gh pr create` via `--base <base>`.

## Reviewers

Reviewer assignment is **not folded into finish-branch**. The user knows who should review their PR
better than this skill does, and hardcoding teammates is a maintenance burden. The user can pass
`-r <handle>` as an override: "make the PR, add @alice as reviewer".

If an override is given, hold the handle(s) and apply them at **promotion** —
`gh pr edit <num> --add-reviewer <handle>` after `gh pr ready` — never on the draft. A human reviewer is
notified only once the watch loop has confirmed the PR is clean.

finish-branch does NOT call the `requesting-code-review` superpowers skill. That skill's useful
concern (setting context for the reviewer) is handled by the PR body itself — the summary, test
plan, and decisions sections are the review brief.

If the user later wants to iterate on review feedback, `receiving-code-review` (when installed)
handles that interaction; it's out of scope here.

## Always-draft + watch-and-promote

Every PR opens `gh pr create --draft`. No signal-based draft-vs-ready decision anymore — draft is
unconditional. "Ready" is reached by promotion (`gh pr ready`) after the watch loop comes back clean,
not by a flag at creation.

The watch-and-promote phase:

1. **Background the watch** via `ScheduleWakeup`. Each wake-up polls `gh pr checks` (settled when no
   bucket is `pending`) and `gh pr view --json reviewDecision,latestReviews,statusCheckRollup` (has the
   bot reviewed yet?). Delay tuned to repo check duration; a give-up window (~10 min) prevents waiting
   forever on a bot review that may never come (some repos only review on ready).
2. **Dispatch by type** when settled: failed/cancelled checks → `ci-check-triage`; unresolved comments →
   `pr-review-triage`; both → checks first (a red build often causes review noise). `caller=finish-branch`
   + `PR_NUMBER` on each. No confirmation gate here because each triage skill has its own hard approval
   gate — finish-branch auto-*enters* triage, never auto-applies a fix.
3. **Loop, capped at 3 rounds.** A triage push re-triggers checks; next wake-up re-evaluates. After 3
   rounds still-red, or on any `escalate` / unappliable fix / rejected push, stop and hand back to the
   user. No infinite green-chasing.
4. **Promote** when clean: `gh pr ready`, then add reviewers (held from the invoking message, or offered).
   Reviewers are never attached to the draft — a human is pinged only at promotion.

Override: the user can opt *out* of the watch ("just open the draft"). There is no "open straight to
ready" path; if insisted on, open draft → promote immediately → warn that checks/reviews haven't settled.

Loop-safety rationale: the cap and the caller flag together bound the cycle. The triage skills never call
finish-branch back; re-entry is driven only by finish-branch's own wake-ups re-polling. So the worst case
is 3 dispatch rounds, then a human takes over — never a runaway.

## Force-push policy

force-with-lease is acceptable on feature branches; it protects against stomping someone else's
push. Use it (never bare `--force`) in two scenarios only:

1. Branch rename after pre-flight (user accepted the rename-and-push offer).
2. User explicitly asked to rebase and push in the "branch up-to-date with base" pre-flight step.

**Never force-push to `main` or `master`.** This is the absolute rule from CLAUDE.md. finish-branch
operates on feature branches by design, but the hard block in the branch-convention section makes
this physically impossible anyway.

For any force-with-lease push, print the exact command before running it and wait for confirmation:
> About to run: `git push --force-with-lease origin MSP-7032/add-orchestrion`
> This will rewrite the remote branch. OK? (y/N)

## Anti-patterns

**Committing dangling changes.** The pre-flight dirty-tree check exists precisely because CLAUDE.md
prohibits silent commits. Never stage, stash, or commit on the user's behalf. If the tree is dirty,
stop and tell the user what to clean up.

**Opening a PR from main.** Hard block, no confirmation path. This is always wrong.

**AI-cheerleader PR bodies.** "This exciting new feature dramatically improves developer
productivity by…" — reject any generated text that evaluates the work instead of describing it.
Summary bullets should be factual and imperative: what was added/changed/removed.

**Scope-drift PRs.** If the diff contains files or changes outside the stated scope in spec.md,
call it out at the confirmation checkpoint. Don't silently let an oversized diff go to review.
> The diff includes changes in `packages/auth/` which are not mentioned in the spec. Intended?

**Swallowing verify-before-done failures.** If the gate failed and the user skipped it, the
draft-PR default and the body warning note are the only safety net. Do not pretend the gate passed.

**Routing through the finish/merge/keep/discard options menu.** finish-branch owns the open→watch→
dispatch→promote lifecycle, not a merge-vs-keep-vs-discard menu. Merging belongs to git/GitHub. Note
the distinction from dispatch: routing red checks to `ci-check-triage` and comments to
`pr-review-triage` is part of shepherding the PR to ready; offering the user a branch-disposition menu
is not. The former is the skill's job; the latter dilutes it.

**Fixing checks or comments inline during the watch.** Tempting once a failure is visible, but it
duplicates the triage skills and bypasses their approval gates. Always dispatch; the triage skills and
debug-loop own the fixing.

**Promoting while red, or looping forever.** Ready is earned — never `gh pr ready` with failing checks
or open threads (unless the user explicitly overrode the watch). And cap the watch→fix→re-check loop at
3 rounds; a failure that survives 3 rounds needs human judgment, not a 4th pass.

**Embedding `.claude-plans/` file paths in the PR body.** Those paths are gitignored and
meaningless to reviewers. Inline the content; don't reference the path.

## Composition

- **Caller:** verify-before-done completes successfully → hands off to finish-branch. Can also be
  invoked directly by the user after any green session.
- **Reads:** `.claude-plans/<slug>/verify.json`, `spec.md`, `handoff.md`, `plan.md`,
  `decisions.md`. All reads are optional — the skill degrades gracefully to git-log-based body
  generation when the workspace is absent.
- **Writes:** nothing to the repo or workspace. Side effects: `git push`, `gh pr create --draft`,
  `gh pr edit`, `gh pr ready`, `gh pr edit --add-reviewer`, and `ScheduleWakeup` for the watch.
- **Calls:** `ci-check-triage` (on red checks) and `pr-review-triage` (on unresolved comments) during
  the watch phase, each with `caller=finish-branch` + `PR_NUMBER`; `knowledge-capture` at pre-flight
  gate #6. finish-branch doesn't call verify-before-done — that's a deliberate boundary. verify and
  finish-branch are separate gates with separate failure modes (re-running verify is cheap; creating a
  PR is a visible external action). finish-branch dispatches to the triage skills but never fixes
  anything itself; the triage skills carry their own approval gates and delegate real fixes to
  debug-loop. The watch loop is bounded (3-round cap + caller flag) so the composition can't run away.

If `verify-before-done` or `debug-loop` aren't installed: mention it once if the gate artifact is
missing, then proceed per the user's explicit confirmation.

## Open questions to resolve before SKILL.md

1. **verify-before-done artifact contract.** This design assumes `verify.json` with `{timestamp,
   commit_sha, result}`. verify-before-done's DESIGN.md needs to commit to this schema. If the
   format differs, reconcile there.

2. **Should verify-before-done and finish-branch be merged?** Kept separate here for these reasons:
   verify runs many times (after every task in execute-plan, on demand), finish-branch runs once
   per PR; their inputs differ (working tree state vs git remote state); their failures have
   different reversibility (failed verify = fix and re-run, failed PR = public embarrassment).
   The boundary is real. But if dogfooding shows the transition is always immediate and the
   double-invocation is friction, revisiting the merge is reasonable.

3. **Convention detection for non-MSP, non-tylertech repos.** The `gh pr list` heuristic (≥ 60%
   prefix) needs a real threshold check. Too aggressive → noisy; too loose → convention is never
   applied. Revisit after one or two non-MSP uses.

4. **decisions.md top-3 selection.** Currently "top 3" means the three most recent entries. Should
   it be the three with the most reviewer conflict? Or the three that affected scope most? Punted
   until there's a real decisions.md to test against.

5. **Body update on push (not PR open).** If the user `git push`es new commits after the PR is
   open, should finish-branch offer to refresh the PR body? Currently: no — user invokes
   finish-branch explicitly. Note the watch loop *does* push (via triage) but only refreshes
   checks/threads, not the body. Revisit if the body drifts from the diff after triage rounds.

6. **Watch cadence + give-up window.** Default ~120–270s active polling, ~10 min bot-review give-up,
   3-round cap. All three are guesses pending dogfooding. Repos with slow integration suites or
   Copilot-on-ready-only configs may need different numbers. Candidate for caller-overridable params.

7. **Bot review on drafts.** Assumes automated reviewers (Copilot, CodeRabbit) run on draft PRs. Some
   org configs only review on ready — in which case the give-up window fires, the PR promotes, and the
   bot review arrives *after* ready, to be handled by a later `pr-review-triage` invocation. Acceptable
   degradation, but worth confirming against the user's actual repo settings during dogfooding.

8. **Auto vs interactive in the watch.** The dispatch to triage is gate-free because the triage skills
   gate themselves. But the watch runs across backgrounded wake-ups — if the user is away, the triage
   skills will stop at their approval gate and wait. That's correct (human-in-the-loop default) but
   means an unattended finish-branch can stall mid-loop. Confirm this is the desired behavior vs. an
   opt-in auto-approve for fully-unattended runs.
