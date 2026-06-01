# source-prompts

Per-source subagent prompts for `research_new` and `refresh_existing` fan-out. Mirrors `pre-task-research`'s structured-record discipline, scoped to one tech item.

## Source selection by kind

Before dispatching sources, the parent skill selects which sources to run based on `kind`. This preamble governs dispatch order; individual source prompts below remain kind-agnostic.

For **`kind: library`**: dispatch Homepage (1) → Repo README (2) → CHANGELOG (3) → knowledge-capture (4, never dropped) → ecosystem MCP (AWS docs for `ecosystem=aws`, MS Learn for `ecosystem=dotnet`) in that order. CHANGELOG is the primary delta source on `refresh_existing`.

For **`kind: service`**: dispatch AWS Documentation MCP (`mcp__aws-documentation__search_documentation` + `mcp__aws-documentation__read_documentation`) as **PRIMARY** when `ecosystem=aws-service`. For `ecosystem=gcp-service`, use Google Cloud docs via WebFetch. For `ecosystem=azure-service`, use MS Learn MCP as PRIMARY. Homepage WebFetch runs second. CHANGELOG source is SKIPPED — services do not maintain CHANGELOG files. Use the AWS docs "New" section (via `mcp__aws-documentation__recommend`) and official feature-announcement pages instead. Knowledge-capture runs last (never dropped).

For **`kind: platform`**: dispatch official docs (WebFetch on homepage) → recent release notes page → knowledge-capture (never dropped). No CHANGELOG fallback — use the platform's releases/changelog page if one exists.

For **`kind: tool`**: dispatch Repo README (WebFetch) → CHANGELOG / GitHub releases → Homepage → knowledge-capture (never dropped). Similar to `kind: library` but CHANGELOG and GitHub releases are higher priority than the homepage.

Token budgets are unchanged (600/source, 2400 total). Drop order when total exceeds budget:

```
ms-learn → aws-docs → confluence → general-mcp → changelog → repo-readme → knowledge-capture (NEVER) → homepage (NEVER)
```

For `kind: service, ecosystem: aws-service`, `aws-docs` is elevated to NEVER-dropped status alongside knowledge-capture and homepage; it is the primary authoritative source.

## Budget

- **Per source:** 600 tokens (subagent output cap).
- **Total:** 2400 tokens across all sources.
- **Subagent timeout:** 90 seconds wall-clock per source.

Budgets are enforced **in-prompt** (each subagent system prompt states the cap), NOT post-hoc. Parent validates per-record format and drops any line that doesn't match. The parent does NOT re-summarize.

## Output formats (pinned)

Two record shapes, depending on source type:

**Citation record (homepage, README, MCP queries):**

```
- **<title>** — <url> — <one-line takeaway under 25 words>
```

**Changelog delta record (CHANGELOG / releases):**

```
- version: <semver>
  date: <ISO date>
  key_change: "<one-sentence summary of what changes for the user>"
```

Anything not matching is dropped whole (no mid-line truncation — breaks URLs).

If a subagent has nothing relevant, it returns the literal string `none` (one line). If it times out, it returns whatever partial records it has and the parent appends `_[truncated: time budget]_`.

## Drop order on total overflow

When total > 2400 tokens, whole-source drops in order from lowest to highest priority:

```
ms-learn → aws-docs → confluence → general-mcp → changelog → repo-readme → knowledge-capture (NEVER) → homepage (NEVER)
```

`knowledge-capture` and `homepage` are NEVER dropped — they're the floor on usefulness. `homepage` is the canonical authority and `knowledge-capture` is local tribal knowledge.

## Sources

### 1. Homepage docs (generic, all ecosystems)

Always run. Highest priority. `WebFetch` the library's homepage / canonical docs URL.

**Subagent prompt:**

> You are researching the tech item `<name>` (kind: `<kind>`, ecosystem: `<ecosystem>`, target version/snapshot: `<version>`).
>
> Fetch the canonical docs at `<homepage-url>`. Return at most 8 records, each formatted EXACTLY as:
>
> `- **<title>** — <url> — <one-line takeaway under 25 words>`
>
> Records should cover: the library's stated purpose (1 record), top-level concepts (2-3 records), and any "getting started" or "quick start" guide URL (1 record). Do NOT paraphrase content. Do NOT include code blocks. If the homepage 404s or the content is unhelpful, return the literal string `none`.
>
> Total output must not exceed 12 lines.

### 2. Repo README (generic, all ecosystems)

Always run. `WebFetch` the raw README URL.

**Default URL pattern:** `https://raw.githubusercontent.com/<org>/<repo>/HEAD/README.md`.

**Subagent prompt:**

> You are researching the tech item `<name>` (kind: `<kind>`, ecosystem: `<ecosystem>`).
>
> Fetch the raw README at `<readme-url>`. Return at most 6 records, each formatted EXACTLY as:
>
> `- **<title>** — <url> — <one-line takeaway under 25 words>`
>
> Records should cover: installation command (1 record), the main API entry point (1-2 records), known sharp edges or "things to know" sections (1-2 records), and the changelog link if README points to one (1 record). Do NOT paraphrase the README body. Do NOT include code blocks. If fetch fails (404, redirect loop, empty README), return `none`.
>
> Total output must not exceed 10 lines.

### 3. CHANGELOG / GitHub releases (kind=library | tool | platform)

**SKIP for `kind: service`** — services do not maintain CHANGELOG files. For services, use AWS docs "New" section via `mcp__aws-documentation__recommend` (Source 5) instead.

For `research_new` (library/tool/platform): fetch the changelog summary for the target version. For `refresh_existing`: fetch the delta between `prior_v` and `target_version`.

**Primary path:** `WebFetch` on `https://raw.githubusercontent.com/<org>/<repo>/HEAD/CHANGELOG.md` (or `HISTORY.md`, `RELEASES.md`, `NEWS.md` — first hit wins).

**Fallback path:** `gh api repos/<org>/<repo>/releases` for the relevant version range.

**Subagent prompt (refresh delta):**

> You are researching the delta in `<name>` from version `<prior_v>` to `<target_version>`.
>
> Fetch `<changelog-url>`. If it 404s, run `gh release list -R <org>/<repo> --limit 20` and then `gh api repos/<org>/<repo>/releases/tags/<target_version>` for the version body.
>
> Return at most 6 records, each formatted EXACTLY as:
>
> ```
> - version: <semver>
>   date: <ISO date>
>   key_change: "<one-sentence summary of what changes for the USER (not internal refactors)>"
> ```
>
> Cover the most user-facing changes in the version range — breaking changes first, then deprecations, then new features. SKIP internal refactors, dependency bumps, doc-only changes. If the range is empty or the changelog format is unparseable, return `none`.
>
> Total output must not exceed 24 lines.

**Subagent prompt (research_new — single version):**

> You are researching version `<target_version>` of `<name>`.
>
> Fetch `<changelog-url>` or `gh api repos/<org>/<repo>/releases/tags/<target_version>`. Return up to 4 records, one per major theme of this version (breaking changes, new feature group, deprecation, infra). Format EXACTLY:
>
> ```
> - version: <target_version>
>   date: <ISO date>
>   key_change: "<one-sentence summary>"
> ```
>
> If unavailable, return `none`.
>
> Total output must not exceed 16 lines.

### 4. knowledge-capture local entries (composition)

Always run. NEVER dropped on overflow. Invoke `knowledge-capture` with `caller=tech-brief`, `read_entries(kind="all", limit=20, since=null)`. Filter the returned digest to entries whose tags or title contain the canonical name OR any alias.

**No subagent — this is a direct read API call.** The parent skill folds matching entries into the Gotchas and "Specifics worth remembering" sections as candidate bullets (subject to user review in interactive mode).

If knowledge-capture is not installed (sibling-installed check fails): skip this source, log to `open-questions.md` ("knowledge-capture sibling not installed; tech-tagged gotchas not pulled"). Do NOT block.

### 5. AWS docs MCP (ecosystem=aws OR ecosystem=aws-service)

Run when `ecosystem == aws` OR `ecosystem == aws-service`. For `kind: service, ecosystem: aws-service`, this source runs FIRST (before homepage) and is NEVER dropped on overflow. Uses `mcp__aws-documentation__search_documentation` + `mcp__aws-documentation__read_documentation` + `mcp__aws-documentation__recommend` (for "New" / recently released content).

**Subagent prompt (kind=service, ecosystem=aws-service):**

> You are researching the AWS service `<name>` for inclusion in a tech brief.
>
> 1. Call `mcp__aws-documentation__search_documentation` with `search_phrase: "<name> overview"`.
> 2. For the top 2 results, call `mcp__aws-documentation__read_documentation`.
> 3. For each of the top 2 URLs, also call `mcp__aws-documentation__recommend` to surface the "New" section and related recently updated pages.
> 4. Return at most 8 records, each formatted EXACTLY as:
>
>    `- **<title>** — <url> — <one-line takeaway under 25 words>`
>
> Cover: service purpose (1), main API entry points (1-2), pricing model dimensions (1), hard limits/quotas (1), common IAM actions (1), and any "New" items from the last 6 months (1-2). Cite the documentation URL on every record per AWS docs MCP best practice. If search returns nothing relevant, return `none`.
>
> Total output must not exceed 12 lines.

**Subagent prompt (kind=library, ecosystem=aws — SDK brief):**

> You are researching the AWS service or SDK `<name>` for inclusion in a tech brief.
>
> 1. Call `mcp__aws-documentation__search_documentation` with `search_phrase: "<name> overview"`.
> 2. For the top 2 results, call `mcp__aws-documentation__read_documentation`.
> 3. Return at most 5 records, each formatted EXACTLY as:
>
>    `- **<title>** — <url> — <one-line takeaway under 25 words>`
>
> Cover: the service's primary use case (1 record), main API or SDK entry point (1-2 records), pricing-or-quotas notes (1 record if relevant), and known limitations or sharp edges (1 record). Cite the documentation URL on every record per AWS docs MCP best practice. If search returns nothing relevant, return `none`.
>
> Total output must not exceed 8 lines.

If the MCP tool is not in the tool list: skip silently. If it returns an error: surface the error to the user, skip the source for this run.

### 6. MS Learn MCP (ecosystem=dotnet)

Run only when `ecosystem == dotnet`. Uses `mcp__claude_ai_Microsoft_Learn__microsoft_docs_search` + `mcp__claude_ai_Microsoft_Learn__microsoft_docs_fetch`.

**Subagent prompt:**

> You are researching the .NET library `<library>` for inclusion in a tech brief.
>
> 1. Call `mcp__claude_ai_Microsoft_Learn__microsoft_docs_search` with the library name.
> 2. For the top 2 results, call `mcp__claude_ai_Microsoft_Learn__microsoft_docs_fetch`.
> 3. Return at most 5 records, each formatted EXACTLY as:
>
>    `- **<title>** — <url> — <one-line takeaway under 25 words>`
>
> Cover: package purpose (1 record), main API entry point (1-2 records), framework/runtime compatibility notes (1 record), known gotchas or breaking changes (1 record). If search returns nothing relevant, return `none`.
>
> Total output must not exceed 8 lines.

Same skip rules as AWS docs MCP.

### 7. Atlassian / Confluence (internal MSP libraries)

Run only when MSP-detected (triangulated check from composition-skills decisions.md) AND the library name matches internal patterns OR the user opts in. Uses `mcp__claude_ai_Atlassian__search`.

**Subagent prompt:**

> You are researching the internal MSP library `<library>` for inclusion in a tech brief.
>
> 1. Call `mcp__claude_ai_Atlassian__search` with `query: "<library>"` and `cloudId: "nicusa.atlassian.net"`.
> 2. For the top 2 Confluence page results, fetch via `mcp__claude_ai_Atlassian__fetch`.
> 3. Return at most 4 records, each formatted EXACTLY as:
>
>    `- **<title>** — <url> — <one-line takeaway under 25 words>`
>
> Cover: the library's purpose within MSP (1 record), main owner/team (1 record if discoverable), and known integration points or sharp edges (1-2 records). If Confluence returns nothing, return `none`.
>
> Total output must not exceed 6 lines.

Two failure modes per `pre-task-research` convention:
- Tool not in tool list → silent skip.
- Auth error / 401 → surface `Atlassian: authenticate via mcp__claude_ai_Atlassian__authenticate, then re-run with fresh=true`. Skip this source for this run.

### 8. MSP Go API framework MCP (ecosystem=go, MSP-internal libraries)

Run only when `ecosystem == go` AND MSP-detected AND the library name matches internal patterns (heuristic: `msp-*`, or user opt-in during the interactive wave). Uses `mcp__msp-go-api-framework__search`.

**Subagent prompt:**

> You are researching the internal MSP Go library `<library>`.
>
> Call `mcp__msp-go-api-framework__search` with the library name. Return at most 5 records, each formatted EXACTLY as:
>
> `- **<title>** — <url> — <one-line takeaway under 25 words>`
>
> Cover: the library's role in the MSP API framework (1 record), main types/functions (1-2 records), and integration patterns (1-2 records). If search returns nothing relevant, return `none`.
>
> Total output must not exceed 8 lines.

Generic Go libraries (`gorilla/mux`, `go-redis`) do NOT trigger this source. The MCP is for in-scope MSP libraries only.

## Validation and assembly

Per the `pre-task-research` discipline:

1. For each subagent return, keep lines matching the structured-record format OR the literal `none`.
2. Drop everything else WHOLE (no mid-line truncation).
3. If a source's record count > its in-prompt cap, keep the first N and append `_[truncated: kept N of M items]_`.
4. If a subagent timed out (90s budget): include the validated partial, append `_[truncated: time budget]_`.

The parent skill then maps records into the brief body:
- Citation records → References section (top 8) + as candidate links in Mental model / Common patterns / Gotchas.
- Changelog delta records → Version history table row(s).
- knowledge-capture entries → candidate Gotchas bullets (user reviews in interactive mode).

The parent NEVER re-summarizes a subagent's output. "Let me synthesize what I found" is bloat that reintroduces every byte the in-prompt budget just saved.

## Failure mode summary

| Source | Tool absent | Auth error | Empty result | All required (homepage + README + changelog) fail |
|---|---|---|---|---|
| Homepage | n/a (WebFetch is always present) | surface | skip section, log | refuse the brief |
| Repo README | n/a | surface | skip section, log | refuse the brief |
| CHANGELOG | n/a | surface | fall back to `gh api releases` | refuse the brief |
| knowledge-capture | sibling-installed check fails → skip + log | n/a | skip section | n/a |
| AWS docs MCP | silent skip | surface | skip section | n/a |
| MS Learn MCP | silent skip | surface | skip section | n/a |
| Atlassian | silent skip | surface | skip section | n/a |
| MSP Go MCP | silent skip | surface | skip section | n/a |

"Refuse the brief" means surface to the user (interactive mode) or `open-questions.md` (auto mode) with the message: `"insufficient sources for an honest brief; install the library locally and provide a manual TL;DR via interactive prompt"`. The skill does NOT produce a hallucinated brief from training data.
