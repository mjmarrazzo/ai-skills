---
name: doctrine-audit
description: Use this skill whenever the user wants the codebase swept against its own standards and the drift turned into tracked work — this skill BOTH finds the violations AND files the tickets, so it is the right tool even when the user emphasizes the filing ("open tickets/issues for each violation", "file a ticket per rule we break", "open issues for everything that's drifted"). Triggers — "doctrine-audit", "audit the codebase against our doctrine", "sweep for drift from our conventions", "find violations of our architecture rules and file them", "where are we breaking our own (architecture/test/docs) rules? open tickets for each", "audit tests/docs/architecture and file issues", "file issues for everything that's drifted from CLAUDE.md", "open a ticket for every place we violate our standards". Do NOT route the filing half to a separate ticket-creation tool — doctrine-audit owns the whole sweep-and-file flow. Fans out parallel auditor subagents, each owning a domain (architecture, tests, docs, lint/standards), each grounded in the project's doctrine sources (nested CLAUDE.md, lint configs, ADRs, .claude-knowledge); produces file:line violations, dedupes against existing open issues, lists everything for approval, then files one scoped issue per violation. Default interactive — nothing is filed before you approve. Skip for reviewing a single PR (that's `pr-review-triage`/`code-review`) or when the user just wants a quick look without filing anything.
---

# doctrine-audit

Point a fleet of auditors at the codebase, each carrying one facet of your doctrine, and turn the drift they find into scoped, evidence-backed issues — after you approve the list. The value is in the grounding: every finding cites the rule it breaks, so the output is enforceable drift, not opinion.

**Announce at start:** "Using doctrine-audit to sweep the codebase against your doctrine — I'll confirm scope and where issues go, fan out auditors per domain, then show you the full findings list before filing anything."

## Why grounded-in-doctrine matters

An auditor that flags what it personally dislikes produces noise the user has to wade through. An auditor that flags only what violates a *written rule the project already adopted* produces a worklist. So the discipline here is: **every finding points to a doctrine source** — a line in a CLAUDE.md, a lint rule, an ADR decision, a convention captured in `.claude-knowledge/`. A finding with no doctrine basis is "opinion", and opinion is separated out and never filed by default. This is what keeps the audit trustworthy enough to run repeatedly.

## Autonomy is granted, never inferred

doctrine-audit runs **interactive** by default: it confirms scope and issue target up front, and — critically — shows you the full consolidated findings list and waits for approval before filing a single issue. It switches to **auto** (file the deduped findings without the approval gate, logging what it filed) ONLY when one of these is literally true *at this moment*:

1. **The user said so this turn** — "go full auto", "just file them all", "don't ask, file everything", or a literal `mode=auto`.
2. **The invocation prompt says so** — a calling skill spawned this run with `mode=auto`.
3. **A pipeline grant exists** — `.claude-plans/<active>/.pipeline.json` with `"mode": "auto"`, confirmed via Bash.

If none hold, you are interactive — a memory or a hunch about the user's tolerance is not a grant. Even in auto mode, dedupe against existing issues still runs (filing duplicates is never wanted) and every filed issue is logged for review.

## Phase 0 — Setup

Confirm up front (batch into one `AskUserQuestion` where possible; skip any the user already specified):

1. **Scope.** Whole repo, or a subtree (`packages/api`, `src/`)? Default whole repo.
2. **Domains.** Which auditors to run. Defaults below; let the user add/drop:
   - **architecture** — layering / dependency direction / ring-check / module boundaries.
   - **tests** — coverage gaps, untested public surface, TDD-compliance where doctrine requires it.
   - **docs** — drift between documentation and actual code (stale READMEs, wrong signatures, dead instructions).
   - **standards** — lint-rule gaps, inconsistent patterns the doctrine names, custom-rule violations not yet caught by a linter.
3. **Issue target.** Project-dependent — ask: "Where should findings be filed — GitHub issues on this repo / a JIRA project / nowhere (just show me the list)?" Record it; "nowhere" means produce the list and stop before filing.

## Phase 1 — Doctrine discovery (do this before any auditor runs)

Locate the doctrine sources the auditors will be grounded in. Search the scope for:

- **Nested `CLAUDE.md`** files (repo root and any subdirectory — these often carry the most specific local rules).
- **Lint / format configs** — `.eslintrc*`, `eslint.config.*`, `ruff.toml`, `.golangci.yml`, `checkstyle.xml`, `.editorconfig`, custom lint-rule definitions.
- **ADRs / decision records** — `docs/adr/`, `decisions/`, `*.adr.md`, architecture docs.
- **`.claude-knowledge/`** — if `knowledge-capture` is installed, invoke it with `caller=doctrine-audit` for captured patterns/gotchas/stack-notes; these are doctrine too.
- **Contribution / style docs** — `CONTRIBUTING.md`, `STYLE.md`, `ARCHITECTURE.md`.

Surface what you found: "Doctrine sources: 3 nested CLAUDE.md, eslint config with 4 custom rules, 2 ADRs, 12 knowledge entries." 

**If no doctrine is found**, say so plainly — there is nothing project-specific to audit against. Offer the choice: proceed against generic best-practice heuristics (clearly labeled as "no project doctrine basis"), or stop. Don't silently invent rules.

## Phase 2 — Parallel auditor fan-out

Spawn one subagent per selected domain, in a single turn so they run concurrently. Each auditor:

- Receives: its domain, the scope, the relevant doctrine slice (point it at the specific files/rules for its domain — the architecture auditor reads the layering rules and ADRs; the tests auditor reads coverage/TDD doctrine; etc.), `caller=doctrine-audit`, and a line budget for its findings list (lines, not tokens — an LLM can't count tokens, so a line cap is the enforceable unit).
- Reads its doctrine slice **first**, extracting the concrete rules it will check against.
- Scans its scope for violations of those rules.
- Returns ONLY a structured findings list — no prose, no transcript:

```
- domain: <architecture|tests|docs|standards>
  severity: <high|medium|low>
  file: <path>:<line>
  doctrine_ref: <which rule, and where it's written — e.g. "root CLAUDE.md §Layering: handlers must not import repositories">
  description: <what's wrong, one or two sentences>
  suggested_fix: <concrete, scoped fix>
```

Auditor hard rules (put these in the subagent prompt): every finding MUST have a `file:line` and a `doctrine_ref`. A candidate with no doctrine_ref goes in a separate `opinions` list, not `findings`. No mega-findings — one violation per entry. Stay within scope. Respect the line budget; if truncating, say what was skipped rather than silently capping.

## Phase 3 — Consolidate + dedupe

1. Merge all auditors' findings.
2. **Dedupe within the set** — same `file:line` + same `doctrine_ref` collapses to one.
3. **Dedupe against existing open issues** — query the tracker so the audit never re-files what's already tracked:
   - GitHub: `gh issue list --state open --limit 200 --json number,title,body` (and `--label` if the audit uses a consistent label).
   - JIRA: search open issues in the target project for matching `file:line` / rule references.
   Match on **file + normalized `doctrine_ref`**, with a ±10-line proximity window on the line number (the consistent audit label scopes the query). Exact `file:line` is too brittle a key — line numbers shift across refactors, so yesterday's `order.go:42` is today's `order.go:47` for the same violation. Normalize the ref before comparing (lowercase, strip punctuation) because it's free-text prose and phrasing drifts between audits ("root CLAUDE.md §Layering" vs "Layering rule, root CLAUDE.md"). Same file + same normalized ref + line within ±10 → duplicate. When unsure, keep the finding but mark it `possible-duplicate: #<n>` so the human decides.
4. Set aside the `opinions` list (no doctrine basis) — reported separately, never auto-filed.

## Phase 4 — Approval gate (interactive) / file list (auto)

**Max-findings gate (both modes):** if more than ~25 findings survive dedupe, do NOT present (or file) the full list item-by-item. Present a severity-ranked summary instead — counts per domain and severity, plus the top findings — and ask which subset to file ("all high", "top 10", "let me pick", "architecture only"). In auto mode, file only the highest-severity ~25 and log the remainder to `open-questions.md` as deferred. A 300-issue dump is unactionable and buries the drift that matters.

**Interactive:** present the consolidated findings, grouped by domain then severity, each showing `file:line`, the doctrine_ref, the description, and the suggested fix. Show counts ("14 findings: 3 high, 8 medium, 3 low; 2 possible duplicates flagged; 5 opinions set aside"). Let the user approve all / drop specific ones / edit / cancel. **File nothing before approval.**

**Auto (granted):** skip the gate; the deduped findings list IS the file list (subject to the max-findings gate). Still print it, and log the filed set to `open-questions.md` so the human can review post-hoc.

## Phase 5 — File scoped issues

For each approved finding, file ONE issue against the `issue_target`:

- **Title**: concise, names the rule and location (`[architecture] handlers/import: order.go imports repository directly`).
- **Body**: the `file:line` evidence, the `doctrine_ref` (quote the rule + where it lives), the description, and the suggested fix.
- **Labels** (when the tracker supports them): a consistent audit label (e.g. `doctrine-drift`) plus the domain — this is what makes the *next* audit's dedupe reliable, so apply it consistently.
- GitHub: `gh issue create --title ... --body ... --label ...`. JIRA: create in the target project with the domain as a component/label.

One issue per violation — never bundle. Return the list of created issue URLs/keys, grouped by domain.

## Phase 6 — Report

- Issues filed (links), grouped by domain + severity.
- Findings dropped at the approval gate (if any).
- Possible duplicates flagged against existing issues.
- The `opinions` list (no doctrine basis) — surfaced for the user to consider promoting into actual doctrine, but not filed.
- If run with no doctrine found: a clear note that findings were heuristic, not doctrine-grounded.

## Artifact location

doctrine-audit is an ad-hoc sweep, not a plan-workspace skill — its artifacts go under the canonical ad-hoc root: `./.claude-results/<YYYY-MM-DD-HHMMSS>/doctrine-audit/` (gitignored). Written there:

- `findings.md` — the full consolidated findings list (including anything dropped at the gate or deferred by the max-findings gate), so nothing is lost between the summary and the tracker.
- `open-questions.md` — auto-mode deferred decisions: the filed set, deferred findings beyond the max-findings cap, and any judgment calls made without asking.

If a pipeline grant put the run inside an active `.claude-plans/<active>/` workspace, use that workspace's `open-questions.md` instead for the deferred log.

## Composition & degradation

- `knowledge-capture` — read as a doctrine source in Phase 1 if installed; skip with a one-line note otherwise.
- The tracker CLI/MCP (`gh`, Atlassian) — required only at Phase 5, and only if `issue_target` isn't "nowhere". If the tracker is unavailable, fall back to printing the issues as a markdown list the user can file manually.
- Every spawned auditor carries `caller=doctrine-audit`; no auditor re-invokes this skill.

## Anti-patterns

- **Filing un-grounded findings** — no `doctrine_ref`, no auto-file; opinion goes in its own list.
- **Skipping the existing-issue dedupe** — re-filing tracked drift destroys trust in the audit; dedupe runs even in auto mode.
- **Over-scoping issues** — one violation per issue; a "fix all layering violations" mega-issue is unactionable.
- **Filing before the approval gate in interactive mode** — list first, always.
- **Inventing doctrine** — if the project has none, say so and label any heuristics as such rather than passing opinion off as the project's rules.
- **Reading auditor transcripts back into the main thread** — take the structured findings list only; the fan-out exists to keep scans out of the orchestrator's context.
- **Dumping hundreds of issues past the max-findings gate** — over ~25 findings means a severity-ranked summary and a subset decision, not a bulk file.

## Inputs accepted

- Scope (path or "whole repo").
- Domains (subset of architecture / tests / docs / standards, or custom).
- `issue_target` (github / jira / none).
- `mode=auto` (or grant) to skip the approval gate.

## Outputs

- A consolidated, deduped, doctrine-grounded findings list.
- One scoped issue per approved finding, consistently labeled, in the target tracker.
- A report grouping filed issues, dropped findings, possible duplicates, and set-aside opinions.
