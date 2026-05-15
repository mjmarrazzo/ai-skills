# tech-brief — DESIGN

Status: v2. The on-disk format, the 5-intent API, and the markdown digest shape are a long-lived contract that two sibling skills (`blueprint`, `pre-task-research`) depend on, plus direct user invocation. Bumps to `schema_version` require a written migration path. v2 adds `kind`, broadened ecosystem enum, service-only sections, and the "Specifics worth remembering" all-kind section.

## Goal

A central, durable, cross-project knowledge store for libraries, managed services, platforms, and CLI tools. Researches a piece of technology once, writes a terse brief outside any single repo (`~/.claude/data/tech-briefs/<ecosystem>/<name>.md`), treats every re-encounter as an append-only delta, and exposes a 5-intent API the rest of the monorepo can read from or write through.

Not in scope: replacement for upstream docs, code-sample hosting, version-pin tracking in user projects, automatic monitoring, cross-machine sync (v2), search index.

## Kinds

Every brief carries a required `kind` field that drives section visibility, version semantics, and source-prompt selection:

| Kind | Definition |
|---|---|
| `library` | Packages you install via a package manager (npm, pip, maven, cargo, etc.). Existing behavior. |
| `service` | Managed cloud services (Lambda, DSQL, S3, BigQuery, Cosmos DB). No package to install; the service runs upstream. |
| `platform` | CI/CD or hosting platforms (GitHub Actions, CircleCI, Vercel, Cloudflare Pages). Consumed via config or API, not installed as a package. |
| `tool` | CLI tools (gh, terraform, awscli). Installed as a binary; run from the shell. |

## The shape of the contract

Briefs are gathered under one central directory:

```
~/.claude/data/tech-briefs/
├── README.md           # auto-regenerated index — grouped by kind then ecosystem, atomic tmpfile + rename
├── .schema.json        # schema_version, kind enum, ecosystem enum, stale thresholds, line caps
├── .audit.log          # append-only write log; rotates at 10 MiB to .audit.log.1 (single backup)
└── <ecosystem>/
    ├── <name>.md
    ├── <name>.archived-<YYYY-MM-DD>.md        # archive intent output
    ├── <name>.v<N>.md                          # clobber intent output
    └── <name>/                                 # ref-file overflow dir (deep mode)
        ├── ref-1.md
        └── ref-2.md
```

Path override: `CLAUDE_TECH_BRIEFS_DIR=<absolute-path>` resolves the root from the env var. Used for testing and for users who keep their briefs in a dotfiles repo. When set, the skill treats the env value verbatim.

### Why `~/.claude/data/`, not `~/.claude/`?

The `data/` segment isolates this skill's writable state from Claude Code's reserved namespace (`~/.claude/plugins/`, `skills/`, `projects/`, `settings.json`, `sessions/`). Sibling skills inside `~/.claude/` have been bitten by this collision before. Defensive namespace; one decision applied across all future user-data skills.

`~/.tech-briefs/` at HOME root was rejected — clutters HOME and breaks the `~/.claude/` convention for all user-facing Claude state.

## Library canonicalization

The canonical identifier is **the package-manager install name verbatim, lowercased, kebab-cased.** Per ecosystem:

| Ecosystem | Source of canonical name | Example |
|---|---|---|
| `js`, `ts` | npm package name; `@scope/pkg` → scope kept with `/` → `__` | `@aws-sdk/client-s3` → `aws-sdk__client-s3` |
| `python` | pip package name | `boto3`, `fastapi` |
| `go` | last segment of `go.mod` module path | `github.com/gin-gonic/gin` → `gin` |
| `java` | maven `artifactId` | `spring-boot-starter-web` |
| `kotlin` | maven `artifactId` (separate from `java` for tooling divergence) | `kotlinx-coroutines-core` |
| `rust` | crates.io name | `tokio`, `serde` |
| `dotnet` | NuGet package id | `microsoft-extensions-logging` |
| `ruby` | gem name | `rails`, `sidekiq` |
| `php` | composer package name (without vendor) | `laravel`, `symfony` |
| `swift` | SwiftPM package name | `alamofire` |
| `aws` | service code or SDK name | `boto3`, `aws-sdk-java-v2`, `aws-sdk-go-v2` — same SDK across ecosystems is allowed |
| `gcp`, `azure` | service or SDK name | `google-cloud-storage`, `azure-identity` |
| `gradle`, `maven` | plugin id / artifactId | `kotlin-multiplatform` |
| `npm` | bin name (when the package is primarily a CLI distributed via npm) | `prettier`, `eslint` |
| `cli` | binary name | `kubectl`, `terraform` |
| `db` | engine name | `postgres`, `redis` |
| `infra` | tool / platform | `terraform`, `pulumi`, `kubernetes` |
| `general` | escape hatch — agent picks best-fit name | `cron`, `git-lfs` |

The brief carries an `aliases:` frontmatter field listing other names the lib goes by. On every read and on every `research_new`, the skill probes both the canonical name AND the aliases of all existing briefs in the ecosystem dir before declaring "no brief found". Without aliases, `react-router` and `react-router-dom` would produce two briefs for the same library.

`research_new` canonicalization flow:
1. Compute canonical name from the user-supplied string per the table.
2. Scan `<ecosystem>/*.md` frontmatter for `name == canonical` OR `canonical IN aliases`.
3. If found: refuse with `"brief exists at <path>; pass intent=refresh_existing instead, or research_new with clobber=true and reason"`.
4. If not found: proceed.

## Ecosystem enum (CLOSED)

Closed enum with explicit `general` escape hatch:

```
js, ts, python, go, java, kotlin, rust, dotnet, ruby, php, swift,
aws, gcp, azure, gradle, maven, npm, cli, db, infra, general,
aws-service, gcp-service, azure-service, platform
```

`ts` is separate from `js` because tooling concerns diverge meaningfully (tsconfig, type defs, decorators). `kotlin` separate from `java` for the same reason. New ecosystems require a `schema_version` bump and `.schema.json` update.

New in v2: `aws-service`, `gcp-service`, `azure-service` are used only when `kind: service`. `platform` is used when `kind: platform` (GitHub Actions, Vercel, Cloudflare Pages, etc.). The existing `aws`, `gcp`, `azure` values remain for library/SDK briefs (boto3, google-cloud-storage, etc.).

Open-ended enum was rejected because of drift: `js` vs `node` vs `typescript` would fork the same library across multiple dirs.

## Version field flex per kind

Version-tracking fields vary by kind to match upstream semantics:

| Kind | Frontmatter fields | Type | Example |
|---|---|---|---|
| `library` | `version_last_seen` + `versions_explored` | semver | `19.1.0`, `[18.3.0, 19.0.0, 19.1.0]` |
| `service` | `snapshot_last_seen` + `snapshots_explored` | date or milestone ID | `2026-05-14`, `dsql-ga`, `re:invent-2024` |
| `platform` | `version_last_seen` + `versions_explored` | whatever upstream uses | `v4.2.0`, `2026-04` |
| `tool` | `version_last_seen` + `versions_explored` | semver or release tag | `2.45.0` |

`version_last_seen = semver_max(...)` rule applies to library/tool only. For service/platform, `snapshot_last_seen` is the most recently appended entry (chronologically by `Date examined`). The Version history table shape is unchanged across kinds; only the column header label adjusts (`Version` vs `Snapshot`).

## Service-only sections

When `kind: service`, the brief includes THREE additional sections inserted after Common patterns and before Gotchas:

1. **Pricing model** — one paragraph. The billing dimensions (per-request, per-GB-second, per-ACU, etc.). NOT a price quote — the model. Example: "Lambda: per request + per-GB-second of compute. Cold start billed; concurrency limits are soft quotas. Free tier: 1M requests/mo + 400k GB-sec/mo."
2. **Quotas & limits** — bullets, append-only. Examples: "Lambda function timeout: 15 min hard cap." "DSQL concurrent connections per cluster: documented quota TBD."
3. **IAM / permissions cheatsheet** — block. Common actions/resources. Example: "`lambda:InvokeFunction`, `lambda:GetFunction`. Execution role needs `logs:CreateLogGroup`."

These sections do NOT appear for `kind: library | platform | tool`.

## All-kind "Specifics worth remembering" section

Every brief (all kinds) gets a "Specifics worth remembering" section before References:

```markdown
## Specifics worth remembering

- <long-tail bullet — thing about this tech that doesn't fit a primary section>
- ...
```

Append-only. No formal schema per bullet — free-text, ideally one sentence. This is NOT a duplicate of Gotchas — Gotchas are footguns ("you WILL hit this"); Specifics are accumulated lore ("worth noting"). Examples:
- *(Lambda)* "Container image cold starts are dramatically slower than zip for small payloads. Use zip when image flexibility isn't needed."
- *(React)* "useEffect with no deps array runs after every render — common foot-gun in lists."

## Source-prompt selection by kind

Source dispatch order varies by kind:

| Kind | Primary sources | Secondary | Notes |
|---|---|---|---|
| `library` | Homepage, repo README, CHANGELOG, knowledge-capture | ecosystem MCP (AWS docs / MS Learn) when SDK-relevant | existing behavior |
| `service` | AWS Documentation MCP (`mcp__aws-documentation__*`) PRIMARY for aws-service; cloud provider equivalent otherwise | release/feature announcements, AWS docs "New" section, knowledge-capture | CHANGELOG rarely useful for services |
| `platform` | Official docs (WebFetch), recent release notes | knowledge-capture | no CHANGELOG fallback |
| `tool` | Repo README, CHANGELOG, GitHub releases | knowledge-capture | similar to library |

For `kind: service, ecosystem: aws-service`: `mcp__aws-documentation__search_documentation` + `mcp__aws-documentation__read_documentation` run FIRST, before homepage WebFetch. The `recommend` tool is used to find related/new content. CHANGELOG source is skipped by default (services don't maintain CHANGELOG files); use AWS docs "New" section + re:Invent/feature announcement pages instead.

## HITL wave for tech-brief

The 2-question wave inherits from prior design but Q1 is expanded:

1. **Confirm: name + kind + ecosystem + version/snapshot**. Single structured question with the inferred values: "tech-brief for `lambda`, kind=service, ecosystem=aws-service, snapshot=2026-05-14 — yes / edit one / cancel".
2. **Sources + depth**. Unchanged.

## The 5 intents

Full input payloads and refusal cases in `references/api-contract.md`. Architectural summary:

### `research_new`

Inputs: `name`, `kind`, `ecosystem`, `caller`, optional `target_version` / `target_snapshot` (default `latest`/`today` depending on kind), optional `mode` (default `interactive`), optional `sources` (default all available), optional `depth` (default `standard`).

Flow:
1. Canonicalize name; scan for existing brief or alias hit. Refuse if found.
2. Bootstrap directory if absent (idempotent).
3. Resolve version/snapshot — for `kind: library | tool`, resolve semver via WebFetch if `latest`. For `kind: service | platform`, use today's date or caller-supplied snapshot ID.
4. Fan out source subagents per `references/source-prompts.md` using kind-aware source selection. Total budget 2400 tokens; per-source 600.
5. Assemble body in order per kind (TL;DR → When-to → Mental model → Common patterns → [Pricing model, Quotas & limits, IAM — service only] → Gotchas → Specifics worth remembering → Version history → References). Each section's line budget is in `references/brief-schema.md`.
6. Enforce per-kind line cap at write time (see "Body per-kind cap enforcement" below).
7. Atomically write `<ecosystem>/<name>.md`.
8. Append audit log row.
9. Regenerate README index atomically (tmpfile + rename); index grouped by kind then ecosystem.

### `research_new + clobber=true`

Used when the existing brief is fundamentally wrong ("v1 brief misread the service"). Requires a non-empty `reason` string. Refuses with `"clobber=true requires reason; pass reason=<one-line explanation>"` if missing.

Flow:
1. Compute next available `N` for `<name>.v<N>.md` (highest existing `vN` + 1; or 1 if none).
2. Rename current `<name>.md` → `<name>.v<N>.md`.
3. Audit log row: `clobber_archive ecosystem=<x> name=<y> archived_as=<name>.v<N>.md reason=<one-line>`.
4. Proceed with `research_new` flow as if the brief didn't exist.

Archived versions are NOT shown in the README index. They live in the ecosystem dir for provenance.

### `refresh_existing`

Inputs: `name`, `kind`, `ecosystem`, `caller`, optional `target_version`/`target_snapshot` (default upstream latest), optional `fresh=true`, optional `mode`.

Flow:
1. Read existing brief. Parse frontmatter. Compute `prior_v = version_last_seen` (library/tool) or `prior_s = snapshot_last_seen` (service/platform).
2. Resolve `target_version`/`target_snapshot`.
3. **Same-version no-op:** if target matches prior AND `fresh != true`, refuse with `"brief is current at <prior>; pass fresh=true to force re-research"`.
4. Fan out delta-scoped research using kind-aware source selection:
   - For library/tool: CHANGELOG between `prior_v` and `target_version`, migration guide, recent release notes.
   - For service: AWS docs "New" section, release announcements since `prior_s`.
   - For platform: release notes since `prior_s`.
5. Compose ONE new Version history row: `| <today> | <target> | <1-3-sentence "Key changes since prior"> |`.
6. Edit-mode body changes ONLY where the delta materially changes a section. Use `Edit` ops, not full rewrites.
7. Append target to `versions_explored` / `snapshots_explored`. For library/tool: set `version_last_seen = semver_max(versions_explored)`. For service/platform: set `snapshot_last_seen` = most recently added entry.
8. **Zero-diff guard:** if no body edits AND no new Version history row was added, do NOT bump `updated`. Audit log row still records `refresh_existing_noop`.
9. Otherwise set `updated = today`, write atomically, regen README, audit log row.

### `read_only`

Inputs: `name`, `kind`, `ecosystem`, optional `caller`.

Flow:
1. Probe `<ecosystem>/<name>.md` and (for matching aliases) other briefs in the ecosystem dir.
2. If found: parse frontmatter + body, compute staleness against `stale_threshold_days` (or ecosystem default if absent) and current date.
3. Return a **markdown digest** (NOT YAML) per "Read-only digest shape" below.
4. NEVER trigger research. NEVER write. NEVER side-effect the audit log.

Status enum: `ok | not_found | stale`. Stale is evaluated at READ time, not baked into the index.

### `archive`

Inputs: `name`, `kind`, `ecosystem`, `caller`, required `reason`.

Flow:
1. Read existing brief. Refuse if absent (`"brief not found for archive"`).
2. Refuse if `reason` missing or empty (`"intent=archive requires a reason"`).
3. Rename `<name>.md` → `<name>.archived-<YYYY-MM-DD>.md`.
4. Audit log row: `archive ecosystem=<x> name=<y> archived_as=<name>.archived-<date>.md reason=<one-line>`.
5. Regen README — archived briefs are dropped from the active index. They remain in the ecosystem dir for forensics.

## Read-only digest shape

Markdown, matching the knowledge-capture-style contract callers already consume:

```markdown
### tech-brief: react (js, v19.1.0, updated 2026-05-14)

**TL;DR:** <one-paragraph TL;DR extracted verbatim>

**Mental model (digest):** <2-3 sentences extracted from Mental model section>

**Top gotchas:**
- <bullet 1 from Gotchas>
- <bullet 2 from Gotchas>
- <bullet 3 from Gotchas>

**Related:** see also react-router, react-query

**Full brief:** `~/.claude/data/tech-briefs/js/react.md`
```

Stale form: `### tech-brief: react (js, v19.1.0, [stale], updated 2024-11-02)`. The `[stale]` marker sits between version and `updated`, comma-separated.

The "Related" footer is only emitted when the brief has a non-empty `see_also` field. The skill does NOT chase those links — the caller decides.

YAML was rejected here (opus C#2 + sonnet C#3 convergence): callers can't usefully consume a YAML struct since they're LLMs folding the digest into `handoff.md` or `research.md`. Markdown matches the existing knowledge-capture contract, which the same callers already handle.

## Append-only version history

The brief's Version history table is append-only. Re-research adds rows; rows are NEVER edited in place. The table grammar (per `references/brief-schema.md`):

```markdown
## Version history (newest first)
| Date examined | Version | Key changes since prior |
|---|---|---|
| 2026-05-14 | 19.1.0 | Async ref forwarding GA; Server Actions stable; ref no longer required as second arg of forwardRef. |
| 2025-09-02 | 19.0.0 | React Compiler beta; useFormStatus / useOptimistic shipped. |
| 2024-04-25 | 18.3.0 | (initial brief) |
```

Newest-first ordering is the convention for human review; the file is read top-to-bottom and the most relevant entry is on top.

## `version_last_seen` semver-max rule

`version_last_seen` is computed as `max(versions_explored)` under semver ordering at write time, NOT the last-appended element.

Rationale: a refresh against an older version (e.g. backporting a security investigation to v18.3.5 while v19.1.0 is current) appends to `versions_explored` but must NOT regress the "current version" pointer. Without semver-max, `version_last_seen` would drift backward and the README index + read API would lie.

Implementation: at every write, the skill computes `version_last_seen = semver_max(versions_explored)`. Tagged (non-semver) versions sort lexicographically as a fallback and emit a one-line warning in the audit log.

## README atomic regen

Every successful write triggers a README regeneration via tmpfile + rename:

1. Read all `<ecosystem>/<name>.md` frontmatter (skip `.archived-*.md`, skip `.v<N>.md`).
2. Compose index in memory (grouped by kind then ecosystem, newest first per group, with brief summary line).
3. Write to `README.md.tmp`.
4. `mv README.md.tmp README.md` (atomic on POSIX).

Two concurrent tech-brief writes may still race the read step in (1), but neither sees a partially written file. Last writer wins for the README content; both audit log rows are preserved (audit is append-only and write-ordered by OS).

The non-atomic alternative (open + write + close) was rejected: two parallel writes both regen, the last writer wins, and the first writer's listing is silently dropped from the index.

## Stale at READ time

The README index renders `updated: <date>` only. No pre-computed stale marker. Callers (and the `read_only` API) evaluate staleness against `updated + stale_threshold_days` at the moment of read.

Why: staleness is time-relative. Baking it into the README means the index becomes wrong the day after it's regenerated. Per-ecosystem defaults (from `.schema.json`):

| Ecosystem | Days |
|---|---|
| js, ts, npm | 180 (6 mo) |
| rust, swift | 270 (9 mo) |
| aws, gcp, azure | 270 (9 mo) |
| aws-service, gcp-service, azure-service | 180 (6 mo — services update frequently) |
| platform | 270 (9 mo) |
| python, go, java, kotlin, dotnet, ruby, php, gradle, maven, cli, db, infra, general | 365 (12 mo) |

Per-brief override via the frontmatter `stale_threshold_days` field. Negative or zero values are rejected at write time with `"stale_threshold_days must be a positive integer"`. Missing field falls through to ecosystem default.

The marker is advisory — entries are NEVER auto-refreshed. The marker informs callers; they choose to invoke `refresh_existing` (or not).

## Graceful degradation when sources fail

For `research_new`, the priority chain when upstream is light on docs:

1. Homepage doc page (WebFetch) — fail = skip section, log to `open-questions.md`.
2. Repo README (WebFetch on `https://raw.githubusercontent.com/<org>/<repo>/HEAD/README.md`) — fail = skip.
3. CHANGELOG.md / RELEASES.md / GitHub releases page — fail = fall back to `gh release list` and `gh api repos/<org>/<repo>/releases`.
4. If ALL of (1), (2), (3) fail: **refuse the brief** with `"insufficient sources for an honest brief; install the library locally and provide a manual TL;DR via interactive prompt"`. Do NOT produce a hallucinated brief.

For `refresh_existing`, if delta sources fail, append a Version history row with `Key changes since prior: "(no upstream changelog available; manual update required)"`. Do NOT silently overwrite body sections with assumptions.

## Body per-kind cap enforcement

Per-kind caps: `library`=200, `service`=280, `platform`=220, `tool`=180 (body lines, excluding frontmatter). Enforced at write time via a post-assemble check:

1. Assemble body in memory.
2. Count lines (excluding frontmatter).
3. Determine cap from `kind`. If over cap: drop sections in priority order — References first (lowest priority for cap), then Common patterns truncated to the most central pattern, then Mental model truncated to 1 paragraph. Each truncation emits a warning to the audit log: `cap_truncated section=<x> kept_lines=<n>`. The skill also prints: `brief exceeded cap; consider extracting <ecosystem>/<name>/<ref>.md`.
4. If still over cap after truncations: REFUSE the write. Surface the assembled body to the user (interactive mode) or `open-questions.md` (auto mode) and ask for guidance. The brief is NOT persisted in this state.

For `depth=deep` writes (≤350 lines), the same cap rule applies but with the explicit understanding that ref-file extraction is required up-front: the skill prompts the user to identify which content moves to `<name>/<ref>.md` before assembly.

## Audit log + rotation

Every write emits one line to `~/.claude/data/tech-briefs/.audit.log`:

```
2026-05-14T15:42:11Z research_new ecosystem=js library=react version=19.1.0 caller=user-direct
2026-05-14T15:55:02Z refresh_existing ecosystem=python library=boto3 version=1.35.0 from=1.34.0 caller=blueprint
2026-05-14T16:01:03Z refresh_existing_noop ecosystem=js library=zod version=3.22.4 caller=user-direct
2026-05-14T16:10:00Z clobber_archive ecosystem=js library=foo archived_as=foo.v1.md reason="v1 brief misread API surface"
2026-05-14T16:20:00Z archive ecosystem=python library=oldlib archived_as=oldlib.archived-2026-05-14.md reason="abandoned upstream, replaced by newlib"
2026-05-14T16:30:00Z cap_truncated section=References kept_lines=4
```

Append-only. Written BEFORE README regen so a corrupted README regen leaves the audit trail intact.

Rotation at 10 MiB (10485760 bytes):
1. Check size before append.
2. If size + new-line > 10 MiB: `mv .audit.log .audit.log.1` (single backup; `.audit.log.1` is overwritten on next rotation — no `.2` or beyond).
3. Start fresh `.audit.log` with the new line as the first row.

Rationale: unbounded growth is a foot-gun on long-lived `$HOME`. One backup preserves recent provenance; deeper history is logged in the brief frontmatter (`versions_explored`, `created`, `updated`) and in archived `.v<N>.md` / `.archived-<date>.md` files.

The audit log argument vs. frontmatter: opus R initially flagged it as potentially redundant. Kept because frontmatter `created`/`updated` only show LATEST timestamps; audit log preserves the full sequence, and `archive`/`clobber` events need a row that's separate from the brief's metadata (the brief itself may be moved/renamed).

## `see_also` cross-brief links

Briefs MAY carry a `see_also:` frontmatter field listing related briefs:

```yaml
see_also:
  - js/react-router
  - js/react-query
```

Read API surfaces them in the digest's "Related" footer. The skill does NOT auto-traverse them — the user/caller decides whether to read linked briefs. Read-only metadata; no back-edge in the cycle graph.

## MSP Go source rule

For ecosystem=`go` briefs in MSP-detected context (triangulated per composition-skills `decisions.md`: remote URL contains `nicusa`/`tylertech`, branch matches `^MSP-\d+/`, or `user.email` ends in `@tylertech.com`), `mcp__msp-go-api-framework__search` is added as a source for libraries whose names match MSP-internal patterns (heuristic: `msp-*`, internal package paths, or user opt-in in the interactive wave).

Generic Go libraries (`gorilla/mux`, `go-redis`) do NOT trigger this source. The MCP exists for in-scope libraries; using it elsewhere is noise.

## Cycle walk

Documented invocation paths confirmed cycle-safe:

| Path | Verdict |
|---|---|
| `blueprint → tech-brief (read_only) → knowledge-capture (read_only)` | knowledge-capture's caller= guard accepts non-knowledge-capture callers; no cycle |
| `pre-task-research → tech-brief (read_only)` | read-only never invokes pre-task-research; no cycle |
| `tech-brief → tech-brief` | `caller=tech-brief` is a no-op (log error, return); no cycle |
| `blueprint → tech-brief (research_new) → knowledge-capture (read_only)` | research_new reads knowledge-capture; knowledge-capture never invokes tech-brief; no cycle |
| `tech-brief → see_also (read_only)` | read-only metadata; not auto-traversed; no back-edge |

`caller=tech-brief` is treated as misuse: skill logs a single-line error to stderr and returns without acting.

## blueprint Phase 1 integration (one batched offer max)

Per `decisions.md`:
1. **Always read.** Scan repo manifests + user request for library names AND recognized cloud service names (Lambda, DSQL, S3, Step Functions, etc.). For each that has an existing brief, fold the `read_only` digest into `handoff.md` under "Known about this stack".
2. **ONE batched create offer per Phase 1.** Collect un-briefed tech items appearing in BOTH the request and the manifests/recognized names. Present a single `AskUserQuestion`:

   > Found N tech items with no brief: react-router, lambda, zod. Build briefs first? (yes — pick which / yes — all / no — defer)

   "defer" logs the un-briefed items to `.claude-plans/<active>/open-questions.md`.
3. **Auto-mode skips the create offer.** It defers all un-briefed items to `open-questions.md`. The user reviews after.

Without a cap, Phase 1 becomes a brief-creation funnel and actual planning backs up. ONE batched prompt keeps it manageable.

## pre-task-research integration (Priority 2, never dropped)

`tech-brief` is added to pre-task-research's source priority list as **Priority 2**, between Priority 1 (local-knowledge) and Priority 3 (Confluence). Like local-knowledge, tech-brief is NEVER dropped on budget overflow. Cap: top N=5 most-relevant briefs per research run (relevance = manifest hit OR mentioned in topic).

`research.md` section: `## Tech briefs (from ~/.claude/data/tech-briefs/)`. Each matched tech item contributes a one-bullet digest with a link to the full brief.

## Cross-machine sync (out of scope for v1)

`~/.claude/data/tech-briefs/` is local-machine state. v1 does NOT address sync. Documented as an anti-pattern: don't assume briefs are on another machine — if the user moves machines, they copy or symlink the dir themselves.

A future v2 may support a symlinked dotfiles repo (`ln -s ~/dotfiles/tech-briefs ~/.claude/data/tech-briefs`); the env-var override (`CLAUDE_TECH_BRIEFS_DIR`) leaves the door open without committing to a sync mechanism.

## Schema versioning

`.schema.json` carries `"schema_version": 2` (bumped from 1 for `kind` field and new ecosystems). The read API consults it on every read to confirm compatibility. Bumps require a written migration path and a version note in `references/schema.json`. No v1→v2 migration tooling — nothing existed at v1.

## Anti-patterns

- **Don't rewrite existing briefs.** Append-only history; edit-only body for material deltas. `research_new + clobber=true` is the explicit escape hatch, and it requires `reason`. Full rewrites without `clobber=true` are refused at the API surface.
- **Don't paraphrase upstream docs.** The brief is a mental model + gotchas. Paraphrasing upstream prose is bloat that goes stale faster than the upstream itself.

  > Example: a Python `requests` brief that re-explains HTTP verbs section by section. Brief should say "standard HTTP semantics, see docs" + the link.

- **Don't auto-trigger silently.** Default is interactive; auto-mode logs every inference to `open-questions.md`. Auto does not mean "bypass user gating" — it means "infer the inputs and log them for review".
- **Don't write per-repo briefs.** `knowledge-capture` (`.claude-knowledge/`) is the per-repo namespace. tech-brief is global (`~/.claude/data/tech-briefs/`). Conflating them defeats both skills.
- **Don't bloat past the per-kind body cap.** Caps: library=200, service=280, platform=220, tool=180. Enforced at write time. Overflow truncates References → Common patterns → Mental model; if still over, refuse. Don't route around the cap by extending sections "just this once".
- **Don't trust "latest" without naming it.** `version_last_seen` is required and is a resolved semver. The string "latest" is resolved at write time.
- **Don't run on every blueprint Phase 1.** Phase 1 reads + ONE batched offer. Mass-briefing every dep in a project is bloat.

- **Tutorial-creep.** Brief is not a tutorial. ≤4 patterns, each ≤15 lines.

  > Example: a 40-line "step-by-step setup" entry in Common patterns is wrong. Brief shows the shape; user clicks through for the full tutorial.

- **Code-listing-creep.** Snippets are illustrative, not copy-paste libraries.
- **Paraphrase-creep.** Don't restate the upstream docs section by section. Link them.
- **No-op refresh bumping `updated`.** Zero body diff + zero new version-history row = unchanged file. Don't bump `updated` to "freshen" the timestamp.
- **Conflation with knowledge-capture.** Library-scoped (cross-project) vs. repo-scoped (per-project). "Our team uses React with X custom hook pattern" is knowledge-capture. "React 19's Suspense behaves like Y" is tech-brief.

  > Example: "in this repo, all hooks live under `src/hooks/` and use the `useXxx` prefix" is knowledge-capture (pattern). "React hooks must be called in the same order every render" is tech-brief (gotcha).

- **Auto-traversing `see_also` links.** Read-only metadata. The skill does NOT chase links. Recursive traversal would explode token budgets and reintroduce cycle risk.
- **Cross-machine sync assumptions.** Out of scope for v1. Local-only state. The override env var leaves the door open without committing to a sync model.
- **Hallucinated briefs when sources fail.** If homepage + README + changelog all fail, REFUSE the brief. Do not synthesize one from training data. The whole skill's value is provenance; a sourceless brief is a confident lie.
- **Materializing the dir on first READ.** Read against a missing dir returns `status: not_found`. Bootstrap happens on first WRITE. Blueprint Phase 1 reading a fresh `$HOME` shouldn't materialize an empty `~/.claude/data/tech-briefs/`.
- **Atomic-write skips for README regen.** Always tmpfile + rename. Without it, concurrent writes lose listings silently.
- **Audit log unbounded growth.** 10 MiB rotation cap. Don't disable it to "preserve history" — the brief frontmatter and archived files carry the long-term provenance.
