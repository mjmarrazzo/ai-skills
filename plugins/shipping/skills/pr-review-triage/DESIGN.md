# pr-review-triage — DESIGN

Lean design rationale for the skill. Operational form lives in `SKILL.md`.

## Purpose

After a PR is opened, automated reviewers (GitHub Copilot review, CodeRabbit, Codex connector, Greptile, Sourcery, etc.) — and humans — leave inline and conversation comments. The user does this triage by hand every PR: pull comments down, decide which are real, fix the legit ones, dismiss the noise with a rationale, comment back on the threads, resolve. That ritual is mechanical *except* for the grading step, which depends on knowing the plan and the load-bearing decisions. This skill automates the mechanics and applies the grading using the active blueprint workspace as context.

## Boundary

In scope:
- Pull all unresolved review comments (inline + conversation) for one PR.
- Grade each against `spec.md` / `plan.md` / `decisions.md` and the actual diff.
- Propose `fix` or `won't fix` per comment with a rationale.
- Get user approval on the table.
- Apply fixes, commit, push.
- Comment back on each thread (link to fix SHA or won't-fix rationale).
- Resolve threads the bot authored (or the user explicitly authorizes).

Out of scope:
- Generating *new* code or features beyond what comments request — fixes are surgical to the comment.
- Merging, re-requesting review, dismissing review submissions.
- Replying to ambient PR discussion (top-level conversation comments unattached to threads, unless the user invokes us on them explicitly).
- Anything when no PR is open — surface and stop.

## A. Locating the PR

Resolution order:
1. Caller passes `PR_NUMBER` or `PR_URL` via context parameter — use verbatim.
2. User mentions a number or URL in the invoking message — extract and use.
3. Default: current branch's PR via `gh pr view --json url,number,state,headRefName`.
4. No PR open on current branch → stop with: "No open PR found on branch `<name>`. Push the branch and open a PR first (or pass the PR number)."

PR state check: if state is `MERGED` or `CLOSED`, stop. Re-opening or commenting on a merged PR is rarely what the user wants; surface and let them confirm explicitly.

## B. Fetching comments

Two REST endpoints cover the comment surface:
- `gh api repos/{owner}/{repo}/pulls/{num}/comments` — inline (line-anchored review) comments.
- `gh api repos/{owner}/{repo}/issues/{num}/comments` — PR conversation (issue-style) comments.

Bots use either. Need both.

REST does *not* expose thread-level `isResolved`. To filter to unresolved threads we use GraphQL:

```graphql
query($owner:String!, $name:String!, $num:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$num) {
      reviewThreads(first:100) {
        nodes {
          id isResolved isOutdated
          comments(first:50) {
            nodes { id databaseId author { login } body path line originalLine diffHunk url }
          }
        }
      }
    }
  }
}
```

Stash the GraphQL thread `id` per inline comment — we need it later for `resolveReviewThread`. PR-conversation comments don't have thread IDs (they're not threaded on GitHub); they can be replied to but not resolved.

**Outdated comments** (`isOutdated: true` or REST `position: null`) are surfaced for user awareness but **not auto-fixed**. The line they reference has been modified since the comment was made; the comment may be stale.

## C. Bot vs human authors

Bot signals:
- Login ends in `[bot]` (e.g. `github-actions[bot]`, `coderabbitai[bot]`).
- Known logins: `copilot-pull-request-reviewer`, `coderabbitai`, `greptile-app`, `sourcery-ai`, `codex-bot`.
- GraphQL `author.__typename == "Bot"`.

Behavior decision: **grade bot and human comments by the same rubric**. The whole point is that comments get graded on merit, not source. But the summary table tags author type so the user can scan ("3 bot, 2 human, 1 unknown") and calibrate expectations — bot reviewers produce more false positives, so a high won't-fix rate on bot comments is normal and not a sign the skill misgraded.

Auto-resolve policy differs by author (see §J): bot threads resolved on fix; human threads left open by default.

## D. Grading rubric

This is the load-bearing logic. Each comment is graded against:
1. The diff hunk it points to (does the code actually have the issue claimed?).
2. The active workspace's `spec.md` / `plan.md` / `decisions.md` (does the comment contradict an explicit decision?).
3. Repo conventions (lint config, style guides, CONTRIBUTING.md if present).

Verdicts and triggers:

| Verdict | Trigger |
|---|---|
| **fix** | Comment names a real issue visible in the diff: bug, typo, dead code, missing null check, security issue, perf regression, broken test, incorrect docstring. The fix is mechanical (≤ ~30 lines, single-file or tightly coupled multi-file). |
| **won't-fix: rejected by decisions** | Comment suggests an approach the workspace's `decisions.md` already considered and rejected. Cite the decision title. |
| **won't-fix: false positive** | Comment misreads the code. Explain what it got wrong (concretely — name the variable / function / control flow it misunderstood). |
| **won't-fix: style-only, no enforced standard** | Comment is purely stylistic (variable rename, comment phrasing, formatting preference) and the repo has no lint rule or style guide enforcing it. Trivial fixes (rename one variable) can still be fix; widespread renames are won't-fix. |
| **won't-fix: out of scope** | Comment requests work that exceeds the PR's stated scope (new feature, refactor of untouched code). |
| **answer (no fix)** | Comment is a question, not a request. Draft a reply; no code change. |
| **escalate** | Comment requests a substantive change: >30 lines, multi-file design change, contradicts spec, or touches an area the spec marked load-bearing. Don't auto-fix; tell the user this warrants re-entering blueprint with a new constraint. |

Edge: a comment that's *both* style-only and false-positive (it asked for a rename based on misreading) is graded false-positive — that's the more informative rationale.

Edge: a comment that requests a fix the user explicitly opted into via blueprint discovery (e.g. "we agreed to skip retries") is won't-fix, citing the discovery answer captured in `handoff.md` or `decisions.md`.

Confidence tagging: each verdict gets a confidence tag (`high` / `medium` / `low`) shown in the table. `low` confidence verdicts are surfaced for explicit user review even if the user batch-approves the rest.

## E. Plan-context loading

Use the canonical active-workspace resolution algorithm (decisions.md):
1. If `WORKSPACE_PATH` passed by caller, use it.
2. Enumerate `.claude-plans/*/`, filter to dirs containing `plan.md` or `spec.md`.
3. One match → use. Multiple → prefer slug matching current branch's ticket key, tiebreak by `plan.md` mtime.
4. Zero → ad-hoc mode.

In ad-hoc mode (no workspace): grade on diff + repo conventions alone. Mark the user-facing summary with: "_No blueprint workspace found — verdicts are based on diff and repo conventions only; rationale will be less confident._" Lower the default confidence on all verdicts by one notch.

Files loaded when workspace is present: `handoff.md`, `spec.md`, `plan.md`, `decisions.md` (each optional — degrade gracefully on absence).

## F. Fix proposal format

For each `fix` verdict:

```
[fix] <file>:<line> by <author> — <short summary of comment>
  Action: <one-line description of the change>
  Patch:
    <inline unified diff if ≤ 20 lines>
    OR
    <file>: +X -Y  (full patch suppressed; will apply on approval)
```

The 20-line threshold balances reviewability against summary table noise. Above 20 lines, the user trusts the verdict, sees the file/range, and inspects the actual diff at commit time.

## G. Won't-fix rationale format

```
[won't fix: <category>] <file>:<line> by <author> — <short summary of comment>
  Why: <one-line rationale>
  Reference: <decisions.md entry title> | <spec.md section> | <none — false positive>
```

Tone: professional, neutral, factual. Not defensive ("you're wrong because…"). Not apologetic ("sorry, we…"). The rationale is what gets posted back as the thread reply, so it has to read well to a human reviewer who may push back.

## H. User approval

Single table, presented as the first user-facing artifact:

```
PR #1234 — 12 unresolved comments (8 bot, 4 human)

  # | Author          | File:Line        | Verdict          | Conf   | Action
 ---|-----------------|------------------|------------------|--------|------------------
  1 | copilot[bot]    | auth.go:42       | fix              | high   | null check
  2 | copilot[bot]    | auth.go:88       | won't-fix: false | high   | comment misreads control flow
  3 | coderabbit[bot] | router.go:15     | won't-fix: dec.  | high   | rejected: "no retries" (decisions.md)
  4 | alice           | mapper.go:201    | escalate         | medium | design-level — re-enter blueprint
  5 | greptile        | cache.go:33      | fix              | low    | nit: error message capitalization
  ...

Choose:
  (a) Approve all
  (b) Approve subset — type comma-separated numbers (e.g. 1,3,5)
  (c) Override a verdict — "override 4: won't-fix: out of scope"
  (d) Skip — I'll handle it manually
```

When the table is small (≤ 4 verdicts), use `AskUserQuestion` with one question per verdict (`fix` / `won't-fix` / `skip`). Above 4, inline table + free-form confirmation — `AskUserQuestion` has a per-call option cap and stops being ergonomic past a handful.

The skill **always** stops here. Never apply fixes without explicit approval. Even on `(a) Approve all`, restate "applying N fixes and posting M won't-fix replies — proceed?" for one final confirm.

## I. Execution

After approval, in order:

1. **Apply fixes.** One verdict at a time. Use Edit on the file(s). Track applied / failed via TodoWrite.
2. **Verify if available.** If `verify-before-done` is installed, hand off with `caller=pr-review-triage` once all fixes applied. If any verify check fails, hand off to `debug-loop` with `caller=pr-review-triage` and the failure bundle.
3. **Commit.** Default: single commit, message `MSP-XXXX: address PR review feedback` (or `Address PR review feedback` for non-MSP repos), body listing each fix as `- <file>:<line>: <one-line>`. Offer per-fix commits at approval time if the user wants finer history; default to single because that's what humans do.
4. **Push.** `git push origin <branch>` — no force, no rebase. New commits append to the branch as fresh history; that's how review-feedback rounds work.

If the user rejected the verify gate or it isn't installed: commit and push anyway, but note in the post-resolve summary that verify wasn't run.

MSP detection (same triangulation as other skills): remote URL contains `nicusa`/`tylertech`, branch matches `^MSP-\d+/`, or `git config user.email` ends `@tylertech.com`. Any one match = MSP, prefix the commit.

## J. Comment-back and resolve

Per applied fix, on the thread:
1. Post a reply: `Fixed in <short-sha>. <one-line description>.` (Plain prose. No emoji. No "Thanks!" — neutral.)
2. Resolve the thread via GraphQL `resolveReviewThread(input: {threadId: $id})` **iff** the comment author is a bot. For human authors: post the reply, leave the thread open. Reviewers expect to resolve their own threads.

Per won't-fix:
1. Post the rationale (from §G) as a reply.
2. Resolve **iff**: bot author AND verdict is `won't-fix: false positive` OR `won't-fix: style-only`. Bot threads on false positives and style are noise; resolving them is correct and not contested.
3. Do NOT resolve when verdict is `won't-fix: rejected by decisions` or `won't-fix: out of scope` — those merit a human acknowledging the rationale before closing.
4. Never resolve human-authored threads. Period.

Per `answer`: post the reply, don't resolve.

Per `escalate`: post `Flagged for design review — handing back to spec.` Don't resolve. Surface to user that they should re-enter blueprint with this constraint.

GraphQL mutations and exact REST calls live in `references/graphql-queries.md` so the SKILL.md doesn't bloat.

Outdated comments (`position: null` or `isOutdated: true`): never auto-act. Surface in a separate "Stale (line moved)" subtable for user review. The user can manually direct triage on those.

## K. Composition

- **Caller flag:** when invoking siblings (verify-before-done, debug-loop, blueprint), pass `caller=pr-review-triage` as a one-line context parameter. The cycle-prevention convention is in decisions.md.
- **Upstream from finish-branch:** finish-branch can emit a one-line trailing suggestion ("Bots will leave review comments in the next few minutes — run `pr-review-triage` once they've settled.") This is *optional and does not modify finish-branch's SKILL.md.* The composition contract is documented here; finish-branch can adopt it on its next edit. No code coupling either direction.
- **Escalation to blueprint:** when one or more comments are graded `escalate`, the post-resolve summary tells the user: "Comment #N is design-level — recommend running `blueprint` with the constraint: <one-line constraint extracted from the comment>." Do not auto-invoke blueprint; the user chooses.
- **Failure to debug-loop:** if applying a fix produces a verify failure, hand off to debug-loop with `caller=pr-review-triage` and a failure bundle (file, error output, the comment that prompted the fix). debug-loop's anti-cycle guard means it won't loop back here.
- **Sibling absent:** verify-before-done not installed → commit + push without verify, note in summary. debug-loop not installed → surface failure to user and stop before commit. blueprint not installed → still escalate via summary text (it doesn't need to invoke anything).

## L. Anti-patterns

These are the failure modes specifically for this skill.

- **Applying every bot comment uncritically.** The whole point is grading. A skill that fixes everything Copilot says is a regression from doing it by hand — the user already filters mentally; we make that filter explicit and reviewable.
- **Won't-fix without a rationale.** Every won't-fix posts a reply. A blank "won't fix" is rude to a human reviewer and unhelpful to a bot review log. The rationale format in §G is mandatory.
- **Auto-resolving human threads.** Reviewers expect to resolve their own. We comment, we don't close.
- **Force-pushing over review feedback.** Reviewer history is the audit trail. New commits go on top. `--force-with-lease` only when rebasing was a separate decision (and we don't make that decision here).
- **Acting on stale comments.** `position: null` or `isOutdated: true` means the anchor line is gone or moved. Don't guess where the comment "would have applied" — surface it, let the user direct.
- **Triggering on a not-yet-reviewed PR.** If `unresolvedReviewThreads + issue_comments` is empty, say so and stop — don't manufacture work.
- **Treating questions as fix requests.** A comment that ends in `?` is usually a question; auto-fixing produces a non-sequitur reply. Grade as `answer`, draft text, don't touch code.
- **Replying with sycophancy.** "Great catch!" / "You're right, fixing now!" trains the reviewer to expect noise. Reply with content: what we did, where it's committed.

## Open questions

- **Per-fix vs single commit default.** Picked single (matches human behavior, smaller history). Some teams prefer per-fix for review traceability; revisit after dogfooding.
- **Re-running on the same PR after new comments.** Currently the skill is one-shot per invocation. If the user re-runs after another round of bot comments, we re-fetch all *unresolved* threads — already-resolved ones aren't re-grading. Should be safe; flag if dogfooding shows otherwise.
- **CodeRabbit "summary" comments.** CodeRabbit posts a top-level summary comment that's not actionable. Currently graded `answer` (no fix), no reply needed. Could be filtered before grading; depends on whether other bots have similar shapes.
- **Confidence threshold for auto-approve.** Right now `(a) Approve all` approves every verdict regardless of confidence. Could change to "approve all `high` confidence, leave `medium`/`low` for explicit review." Punt until we see real noise rates.
- **GitHub Enterprise / SAML.** `gh` handles auth uniformly; haven't tested against GHE. Assume it works until a user reports otherwise.
