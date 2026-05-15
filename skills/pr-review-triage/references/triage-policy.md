# Triage policy — pr-review-triage

Grading rubric, edge cases, and resolve policy. SKILL.md carries the operational flow; this file holds the detailed rules so SKILL.md stays readable.

## Grading rubric

Each comment is graded against: (1) the diff hunk it points to, (2) the active workspace's `spec.md` / `plan.md` / `decisions.md`, (3) repo conventions (lint config, CONTRIBUTING.md, style guides). Pick one verdict:

| Verdict | When |
|---|---|
| **fix** | Real, mechanical issue visible in the diff: bug, typo, missing null check, dead code, security issue, perf regression, broken assertion, incorrect docstring. Patch ≤ ~30 lines, single-file or tightly coupled. |
| **won't-fix: rejected by decisions** | Comment suggests an approach `decisions.md` explicitly considered and rejected. Cite the decision title. |
| **won't-fix: false positive** | Comment misreads the code. Name what it got wrong concretely (variable, function, control flow). |
| **won't-fix: style-only** | Pure style preference; no enforced lint rule or style guide for it. Trivial single-symbol renames can still be `fix`; broad renames are won't-fix. |
| **won't-fix: out of scope** | Comment requests work beyond the PR's stated scope (new feature, refactor of untouched code). |
| **answer** | Comment is a question, not a request. Draft a reply; no code change. |
| **escalate** | Substantive change: >30 lines, multi-file design, contradicts spec, or touches a load-bearing area. Don't auto-fix — recommend re-entering blueprint with the constraint. |

### Edge cases

- **Both style-only and false-positive** (e.g. rename request based on misreading): grade as `false positive` — more informative rationale.
- **Comment requests something the user explicitly opted into during blueprint discovery** (e.g. "we agreed to skip retries" in `handoff.md`): `won't-fix: rejected by decisions`, citing the handoff entry.
- **CodeRabbit-style top-level "walkthrough" or summary comments** (not actionable on any specific line): `answer` with no reply needed; mark "no action".

### Confidence tags

Every verdict gets: `high` (clear signal), `medium` (judgment call), `low` (could go either way). `low`-confidence verdicts are flagged for explicit user review even on batch-approve.

## Resolve policy

| Verdict | Bot author | Human author |
|---|---|---|
| fix | Reply + resolve | Reply, leave open |
| won't-fix: false positive | Reply + resolve | Reply, leave open |
| won't-fix: style-only | Reply + resolve | Reply, leave open |
| won't-fix: rejected by decisions | Reply, leave open | Reply, leave open |
| won't-fix: out of scope | Reply, leave open | Reply, leave open |
| answer | Reply, leave open | Reply, leave open |
| escalate | Post "Flagged for design review — handing back to spec." Leave open. | Same. |

**Rule:** Never resolve human-authored threads. Reviewers expect to resolve their own; we comment, they close.

## Bot detection

Tag each comment as `bot` when:
- Login ends in `[bot]` (e.g. `coderabbitai[bot]`), OR
- Login matches known bots: `copilot-pull-request-reviewer`, `coderabbitai`, `greptile-app`, `sourcery-ai`, `codex-bot`, OR
- GraphQL `author.__typename == "Bot"`.

The bot/human tag affects the resolve policy above, NOT the grading rubric — comments are graded on merit regardless of source.
