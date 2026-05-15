---
name: pre-task-research
description: Use this skill BEFORE planning when the user says "research before planning", "deep dive on X first", "look it up before we touch this", "what do we already know about Y". Also auto-invoked by `blueprint` Phase 1 for unfamiliar or large work (more than 5 files, new subsystem, cross-cutting concerns) when the user opts in. Fans out parallel subagents across local knowledge, Confluence, JIRA (MSP-detected), recent PRs, AWS docs, and Microsoft Learn; enforces token budgets in-prompt; writes a citation-rich `research.md`. Default is interactive — asks which sources to query before fan-out. Skip only on explicit opt-out ("skip research", "just plan it") or trivial requests.
---

# Pre-Task Research

Fan out parallel research subagents BEFORE blueprint Phase 1 so the discovery questionnaire isn't asking the user what's already in Confluence, JIRA, recent PRs, or last week's gotchas log. The output is a bloat-bounded digest — citation lines, no prose, hard line caps enforced in each subagent's system prompt.

**Announce at start:** "Using pre-task-research to gather what we already know before planning."

## When to run, when to skip

Auto-trigger:
- Blueprint Phase 1 offers it for scope signals (more than 5 files, new subsystem, cross-cutting concerns) and the user opts in via a single AskUserQuestion.
- User says "research X first", "deep dive on Y", "look it up before planning", "what do we already know".

Skip:
- Trivial requests (one-line edits, renames, typos).
- User opts out: "skip research", "just plan it", "no research".
- A `research.md` already exists in the active workspace and is <24h old (cache hit). User bypasses with "fresh research", "re-run research", or caller `fresh=true`.
- `caller=pre-task-research` — cycle guard, log error to stderr, no-op.

## Inputs (caller-supplied or inferred)

| Input | Default | Notes |
|---|---|---|
| `topic` | the user request | Interactive mode re-asks if the request is broad. |
| `sources` | all available | Members: `local-knowledge`, `confluence`, `jira`, `merged-prs` (or `commits` fallback), `aws-docs`, `ms-learn`. |
| `mode` | `interactive` | Per the HITL-default decision. `auto` opt-in via phrase or caller param. |
| `fresh` | `false` | Bypass cache; force re-run. |
| `budget` | `{per_source_lines: 15, total_lines: 250, time_seconds: 120}` | Tunable; defaults pinned. |
| `caller` | (required) | Cycle guard. Self-call no-ops. |

## Workspace resolution and output paths

Use the canonical active-workspace resolution algorithm pinned in `.claude-plans/2026-05-14-composition-skills/decisions.md`. In brief: check `WORKSPACE_PATH`; enumerate `.claude-plans/*/` with `plan.md` or `spec.md`; prefer the slug matching the current branch's ticket; fall back to most-recent mtime.

Output:
- Workspace mode: `.claude-plans/<active>/research.md`.
- Pre-workspace mode (blueprint Phase 1 called us before creating a workspace): `./.claude-results/<YYYY-MM-DD-HHMMSS>/pre-task-research/research.md`. Blueprint moves it into the workspace once created.

When writing to the ad-hoc root, append `.claude-results/` to `.gitignore` if not present (idempotent, same pattern as siblings).

## Default workflow

Phase order. Each phase short-circuits the rest on guard hit.

### 1. Guards

In order:

1. **Cycle guard:** `caller=pre-task-research` → log to stderr, return.
2. **Triviality guard:** request is a typo/rename/one-liner or matches an opt-out phrase → exit.
3. **Cache guard:**

   ```bash
   test -f .claude-plans/<active>/research.md && \
     test $(($(date +%s) - $(stat -f %m .claude-plans/<active>/research.md 2>/dev/null \
            || stat -c %Y .claude-plans/<active>/research.md))) -lt 86400
   ```

   Hit → reuse existing file. `fresh=true` or phrases "fresh research" / "re-run research" bypass. Cache key is workspace + file existence + age. No topic hashing.

### 2. Interactive question wave (DEFAULT)

Interactive is the default mode. Auto mode is explicit opt-in. Fire ONE wave via `AskUserQuestion`, max 3 questions, BEFORE any fan-out:

1. **Source selection** — Options: "All available" / "Local only" / "Local + Confluence" / "Custom". Default highlight: "All available".
2. **Topic focus** — free-form. Skip if the request is already narrow.
3. **JIRA scope** (only if MSP-detected AND JIRA selected) — "Current branch ticket + linked issues" / "Whole project".

In auto mode, skip the wave and log to `.claude-plans/<active>/open-questions.md`:

```markdown
## <date> — pre-task-research — source selection
**Question we'd have asked:** Which sources should I query?
**What we rolled with:** all available; MSP-gated JIRA = <on|off>
**Why:** auto mode, triangulated MSP detection = <true|false>
**You might want to revisit if:** any source returned `none` or `[truncated]`
```

**Do NOT skip the wave in interactive mode to look efficient.** Interactive is the methodology; the wave is load-bearing.

### 3. Source availability probe

Two failure modes per external source:

- **Tool not in tool list** → silent skip. Section omitted; one-line log in auto-mode `open-questions.md`.
- **Auth error / 401** → surface actionable message to user, skip source for this run:

  > Atlassian: authenticate via `mcp__claude_ai_Atlassian__authenticate`, then re-run with `fresh=true`.

Same pattern for Microsoft 365 (`mcp__claude_ai_Microsoft_365__authenticate`).

### 4. TodoWrite — one item per selected source

```
[ ] Local knowledge
[ ] Confluence
[ ] JIRA
[ ] Merged PRs (or Recent commits if gh absent)
[ ] AWS docs
[ ] Microsoft Learn
```

Update each as its subagent completes: `✓ <N> records` / `✓ none` / `[truncated]` / `skipped: <reason>`. This is the user's progress signal for the parallel fan-out.

### 5. Local knowledge FIRST (synchronous)

Invoke `knowledge-capture` with `caller=pre-task-research`, requesting `read_entries(kind="all", limit=20)`. Render the returned digest verbatim as section #1 of `research.md`.

**Critical:** local knowledge is ALWAYS section #1 but NEVER causes early exit. Even on direct-match, external sources still run. The "this answers it" check is a vibes-check the LLM will overuse; one fan-out is cheaper than missing context downstream.

Only `local_only=true` or interactive selection "Local only" skips the fan-out.

If `knowledge-capture` is not installed: section header still rendered with `_skipped: knowledge-capture sibling not installed_`.

### 6. External sources IN PARALLEL

All selected external sources dispatch as subagents in ONE message (single parallel fan-out). One subagent per source. Each receives its specific system prompt from `references/source-prompts.md`. Every prompt enforces:

> Return at most N items, each formatted EXACTLY as: `- **<title>** — <url> — <one-line takeaway under 25 words>`. Do not paraphrase contents. If nothing relevant, return the literal string `none`. Total output must not exceed M lines.

`N = 15` (default), `M = N + 2` (header allowance). Budgets are enforced IN-PROMPT, not post-hoc. The parent does NOT re-summarize.

### 7. Validate and assemble

For each subagent return:

1. Keep lines matching the structured-record regex OR the literal `none`.
2. Drop everything else WHOLE (no mid-line truncation — it breaks URLs).
3. If count > N: keep first N, append `_[truncated: kept N of M items]_`.
4. If subagent timed out (120s budget): include validated partial, append `_[truncated: time budget]_`.

Concatenate in priority order using the template at `references/research-template.md`. Empty sections still render with `_none found_` or `_skipped: <reason>_` — empty sections matter because they tell the next reader "the well was dry".

### 8. Whole-record overflow drop

If total > 250 lines: drop entire sections from lowest to highest priority until under budget:

```
ms-learn → aws-docs → merged-prs → jira → confluence → local-knowledge
```

`local-knowledge` is NEVER dropped. Each drop appends `_[dropped: <section> — total exceeded 250-line budget]_`. Never partial-drop; always whole-record.

See `references/budget-policy.md` for the full priority table and drop rules.

### 9. Surface and log

- Print: `research.md — <N> records across <M> sources — <path>`.
- Auto mode: append source-choice rationale and `none`/`[truncated]`/`dropped` events to `open-questions.md`; surface "logged <K> deferred items in open-questions.md".
- Interactive mode: surface artifact path only; next gate (blueprint Phase 1) owns user interaction.

## Source-priority order

| Priority | Source | Drop on overflow |
|---|---|---|
| 1 | Local knowledge | NEVER |
| 2 | Confluence | 5th |
| 3 | JIRA (MSP-gated) | 4th |
| 4 | Recent PRs (or commits) | 3rd |
| 5 | AWS docs | 2nd |
| 6 | Microsoft Learn | 1st |

Local is most tribal and least re-discoverable. Confluence / JIRA carry team-specific context. PRs / commits carry recent change context. AWS / MS Learn are publicly searchable later — losing them in the digest is cheapest.

## MSP detection for JIRA gating

Triangulated check from composition-skills decisions.md. JIRA runs by default ONLY when one matches:

1. Remote URL contains `nicusa` or `tylertech` (case-insensitive).
2. Current branch matches `^MSP-\d+/`.
3. Git config `user.email` ends in `@tylertech.com`.

Non-MSP workspaces omit JIRA entirely unless caller explicitly passes `sources` including `jira`, or user opts in during the interactive wave.

For MSP-detected runs, JIRA query seeds:
- Current branch's ticket key (from `MSP-\d+/...`).
- File paths from the request, best-effort matched to JIRA components/labels; fallback to project-wide recent activity.

## Atlassian / Microsoft auth contract

Three outcomes, three behaviors:

| Outcome | Section | Surface to user |
|---|---|---|
| Tool not in tool list | omitted | none (silent) |
| Auth error / 401 | `_skipped: authenticate via <tool>, then re-run with fresh=true_` | yes, actionable |
| Tool present + zero results | rendered with `_none found_` | none |

Silent skip on auth error hides actionable signal — surface it.

## `gh` absent → `git log` fallback

When `gh` is not installed or `gh pr list` fails:

1. Section heading becomes `## Recent commits touching <paths> (gh not available)`.
2. Subagent receives the commits-fallback prompt from `references/source-prompts.md`. Query template:

   ```bash
   git log --all --follow --diff-filter=M --format='%h %ad %s' --date=short -- <paths>
   ```

3. Record format: `- **<sha>** — <commit-subject> — <date> — <one-line takeaway>`.

Git is always available in a git repo. This path never silent-skips except outside any repo.

## Cache policy

Cache hit when:

```bash
test -f .claude-plans/<active>/research.md && file is <24h old
```

Cache is implicit (workspace + file existence + age). No topic-hash — same-topic rephrasings hit, cross-workspace runs miss. Bypass via `fresh=true` or natural phrases ("fresh research", "re-run research", "ignore the cache").

## Caller-supplied parameters

The full contract a caller may pass:

```yaml
caller: <skill-name>       # required, cycle guard
topic: <string>            # optional, defaults to user request
sources: [<source>, ...]   # optional, defaults to all available
mode: interactive | auto   # optional, defaults to interactive
fresh: <bool>              # optional, defaults to false
budget:
  per_source_lines: <int>  # default 15
  total_lines: <int>       # default 250
  time_seconds: <int>      # default 120
```

`caller=pre-task-research` is misuse: log to stderr and return.

## Composition

| Skill | Callees (may invoke) | Callers (may invoke this) | If `caller=<self>` |
|---|---|---|---|
| pre-task-research | knowledge-capture (read only) | blueprint (Phase 1 offer), future start-ticket | log error, no-op |

- **Reads:** `knowledge-capture`'s `.claude-knowledge/` via its read API (with `caller=pre-task-research`); active workspace for cache check; git state for MSP detection and commit fallback; MCP tool list for source availability.
- **Writes:** `.claude-plans/<active>/research.md` (or ad-hoc root in pre-workspace mode); appends to `open-questions.md` in auto mode; idempotent `.gitignore` append for `.claude-results/` when ad-hoc.
- **Never reads:** the contents of pages returned by subagents. The parent only sees structured records.

If a sibling isn't installed, mention once and degrade gracefully — never block.

## Anti-patterns

- **Full-text dumps.** The whole reason this skill exists. If a subagent returns prose, drop every prose line — empty section beats bloat.
- **Re-summarizing subagent output in the main session.** The parent validates and concatenates; it does NOT paraphrase. "Let me synthesize what I found" reintroduces every byte the in-prompt budget just saved.
- **Running on trivial requests.** Cost without value. Trivial guard skips.
- **Running on the same topic within 24h without `--fresh`.** Cache hit. Force only when sources may have moved (post-merge, post-doc-update).
- **Skipping the user-question wave in interactive mode to look efficient.** Interactive is the methodology — the wave is load-bearing. Auto mode is opt-in; don't simulate it by skipping the questions.
- **Early-exit on local-knowledge match.** Never. Local is section #1, external still runs. The "this answers it" check is a vibes-check the LLM will overuse.
- **Silent-skip on Atlassian auth error.** Surface the actionable message. Silent skip wastes the next fan-out too.
- **Mid-line truncation to fit budget.** Whole-record drops only. Mid-line truncation breaks URLs and produces garbage citations.
- **Topic-hashing the cache.** Workspace + file existence is the cache. Topic-hashing miscaches every rephrasing.
- **Running JIRA on non-MSP workspaces by default.** JIRA is MSP-gated. The gate exists precisely to keep this skill generic.

## Open questions

- Whether commit-fallback should bound by `--since=6.months` (currently unbounded; per-source cap is the limit).
- Whether AWS-docs and MS-Learn subagents should promote to opus for high-stakes paths (auth, payment, infra). Currently sonnet for all source subagents.
- Whether `aws-marketplace`, `datadog-mcp`, or `msp-go-api-framework` should be first-class sources. Currently out of scope; surface in `open-questions.md` if user installs them.
