# pre-task-research — DESIGN

Status: design. The implementation lives in `SKILL.md` and `references/`.

## Goal

Produce a citation-rich digest (`research.md`) of everything the team already knows about a topic — local knowledge, Confluence, JIRA, recent merged PRs touching the same paths, AWS docs, Microsoft Learn — BEFORE blueprint Phase 1 fires the discovery questionnaire. The digest is structured, bloat-bounded, and fans out to source-typed subagents in parallel so the parent session never sees raw page contents.

Bloat is the antagonist for this entire skill. Every design decision is downstream of "the digest must fit, and the parent must not re-summarize." The skill loses its value the moment it leaks page text into the main session.

## What it is not

- Not a code search tool. Use grep/Glob for repo-local code questions.
- Not a documentation writer. Output is a citation list, not prose.
- Not a chat-with-the-docs interface. One pass, write the artifact, done.
- Not a substitute for blueprint Phase 1. It runs BEFORE Phase 1 and feeds it.

## When to trigger

Pushy when scope is wide or unfamiliar; quiet on trivial requests.

Auto-trigger:
- Blueprint Phase 1 offers it when scope signals fire (more than 5 files touched, new subsystem, cross-cutting concerns like auth/billing/migrations) and the user opts in via a single AskUserQuestion. See `skills/blueprint/SKILL.md` Phase 1.
- User says "research X first", "deep dive on Y", "what do we already know about Z", "look it up before planning".

Skip when:
- The request is a trivial edit (one-line change, rename, typo).
- The user opts out: "skip research", "just plan it", "no research".
- `research.md` already exists in the active workspace and is <24h old (cache hit). User opts out of the cache via "fresh research", "re-run research", or caller `fresh=true`.
- `caller=pre-task-research` (cycle guard — log error and no-op).

## Inputs (caller-supplied or inferred)

- `topic: string` — default: the user request as posed. In interactive mode, the skill re-asks for a focused topic when the request is broad.
- `sources: [...]` — default: all available. Members: `local-knowledge`, `confluence`, `jira`, `merged-prs` (or `commits` fallback), `aws-docs`, `ms-learn`. Source availability is detected, not assumed.
- `mode: interactive | auto` — default: `interactive` per the human-in-the-loop default decision. Auto mode runs full fan-out and logs source-choice rationale to `open-questions.md`.
- `fresh: bool` — default `false`. Forces re-run even if a recent `research.md` exists.
- `budget: { per_source_lines: 15, total_lines: 250, time_seconds: 120 }` — tunable per call; defaults pinned.
- `caller: <skill-name>` — required for cycle guard. `caller=pre-task-research` is a misuse: log error and no-op.

## Outputs

- Workspace artifact: `.claude-plans/<active>/research.md`. Template lives at `references/research-template.md`. Total target ≤250 lines.
- Auto-mode side artifact: `.claude-plans/<active>/open-questions.md` (append). Entries record source-choice rationale and any source that returned `none` or `[truncated]`.
- Pre-workspace mode (blueprint Phase 1 hasn't created a workspace yet): `./.claude-results/<YYYY-MM-DD-HHMMSS>/pre-task-research/research.md`. Blueprint moves it into the workspace once one is created.

## Workflow

```
1. Cycle/cache/scope guards
2. Interactive question wave (sources + focus)   [skip in auto mode; log to open-questions.md]
3. Source availability probe                      [silent for unavailable; surface for auth-errors]
4. TodoWrite: one item per selected source
5. Local knowledge FIRST (synchronous, cheap)
6. External sources IN PARALLEL (one subagent per source, in-prompt budget)
7. Validate each subagent return; drop malformed lines (never truncate mid-line)
8. Assemble research.md from the template, in section order
9. If projected total > 250 lines: whole-record drop in priority order
10. Surface artifact path; log deferred decisions in auto mode
```

### 1. Cycle / cache / scope guards

Run in order. First-fail short-circuits.

- **Cycle guard:** `caller=pre-task-research` → log to stderr, no-op return.
- **Triviality guard:** if the user's request is a one-line/typo/rename or matches an explicit opt-out phrase, log "skipped: trivial" and exit.
- **Cache guard:** `test -f .claude-plans/<active>/research.md` AND its mtime is <24h old (`stat -f %m`, BSD; `stat -c %Y`, GNU). Cache hit: surface the existing path and exit with "cache hit — pass `fresh=true` to re-run". `fresh=true` or natural phrases ("fresh research", "re-run research", "ignore the cache") bypass the cache.

The cache key is implicit: workspace + file existence + age. No topic-hash. Same-topic rephrasings still hit the cache; cross-workspace runs do not. Pinned in `decisions.md` of this workspace.

### 2. Interactive question wave (default mode)

Interactive is the default. Before fan-out, ask the user via `AskUserQuestion` (max one wave, max 4 questions):

1. **Source selection** — "Which sources should I query?" Options: "All available", "Local knowledge only", "Local + Confluence", "Custom (you'll list them)". Default highlighted: "All available".
2. **Topic focus** (when the request is broad) — free-form: "What's the focused topic for this research run?" Skip when the original request is already narrow (single subsystem, single proper noun).
3. **JIRA scope** (only when MSP detected AND JIRA is selected) — "Include only the current branch's ticket, or search the whole project?" Defaults: "Current branch ticket + linked issues".

In auto mode, skip all of this and log to `open-questions.md`:

```markdown
## <date> — pre-task-research — source selection
**Question we'd have asked:** Which sources should I query?
**What we rolled with:** all available, MSP-gated JIRA = on
**Why:** auto mode, triangulated MSP detection matched
**You might want to revisit if:** any source returned `none` or `[truncated]`
```

### 3. Source availability probe

Two distinct failure modes per source (per composition-skills decisions.md and this workspace's decisions.md):

- **Tool not present** (MCP not in tool list, `gh` missing, etc.) → silent skip. Section omitted from `research.md`; one-line note in auto-mode `open-questions.md`.
- **Auth error / 401** → surface to user as actionable message: "Atlassian: authenticate via `mcp__claude_ai_Atlassian__authenticate` then re-run." Skip this source for the run. Same pattern applies to Microsoft 365 and AWS Marketplace.

Per-source probes:
- `local-knowledge`: `test -d .claude-knowledge/`. Always available even when absent — empty section.
- `confluence`: `mcp__claude_ai_Atlassian__search` is in the tool list. Calls returning auth-error trigger the actionable message.
- `jira`: `mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql` is in the tool list AND the workspace is MSP-detected (per composition-skills decisions.md triangulation) OR caller passed `sources` explicitly including `jira` OR user opted in. Non-MSP workspaces omit JIRA entirely by default.
- `merged-prs`: `gh --version` succeeds. If not: fall back to `git log` (next bullet).
- `commits` (gh fallback): always available when in a git repo. Section heading becomes `## Recent commits touching <paths> (gh not available)`.
- `aws-docs`: `mcp__aws-documentation__search_documentation` is in the tool list.
- `ms-learn`: `mcp__claude_ai_Microsoft_Learn__microsoft_docs_search` is in the tool list.

### 4. TodoWrite

Track each selected source as a todo item so the user can see progress:

```
- [✓] Local knowledge
- [⏳] Confluence
- [⏳] JIRA
- [⏳] Merged PRs
- [⏳] AWS docs
- [⏳] Microsoft Learn
```

Update each item as its subagent completes (`✓` / `none` / `[truncated]` / `skipped: <reason>`).

### 5. Local knowledge FIRST (synchronous)

`knowledge-capture` is the only sibling read here. Invoke `caller=pre-task-research`, request `read_entries(kind="all", limit=20)`. The skill returns a bounded markdown digest (per knowledge-capture's read API).

**Critical:** local knowledge is ALWAYS section #1 but NEVER causes early exit. Even when a local entry "directly answers" the topic, external sources still run. The "directly answers" check is a vibes-check the LLM will overuse; making the user pay for one fan-out is cheaper than missing context downstream. See decisions.md for the rationale.

Only the user opting in to `local_only=true` (or interactive selection "Local knowledge only") skips the fan-out.

### 6. External sources IN PARALLEL

All selected external sources dispatch as subagents in ONE message (parallel fan-out). One subagent per source. Each receives its specific system prompt from `references/source-prompts.md`. Each prompt enforces:

> Return at most N items, each formatted EXACTLY as: `- **<title>** — <url> — <one-line takeaway under 25 words>`. Do not paraphrase contents. If you have nothing relevant, return the literal string `none`. Total output must not exceed M lines.

N defaults to 15 per source. M is N+2 (header allowance).

**Parent never re-summarizes.** The parent's job is: validate format, drop malformed lines, concatenate digests in section order, write the artifact. Any "let me restate what I found" step in the parent re-introduces the bloat the skill exists to prevent.

### 7. Validate and drop malformed lines

For each subagent return:

1. Split on newlines.
2. Keep lines matching the regex `^- \*\*[^*]+\*\* — \S+ — .{1,200}$` (record format) OR the literal `none`.
3. Drop everything else. Do NOT mid-line truncate (truncation breaks URLs and citations — see decisions.md).
4. If post-validation count > N: keep the first N records; append a `_[truncated: kept N of M items]_` line as the last entry for that section.
5. If a subagent missed its 120s time budget: include partial validated results plus `_[truncated: subagent time budget exceeded]_`.

### 8. Assemble research.md

Use the template at `references/research-template.md` verbatim. Section order is the priority order (highest to lowest):

1. Local knowledge
2. Confluence
3. JIRA (MSP-gated)
4. Recent PRs (or Recent commits — gh fallback)
5. AWS docs
6. Microsoft Learn
7. Open questions surfaced

Empty sections (subagent returned `none`, source skipped) are still rendered with a one-liner: `_none found_` or `_skipped: <reason>_`. Empty sections matter — they tell the next reader "we did look here and the well was dry."

### 9. Whole-record overflow drop

After assembly, count lines. If total > 250: drop entire sections in priority order from lowest to highest until under budget:

```
1. Microsoft Learn      ← drop first
2. AWS docs
3. Recent PRs / commits
4. JIRA
5. Confluence
6. Local knowledge      ← never dropped
```

Each drop appends a footer line: `_[dropped: <section> — total exceeded 250-line budget]_`. Never partial-drop a section; always whole-record. Whole-record drops preserve citation integrity.

This order is the LOAD-BEARING design decision: low-relevance external docs go first; tribal local knowledge stays. The drop order is pinned in `references/budget-policy.md`.

### 10. Surface and log

- Print one-line summary: `research.md — <N> records across <M> sources — <path>`.
- In auto mode: append source-choice rationale and any `none`/`[truncated]`/`dropped` events to `open-questions.md`. Surface count: "logged 2 deferred items in open-questions.md".
- In interactive mode: only surface the artifact path; the next gate (typically blueprint Phase 1) owns user interaction.

## Budget enforcement IN-PROMPT, not post-hoc

The single most important design choice. Each subagent's system prompt tells it the line cap explicitly:

> You return at most 15 items, each on its own line, in this exact format:
> `- **<title>** — <url> — <one-line takeaway under 25 words>`
> Do not paraphrase. Do not exceed 17 total lines (including header). If you have nothing relevant, return the literal string `none`.

This pushes bloat enforcement up to the source of the tokens, where it's cheap. Post-hoc parent-side truncation breaks URLs, splits citations, and produces garbage entries. The parent's validation step (step 7) drops MALFORMED records WHOLE — it never edits a record.

If a subagent returns prose anyway: the parent's regex drops every prose line. The section ends up empty with a note. That's the right failure mode — better an empty section than a hallucinated digest.

## Source-priority order and overflow drop

Both ordering and overflow are pinned. Source order in `research.md` matches priority order (highest first):

| Priority | Source | Drop order on overflow |
|---|---|---|
| 1 | Local knowledge | never |
| 2 | Confluence | 5th to drop |
| 3 | JIRA (MSP-gated) | 4th to drop |
| 4 | Recent PRs / commits | 3rd to drop |
| 5 | AWS docs | 2nd to drop |
| 6 | Microsoft Learn | 1st to drop |

Rationale: local knowledge is the most tribal and least re-discoverable. Confluence and JIRA carry team-specific context. PRs/commits carry recent-change context. AWS and MS Learn are publicly searchable later — losing them in the digest is cheapest.

## Cache contract

Re-run check (BSD `stat -f %m` on macOS, GNU `stat -c %Y` on Linux):

```bash
test -f .claude-plans/<active>/research.md && \
  test $(($(date +%s) - $(stat -f %m .claude-plans/<active>/research.md 2>/dev/null || stat -c %Y .claude-plans/<active>/research.md))) -lt 86400
```

Cache hit → reuse existing `research.md`. The parent skill's next gate (blueprint Phase 1) reads the cached file. Cache is workspace-scoped; cross-workspace runs always miss.

`fresh=true` and natural phrases bypass. Cache does NOT consider topic similarity — workspace match is the only key.

## MSP detection for JIRA gating

Use the triangulated check pinned in composition-skills decisions.md:

1. Remote URL contains `nicusa` or `tylertech` (case-insensitive).
2. Current branch matches `^MSP-\d+/`.
3. Git config `user.email` ends in `@tylertech.com`.

ANY match → MSP repo → JIRA runs by default (still subject to user opt-out in interactive mode). NO match → JIRA omitted entirely unless caller passes `sources` including `jira` explicitly, OR user explicitly asks "include JIRA" in the interactive question wave.

When MSP-detected, JIRA query auto-populates with:
- Current branch's ticket key extracted from `MSP-\d+/...`.
- File paths from the user's request (best-effort matching to JIRA components/labels — fallback: project-wide recent activity).

## Atlassian auth-error contract

Distinguish three Atlassian outcomes:

| Outcome | Section in research.md | User-facing surface |
|---|---|---|
| Tool not in tool list | omitted | none (silent) |
| Auth error / 401 / no token | `_skipped: authenticate via mcp__claude_ai_Atlassian__authenticate, then re-run with fresh=true_` | yes (one-line message, actionable) |
| Tool present + auth ok + zero results | rendered with `_none found_` | none |

Same pattern applies to Microsoft 365 (`mcp__claude_ai_Microsoft_365__authenticate`). Silent skips hide actionable signal; the auth-error case must surface.

## `gh` absent → `git log` fallback

When `gh` is not installed or `gh pr list` fails:

1. Section heading changes from `## Recent PRs touching <paths>` to `## Recent commits touching <paths> (gh not available)`.
2. Subagent receives the commits-fallback prompt (`references/source-prompts.md`). Query:

   ```bash
   git log --all --follow --diff-filter=M --format='%h %ad %s' --date=short -- <paths>
   ```

3. Record format is the same: `- **<sha>** — <commit-subject> — <date> — <one-line takeaway>`.

Git is always available in a git repo; this path never silent-skips unless the workspace is outside any repo.

## Caller cycle guard

Every cross-skill invocation passes `caller=<skill-name>` (composition-skills decisions.md). This skill:

- Receives `caller` and stores it.
- When invoking `knowledge-capture` (read), passes `caller=pre-task-research`.
- When the received `caller` is `pre-task-research`: log to stderr ("misuse: pre-task-research called from pre-task-research"), no-op, return.

## TodoWrite usage

Track one todo per selected source. Update status as subagents complete. Example sequence:

```
[ ] Local knowledge        →  [✓] Local knowledge (5 entries)
[ ] Confluence             →  [✓] Confluence (12 records, [truncated])
[ ] JIRA                   →  [✓] JIRA (3 records)
[ ] Merged PRs             →  [✓] Merged PRs (8 records)
[ ] AWS docs               →  [✓] AWS docs (none)
[ ] Microsoft Learn        →  [✓] Microsoft Learn (skipped: auth error)
```

This is the user's progress signal for fan-out — without it, parallel subagents look like a black box.

## Composition matrix

| Skill | Callees (may invoke) | Callers (may invoke this) | If `caller=<self>` |
|---|---|---|---|
| pre-task-research | knowledge-capture (read) | blueprint (Phase 1), future start-ticket | log error to stderr, no-op |

## Failure modes

| Failure | Behavior |
|---|---|
| All external subagents return `none` | Render empty sections, surface "no external context found; local knowledge: <N> entries" |
| All external subagents return prose (malformed) | Drop all malformed lines; empty sections with `_none found (subagent returned malformed records)_` note; advise user once: "subagents returned freeform — research output is empty for those sources" |
| Subagent times out (120s) | Include validated partial; append `_[truncated: time budget]_` |
| Cache file corrupt / unparseable | Treat as cache miss; re-run |
| `.claude-plans/<active>/` does not exist | Pre-workspace mode: write to `./.claude-results/<ts>/pre-task-research/` |
| All sources unavailable | Surface "no sources available — research skipped" and exit |

## Anti-patterns

- **Full-text dumps.** The whole reason this skill exists. Never. If a subagent returns prose, drop it — empty section is better than bloat.
- **Re-summarizing subagent output in the main session.** Bloat reentry. The parent validates and concatenates; it does not paraphrase. "Let me synthesize what I found" is the failure mode.
- **Running on trivial requests.** Cost without value. Trivial guard skips.
- **Running on the same topic within 24h without `--fresh`.** Cache hit. Force only when sources may have changed (post-PR-merge, post-doc-update).
- **Skipping the user-question wave in interactive mode to look efficient.** Interactive is the default for a reason — user-centric question-up-front beats "looked smart, missed scope" every time. Auto mode is opt-in; don't simulate it by skipping questions.
- **Early-exit on local-knowledge match.** Never. Local is section #1, external still runs. The "this answers it" check is a vibes-check.
- **Silent-skip on Atlassian auth error.** Surface the actionable message. Silent skip wastes a future fan-out.
- **Mid-line truncation.** Always whole-record drops. Mid-line truncation breaks URLs and produces garbage citations.
- **Topic-hashing the cache.** Workspace + file existence is the cache. Topic-hashing miscaches every rephrasing.
- **Re-running JIRA on non-MSP workspaces.** JIRA is MSP-gated by default. Generic templates baking `MSP-1234` examples into non-MSP runs is the failure mode this gate prevents.

## Open questions

- Should commit-fallback include `--since=6.months` to bound noise? Currently unbounded; let the per-source line cap be the limit.
- For very-large MSP repos, should the JIRA query auto-narrow to the current epic? Deferred to dogfooding.
- Should `aws-docs` and `ms-learn` subagents be promoted to opus for high-stakes paths (auth, payment, infra)? Currently sonnet for all source subagents; revisit if quality suffers.
