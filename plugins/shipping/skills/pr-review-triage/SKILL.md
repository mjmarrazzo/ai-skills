---
name: pr-review-triage
description: Use this skill whenever the user says "triage the copilot review", "handle the PR comments", "respond to copilot", "respond to coderabbit", "respond to codex", "respond to codereview", "address the review feedback", "fix the review comments", "resolve the review comments", "handle the PR feedback", "process the bot review", "go through the PR comments", or "look at the PR review". Also trigger after finish-branch opens a PR and the user circles back saying "the bots commented" or "review is in". Pulls unresolved review threads via gh, grades each comment against the active spec/plan/decisions, proposes fix or won't-fix per comment, gets user approval, applies fixes, commits, and replies on each thread linking the fix SHA. Skip only on explicit opt-out: "I'll handle the comments myself", "just ignore the bots", "no triage", or a single trivial comment the user already named.
---

# pr-review-triage

Turn the unresolved review queue on a PR into a single approvable table, then apply the approved fixes, comment back with the fix SHA, and resolve the bot threads — without the user re-reading every Copilot suggestion.

**Announce at start:** "Using pr-review-triage to pull unresolved review comments on PR #`<num>` and grade them against the active plan."

## When to trigger

Trigger phrases and opt-outs are in the frontmatter. One additional case: user names a single specific comment ("just fix the typo on line 42") — handle that one directly; skip the full flow.

**Scope:** triage unresolved review threads on one PR. Not in scope: merging, re-requesting review, dismissing review submissions, generating new code beyond what comments request.

## In-session tracking

Use `TodoWrite` to track:
1. Locate PR
2. Fetch comments (REST inline + REST conversation + GraphQL threads)
3. Load plan context
4. Grade each comment
5. Present table + get approval
6. Apply fixes (one item per approved fix)
7. Commit + push
8. Reply + resolve threads (one item per thread)

## Pre-flight

### 1. Locate the PR

Resolution order:
1. Caller passes `PR_NUMBER` or `PR_URL` — use verbatim.
2. User's message contains a PR number or URL — extract.
3. Default: `gh pr view --json url,number,state,headRefName,baseRefName`.

If no PR open on current branch:

> No open PR found on branch `<name>`. Push the branch and open the PR first (or pass the PR number).

Stop.

If PR state is `MERGED` or `CLOSED`:

> PR #`<num>` is `<state>`. Triaging review feedback on a closed PR is unusual — confirm you want to proceed.

Wait for confirmation before continuing.

### 2. Verify gh availability

Run `which gh && gh auth status` before any API call. On failure surface the fix (install / `gh auth login`) and stop. Never fall back to raw `curl` against the GitHub API — auth handling diverges and credentials leak.

### 3. Fetch comments

Two REST endpoints plus one GraphQL query:

```bash
# Inline (line-anchored) review comments
gh api "repos/$OWNER/$REPO/pulls/$NUM/comments" --paginate

# Conversation (issue-style) comments on the PR
gh api "repos/$OWNER/$REPO/issues/$NUM/comments" --paginate

# Thread structure + isResolved (REST doesn't expose this cleanly)
gh api graphql -f query='...'  # see references/graphql-queries.md
```

Merge results into a single list with: `id`, `databaseId`, `threadId` (inline only), `author.login`, `author.type` (Bot|User), `path`, `line`, `originalLine`, `body`, `diffHunk`, `url`, `isResolved`, `isOutdated` (inline only).

Filter to `isResolved == false`. If after filtering the list is empty:

> No unresolved review threads on PR #`<num>`. Nothing to triage.

Stop.

### 4. Classify by author

Tag each comment `bot` or `human`. Bot signals and full detection rules: see `references/triage-policy.md § Bot detection`. The tag affects resolve policy only — grading is identical for both.

### 5. Separate stale comments

Comments with `position: null` (REST) or `isOutdated: true` (GraphQL) are stale — the line they anchor to has been modified. Hold them in a separate "Stale (line moved)" subtable. Never auto-fix stale comments; surface to user for manual direction.

## Plan-context loading

Apply the canonical active-workspace resolution algorithm:

1. If `WORKSPACE_PATH` passed as a context parameter, use it.
2. Enumerate `.claude-plans/*/`, filter to dirs containing `plan.md` or `spec.md`.
3. One match → use. Multiple → prefer slug containing the current branch's ticket key; tiebreak by `plan.md` mtime.
4. Zero matches → ad-hoc mode.

When workspace present, load (each optional, degrade on absence): `handoff.md`, `spec.md`, `plan.md`, `decisions.md`.

In ad-hoc mode, surface this in the table header:

> _No blueprint workspace found — verdicts based on diff + repo conventions only; rationale will be less confident._

Lower default confidence one notch on every verdict in ad-hoc mode.

## Grading rubric

For each comment, grade against: (1) the diff hunk, (2) workspace files, (3) repo conventions. Full rubric, edge cases, confidence rules, and resolve policy: `references/triage-policy.md`.

Summary of verdicts:

| Verdict | When |
|---|---|
| **fix** | Real, mechanical issue in the diff. Patch ≤ ~30 lines. |
| **won't-fix: rejected by decisions** | Approach already rejected in `decisions.md`. Cite the title. |
| **won't-fix: false positive** | Comment misreads the code. Name what it got wrong. |
| **won't-fix: style-only** | Pure style preference; no enforced rule. |
| **won't-fix: out of scope** | Requests work beyond the PR's scope. |
| **answer** | Question, not a request. Draft reply; no code change. |
| **escalate** | >30 lines, multi-file design, contradicts spec. Recommend blueprint. |

Tag each verdict `high` / `medium` / `low` confidence. `low`-confidence verdicts get flagged for explicit user review even on batch approve.

## Fix proposal format

Per `fix` verdict:

```
[fix] <file>:<line> by <author> — <one-line summary of comment>
  Action: <one-line description of the change>
  Patch:
    <inline unified diff if ≤ 20 lines>
    OR
    <file>: +X -Y  (full patch applied on approval)
```

## Won't-fix rationale format

Per won't-fix verdict (this exact text is what gets posted as the thread reply):

```
[won't fix: <category>] <file>:<line> by <author> — <one-line summary of comment>
  Why: <one-line rationale, neutral and factual>
  Reference: <decisions.md entry title | spec.md section | none — false positive>
```

Tone: professional, not defensive, not apologetic. No emoji. No "Thanks for the suggestion!". The reply has to read well to a human reviewer who may push back on it.

## User-approval gate

Present a single table:

```
PR #1234 — 12 unresolved comments (8 bot, 4 human)
Workspace: .claude-plans/2026-05-14-MSP-7032-orchestrion/

  # | Author          | File:Line       | Verdict          | Conf   | Action
 ---|-----------------|-----------------|------------------|--------|----------------------
  1 | copilot[bot]    | auth.go:42      | fix              | high   | null check
  2 | copilot[bot]    | auth.go:88      | won't-fix: false | high   | misreads control flow
  3 | coderabbit[bot] | router.go:15    | won't-fix: dec.  | high   | rejected: "no retries"
  4 | alice           | mapper.go:201   | escalate         | medium | design-level
  5 | greptile        | cache.go:33     | fix              | low    | nit: error capitalization
  ...

Stale (line moved, not auto-actioned):
  S1 | copilot[bot]    | (removed) :77   | review manually  | -      | -

Choose:
  (a) Approve all
  (b) Approve subset (comma-separated numbers): e.g. 1,3,5
  (c) Override a verdict: "override 4: won't-fix: out of scope"
  (d) Skip — I'll handle manually
```

When verdict count is ≤ 4: use `AskUserQuestion` with one question per verdict (`fix`/`won't-fix`/`skip`).

When verdict count is > 4: inline table above + free-form confirmation. `AskUserQuestion` doesn't scale to that many options ergonomically.

**Always stop here. Never apply fixes without explicit approval.** Even on `(a) Approve all`, restate the count and confirm:

> Applying `<N>` fixes, posting `<M>` won't-fix replies, replying to `<K>` questions. Proceed?

Wait for `y` / "yes" / "go" / "do it". Anything else: re-prompt or stop.

## Execution

After approval, in order:

### 1. Apply fixes

One verdict at a time. Use `Edit` for the file change. Track each fix as a TodoWrite item; mark done as applied.

If a fix can't apply cleanly (the surrounding context the comment referenced has moved): mark that fix as failed, surface it to the user, continue with the rest. Don't guess.

### 2. Run verify-before-done if installed

Sibling-installed check (per composition-skills decisions.md). If installed: hand off with `caller=pr-review-triage`.
- `pass` → continue.
- `fail` → hand off to `debug-loop` with `caller=pr-review-triage` + failure bundle (file, command, output, triggering comment).

If not installed: continue, note in summary.

### 3. Commit

**MSP detection:** triangulated per composition-skills decisions.md. Any match = MSP; extract ticket key from branch.

**Commit policy:** single commit by default — clean review history. Per-fix commits offered at approval time.

Default message:
- MSP: `MSP-XXXX: address PR review feedback`
- Non-MSP: `Address PR review feedback`

Body lists one line per applied fix: `- <file>:<line>: <summary>`.

### 4. Push

`git push origin <branch>`. Plain push, no force, no rebase. New commits append to the branch; that's the audit trail for the review round.

If the push is rejected (someone pushed to the remote branch since): surface, do not force. Tell the user to pull and re-run.

## Comment-back and resolve threads

After push completes (SHA must be on remote before replying):

**Get fix SHA:** `git rev-parse --short HEAD` (or per-fix SHA if commits were split).

**Reply on inline thread:** REST `POST /pulls/$NUM/comments/$COMMENT_ID/replies`, body `"Fixed in $SHORT_SHA. <description>."`.

**Reply on conversation comment:** REST `POST /issues/$NUM/comments`, body `"Re: @$ORIG_AUTHOR — fixed in $SHORT_SHA. <description>."` (no thread structure; can't be resolved).

**Resolve thread:** GraphQL `resolveReviewThread(input:{threadId:$id})`. Full invocations in `references/graphql-queries.md`.

**Resolve policy:** full table in `references/triage-policy.md`. Key rule: **never resolve human-authored threads** — reply and leave open. Bot `fix` and bot `won't-fix: false positive` / `won't-fix: style-only` threads are resolved; `rejected by decisions` and `out of scope` are left open regardless of author.

## Post-resolve summary

After all replies and resolves, surface to the user:

```
pr-review-triage — done
─────────────────────────
PR #1234 — branch MSP-7032/add-orchestrion

Applied: 5 fixes — commit a1b2c3d (pushed to origin)
Replied: 4 won't-fix, 1 answer, 1 escalate
Threads resolved: 7 bot threads
Threads left open: 3 (1 human, 2 won't-fix awaiting reviewer)

Escalations (re-spec recommended):
  - Comment #4 (mapper.go:201, alice) — design-level change to the mapping contract.
    Suggest: run blueprint with the constraint: "<one-line constraint>"

Skipped (stale, line moved): 1
  - S1 (auth.go originally:77, copilot[bot]) — review manually.

Verify: passed against HEAD a1b2c3d
```

If verify wasn't run, swap that last line for `Verify: not run (verify-before-done not installed)` or `Verify: skipped at user request`.

## Composition

- **Called by:** the user directly. `finish-branch` may suggest it as a one-line tail message after PR creation (one-directional; no coupling).
- **Calls:** `verify-before-done` (after fixes) with `caller=pr-review-triage`; `debug-loop` (on verify failure) with `caller=pr-review-triage` + failure bundle. `blueprint` is **never auto-invoked** — escalations are text recommendations only.
- **Reads:** `handoff.md`, `spec.md`, `plan.md`, `decisions.md` (all optional); PR diff + thread state via `gh`.
- **Writes:** code edits (per approved fix); git commit(s); GitHub replies + thread resolves via `gh api`.
- **Caller flag:** pass `caller=pr-review-triage` to all sibling invocations (cycle-prevention convention per composition-skills decisions.md).
- **Sibling absent:** verify-before-done → commit without verify, note in summary. debug-loop → surface failure and stop. blueprint → escalations still emitted as text.

## Anti-patterns

These are the failure modes specifically for this skill.

**Applying every bot comment uncritically**
> Example: Copilot suggests 12 changes; skill applies all 12 and commits.
> The whole point of this skill is grading. A skill that fixes everything Copilot says is a regression — the user already filters mentally; we make the filter explicit and reviewable.
> Correct: every comment gets a verdict with a rationale; the user approves the table.

**Won't-fix without rationale**
> Example: Posting "Won't fix." with no explanation on a thread.
> Rude to humans, unhelpful in the bot's review log. Every won't-fix has the §Won't-fix rationale format applied.
> Correct: post the categorized rationale with reference to decisions/spec/diff.

**Auto-resolving human threads**
> Example: Alice left a comment; skill applies a fix and resolves her thread.
> Reviewers expect to resolve their own threads — closing on their behalf signals "I decided this is done" and skips their re-review.
> Correct: reply with the fix SHA; leave the thread open for Alice.

**Force-pushing over review-feedback commits**
> Example: Squash and force-push to consolidate the original work with the review fixes.
> The reviewer's history of "here's what I asked for, here's what got fixed" is the audit trail. Force-push erases it.
> Correct: append commits. Squashing happens at merge time, on GitHub, not from this skill.

**Acting on stale comments**
> Example: Comment points to line 77 but the file's been edited and line 77 is now blank. Skill guesses where the comment "would have applied" and fixes a different line.
> The anchor is gone. Any guess is unverifiable. Surface and stop on this one.
> Correct: stale comments go in the "Stale (line moved)" subtable for manual user direction.

**Treating questions as fix requests**
> Example: Reviewer asks "Why isn't this using the cached client?" — skill changes the code to use the cached client.
> Questions are not requests. Auto-fixing produces non-sequitur replies and may make a change the reviewer didn't actually want.
> Correct: grade as `answer`; draft a reply; touch no code.

**Sycophantic replies**
> Example: "Great catch! Thanks for spotting this!" as the reply body.
> Trains the reviewer to expect noise; degrades the signal of substantive replies. Bots especially don't need to be thanked.
> Correct: reply with content — what was changed, where it's committed. Or for won't-fix, the rationale. That's it.

**Triggering on a PR with no unresolved threads**
> Example: User says "handle the PR comments" — skill happily fetches an empty list and starts grading nothing.
> Surface "No unresolved review threads" and stop. Don't manufacture work.

**Verdicts without confidence tags**
> Example: All 12 comments graded with no confidence indicator.
> The user can't tell which verdicts are slam-dunks vs judgment calls. The whole approval gate becomes "trust the skill or read every diff."
> Correct: every verdict tagged `high`/`medium`/`low`; `low`-confidence ones get flagged for explicit user review even on batch approval.

## Open questions

1. **Per-fix vs single commit default.** Chose single — matches human behavior, cleaner history. Per-fix offered at approval. Revisit if dogfooding shows reviewers prefer the granularity.
2. **Re-running on the same PR after a new round of bot comments.** Skill is one-shot per invocation; re-running fetches all currently-unresolved threads. Should be safe — resolved threads aren't re-graded. Flag if dogfooding produces surprises.
3. **CodeRabbit "walkthrough" / summary comments.** Currently graded as `answer` with no action. Could be filtered before grading once we see the shape of other bots' summary outputs.
4. **Auto-approve threshold.** `(a) Approve all` currently approves every verdict regardless of confidence. Could change to "approve all high, leave medium/low for review." Punt until real noise rates are observed.
5. **GitHub Enterprise / SAML.** `gh` handles auth uniformly; not tested against GHE. Assume working until reported otherwise.
