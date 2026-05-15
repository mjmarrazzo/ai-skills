# Budget Policy

Bloat is the antagonist for this skill. Budgets are enforced at three layers: in-prompt (each subagent), parent-side validation (record-level), and whole-record overflow drop (section-level). Nothing in this skill is allowed to do mid-line truncation — it breaks URLs and produces garbage citations.

---

## Per-source line caps

| Source | Default `per_source_lines` (N) | Max total lines per section (N+2) | Notes |
|---|---|---|---|
| Local knowledge | 20 records | 22 lines | Owned by `knowledge-capture` read API. |
| Library briefs | 5 briefs × ~10 lines each | ~52 lines | Sibling-skill call; cap = top 5 most-relevant briefs. NEVER dropped. |
| Confluence | 15 | 17 | |
| JIRA | 15 | 17 | MSP-gated. |
| Merged PRs | 15 | 17 | |
| Recent commits (gh fallback) | 15 | 17 | Replaces merged-PRs section. |
| AWS docs | 15 | 17 | |
| Microsoft Learn | 15 | 17 | |
| Open questions surfaced | 15 | 15 | Free-form; no header allowance needed. |

All caps are tunable per call via `budget.per_source_lines`. The local-knowledge cap is enforced inside `knowledge-capture`'s read API; pre-task-research passes it through.

---

## Total target and hard cap

| Metric | Value | Behavior |
|---|---|---|
| Soft target | 250 lines | Aim for this. Most populated digests are 80–140 lines. |
| Hard cap | 250 lines | Whole-record overflow drops fire when projected total exceeds this. |
| Time budget per subagent | 120 seconds | After 120s, partial validated results + `_[truncated: time budget]_` marker. |

The soft target and hard cap are the same number on purpose — there is no "warning zone". When the math says we will exceed 250, drops fire immediately, lowest priority first.

---

## Overflow drop order (priority — LOAD-BEARING)

When projected total > 250 lines, drop entire sections in this order until under budget:

| Drop order | Section | Why this order |
|---|---|---|
| 1 (first to drop) | Microsoft Learn | Publicly searchable later; least team-specific. |
| 2 | AWS docs | Publicly searchable later; same rationale. |
| 3 | Recent PRs / commits | Recoverable from `git log`; medium specificity. |
| 4 | JIRA | Team-specific but searchable in JIRA UI; MSP-gated already. |
| 5 (last droppable) | Confluence | Team-specific, harder to re-discover. |
| NEVER | Library briefs | Durable curated knowledge about specific deps; defeats the purpose of maintaining briefs if dropped. |
| NEVER | Local knowledge | Most tribal, least re-discoverable, the whole point of the digest. |

**Both local-knowledge AND library-briefs are NEVER dropped.** If the two never-drop sections together exceed 250 lines, the skill emits both sections and appends a single-line footer:

```
_[warning: never-drop sections (local-knowledge + library-briefs) exceed total budget; consider trimming .claude-knowledge/ or reducing matched briefs below 5]_
```

It does NOT truncate either section to fit. The user owns their gotchas log and their briefs; the skill surfaces all of both.

---

## Drop semantics (WHOLE-record, not partial)

Drops are always whole-section. The skill does NOT:
- Truncate a section to fewer records to make room.
- Drop the oldest records from a section.
- Mid-line truncate a single record to save characters.

When a section drops, append to the footer:

```
_[dropped: <section> — total exceeded 250-line budget]_
```

The dropped section's heading is NOT rendered. The next reader sees the footer and knows the source was queried but the result didn't fit.

---

## Record-level validation (parent-side)

After every subagent returns, the parent applies the regex:

```
^- \*\*[^*]+\*\* — \S+ — .{1,200}$
```

Behaviors:
- **Matches:** keep the line verbatim.
- **Does not match:** drop the line WHOLE. Never edit, never truncate.
- **Literal `none`:** preserve as the section body (renders as `_none found_`).
- **Sentinel lines** (`auth-error:`, `gh-unavailable`, `tool-unavailable`): trigger parent-side behavior; never render as records.

If post-validation count > N: keep the first N records (highest-relevance-first; subagent prompts ordered output). Append `_[truncated: kept N of M items]_` as the last entry for that section.

---

## Time-budget behavior (partial results)

Each subagent has 120s wall-clock. When a subagent misses the budget:

1. The subagent's last instruction is to return whatever it has, followed by `_[truncated: time budget]_`.
2. The parent treats this exactly like a normal return: validate, drop malformed, keep up to N.
3. The `_[truncated: time budget]_` marker is preserved as the final line of the section body.

If a subagent doesn't return AT ALL within 120s (no partial): the parent renders the section with `_skipped: subagent timeout (120s)_` and continues. Other subagents' results are unaffected.

---

## In-prompt enforcement (the load-bearing layer)

Every source prompt in `source-prompts.md` includes these clauses verbatim:

> Return at most <N> records.
> Return at most <M> lines total (counting any header).
> Each record is one line in this exact format:
> `- **<title>** — <url> — <one-line takeaway under 25 words>`
> Do NOT paraphrase contents. Do NOT add commentary, headers, or trailing summary.
> If nothing relevant, return the literal string `none`.

The reason this layer exists: post-hoc parent-side truncation breaks URLs and produces garbage. Enforcing bloat at the source of the tokens is cheap and durable. The parent's validation layer is a safety net, not the primary enforcement.

---

## Cache contract

Cache check at skill start:

```bash
test -f .claude-plans/<active>/research.md && \
  test $(($(date +%s) - $(stat -f %m .claude-plans/<active>/research.md 2>/dev/null \
         || stat -c %Y .claude-plans/<active>/research.md))) -lt 86400
```

Cache hit: reuse existing file. Skip all fan-out, all token spend, all subagent dispatch.

Cache miss: full fan-out.

Bypass via `fresh=true` (caller param) or natural phrases ("fresh research", "re-run research", "ignore the cache").

The cache key is implicit: workspace path + file existence + mtime <24h. No topic-hash. Same-topic rephrasings hit; cross-workspace runs miss; same-topic-new-workspace runs miss.

---

## Tunability

Callers may override defaults:

```yaml
budget:
  per_source_lines: 25       # default 15
  total_lines: 400           # default 250
  time_seconds: 180          # default 120
```

When overrides land, the parent passes `<N>` and `<M>` to each subagent prompt via template substitution. The 25-word takeaway rule and the record format are NOT tunable — they're load-bearing for the validation regex.

Total budget caps above 500 lines start to defeat the skill's purpose (parent re-summarization risk). The skill warns once in `open-questions.md` when `total_lines > 500`:

```markdown
## <date> — pre-task-research — large total_lines override
**What we rolled with:** total_lines = <N>
**Why:** caller override
**You might want to revisit if:** research.md becomes harder to skim than the source pages
```

---

## Anti-patterns (budget-specific)

- **Mid-line truncation.** Never. Breaks URLs and citations. Whole-record drops only.
- **Truncating local knowledge to fit budget.** Never. Local is uncapped at the section level; user owns the gotchas log.
- **Re-running fan-out on cache hit.** Cache hit short-circuits all token spend. Force only via `fresh=true`.
- **Parent re-summarizing to "make it fit".** The parent assembles; it never paraphrases. If the digest is too long, drops fire. Period.
- **Per-source caps above 30 records.** The skill is a citation index, not a search dump. If N > 30 looks tempting, narrow the topic instead.
