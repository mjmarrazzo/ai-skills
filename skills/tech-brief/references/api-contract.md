# api-contract

The 5-intent cross-skill contract. Callers (`blueprint`, `pre-task-research`, user-direct) invoke tech-brief with one of these intents. Long-lived contract; bumps require `schema_version` increment.

## Common envelope

Every invocation passes:

```yaml
intent: research_new | refresh_existing | read_only | archive   # required
name: <canonical-name>               # required (all intents)
kind: library | service | platform | tool  # required (all intents); drives sections, version semantics, source selection
ecosystem: <enum>                    # required (all intents)
caller: <skill-name>                 # required; cycle guard
mode: interactive | auto             # optional, default interactive
```

`caller=tech-brief` is a no-op cycle guard. The skill logs a single-line error to stderr and returns without acting.

`kind` must be one of `library | service | platform | tool`. Missing or invalid `kind` → refuse with `"kind '<x>' not in enum; valid values: library, service, platform, tool"`.

`ecosystem` must be a member of the closed enum in `.schema.json`:

```
js, ts, python, go, java, kotlin, rust, dotnet, ruby, php, swift,
aws, gcp, azure, gradle, maven, npm, cli, db, infra, general,
aws-service, gcp-service, azure-service, platform
```

Invalid ecosystem → refuse with `"ecosystem '<x>' not in enum; valid values: <list>"`.

## Intent 1: `research_new`

Create a fresh brief from scratch.

**Input payload:**

```yaml
intent: research_new
name: react-router
kind: library                    # required; library | service | platform | tool
ecosystem: js
caller: user-direct
target_version: 7.0.0          # optional, default "latest" (resolved at write time for library/tool); use target_snapshot for service/platform
target_snapshot: 2026-05-14    # optional; for kind=service|platform; date or milestone ID; default = today
sources: [homepage, readme, changelog, knowledge-capture]   # optional, default all available (kind-aware)
depth: standard                 # optional: shallow | standard | deep — default standard
clobber: false                  # optional, default false
reason: <string>                # required ONLY when clobber=true
mode: interactive               # optional, default interactive
```

**Validation rules:**

- `name` must be a valid canonical name (lowercase, kebab-case per ecosystem convention in `brief-schema.md`).
- `kind` must be a member of `library | service | platform | tool`. Refuse if missing or invalid.
- `ecosystem` must be a valid enum member.
- `target_version` of `"latest"` is resolved via WebFetch on the homepage/repo; the resolved semver is what gets persisted, NEVER the string `"latest"`. For `kind: service | platform`, use `target_snapshot` instead.
- `depth=deep` enables ≤350-line body cap and requires up-front user input on which content moves to ref files.
- `clobber=true` requires `reason` (non-empty string).

**Output:** path to the written brief + a one-line confirmation:

```
~/.claude/data/tech-briefs/js/react-router.md — wrote v7.0.0 (12 records across 4 sources)
```

**Refusal cases:**

| Condition | Refusal message |
|---|---|
| Brief already exists at the canonical path | `"brief exists at <path>; pass intent=refresh_existing, or research_new with clobber=true and reason"` |
| Brief exists under an alias hit | `"brief exists at <path> (matched alias '<alias>'); pass intent=refresh_existing"` |
| `kind` missing or not in enum | `"kind '<x>' not in enum; valid values: library, service, platform, tool"` |
| Ecosystem not in enum | `"ecosystem '<x>' not in enum; valid values: <list>"` |
| Required source (homepage + README + changelog) ALL fail | `"insufficient sources for an honest brief; install the library locally and provide a manual TL;DR via interactive prompt"` |
| Body exceeds per-kind line cap after truncation pass | `"brief exceeded <N>-line cap after truncation; assembled body surfaced for manual review (or open-questions.md in auto mode)"` |
| `clobber=true` without `reason` | `"clobber=true requires reason; pass reason=<one-line explanation>"` |

## Intent 2: `research_new + clobber=true`

Archive the existing brief and write a fresh one. Use when the existing brief is fundamentally wrong (e.g. "v1 brief misread the API surface").

**Input payload:** same as `research_new` plus:

```yaml
clobber: true
reason: "v1 brief described the legacy v6 API; new brief reflects v7's data-router model"
```

**Effect:**

1. Compute next available `N` for `<library>.v<N>.md` (highest existing `vN` + 1; or 1 if none).
2. `mv ~/.claude/data/tech-briefs/<ecosystem>/<library>.md ~/.claude/data/tech-briefs/<ecosystem>/<library>.v<N>.md`.
3. Audit log row:
   ```
   2026-05-14T16:10:00Z clobber_archive ecosystem=js library=react-router archived_as=react-router.v1.md reason="v1 brief described the legacy v6 API; ..."
   ```
4. Proceed with `research_new` flow as if the brief didn't exist.

The archived `.v<N>.md` is NOT shown in the README index. It lives in the ecosystem dir for provenance.

**Refusal cases:**

| Condition | Refusal message |
|---|---|
| No existing brief to clobber | `"no existing brief to clobber; use research_new without clobber=true"` |
| `reason` missing or empty | `"clobber=true requires reason; pass reason=<one-line explanation>"` |

## Intent 3: `refresh_existing`

Append a delta row + edit-mode body changes between the prior version and a target version.

**Input payload:**

```yaml
intent: refresh_existing
name: react
kind: library                    # required
ecosystem: js
caller: blueprint
target_version: 19.1.0          # optional (library/tool/platform), default upstream latest
target_snapshot: 2026-05-14    # optional (service/platform), default today or latest milestone
fresh: false                    # optional, default false (same-version no-op unless true)
mode: interactive               # optional, default interactive
```

**Validation rules:**

- `kind` must be present and valid. Refuse if missing.
- Brief must exist at `~/.claude/data/tech-briefs/<ecosystem>/<name>.md`. If missing, refuse.
- `target_version` of `"latest"` (or omitted) resolves via WebFetch for library/tool; for service/platform use `target_snapshot`.
- Same-version/snapshot refresh requires `fresh=true` to override the no-op guard.

**Delta detection:**

1. Read existing frontmatter → `prior_v = version_last_seen` (library/tool/platform) or `prior_s = snapshot_last_seen` (service).
2. Resolve target.
3. Fan out delta sources scoped to prior → target (kind-aware per `source-prompts.md`):
   - For library/tool: CHANGELOG between the two versions, migration guide, recent release notes.
   - For service: AWS docs "New" section, release announcements since `prior_s`.
4. Compose ONE new Version/Snapshot history row.
5. Edit body sections **only** where the delta materially changes them. Use `Edit` operations, not full rewrites.

**Zero-diff no-op:** if no body edits AND no new Version history row was added, do NOT bump `updated`. The audit log records `refresh_existing_noop`.

**Output:** path + delta summary:

```
~/.claude/data/tech-briefs/js/react.md — refreshed 19.0.0 → 19.1.0 (1 version row, 3 body edits)
```

Or for no-op:

```
~/.claude/data/tech-briefs/js/react.md — no changes (current at 19.1.0; pass fresh=true to force)
```

**Refusal cases:**

| Condition | Refusal message |
|---|---|
| Brief does not exist | `"no existing brief to refresh at <path>; use intent=research_new"` |
| `target_version == prior_v` AND `fresh != true` | `"brief is current at <prior_v>; pass fresh=true to force re-research"` |
| All delta sources fail | Append Version history row with `Key changes since prior: "(no upstream changelog available; manual update required)"`. Do NOT silently overwrite body. |
| `kind` missing or invalid | `"kind '<x>' not in enum; valid values: library, service, platform, tool"` |
| Body exceeds per-kind line cap after truncation pass | Same refusal as `research_new` |

## Intent 4: `read_only`

Return a markdown digest of an existing brief. NEVER triggers research. NEVER writes.

**Input payload:**

```yaml
intent: read_only
name: react
kind: library                    # required
ecosystem: js
caller: pre-task-research
```

**Output:** a markdown digest (NOT YAML):

```markdown
### tech-brief: react (js, v19.1.0, updated 2026-05-14)

**TL;DR:** React is a declarative component library for building user interfaces. v19 introduces Server Components, Actions, and stabilizes the new compiler. Most apps still use Function Components + Hooks; class components and legacy lifecycle methods are de-emphasized.

**Mental model (digest):** Components are pure functions of props that return JSX. React reconciles a virtual tree against the DOM. State lives inside components (`useState`) or context (`useContext`); side effects run in `useEffect` after commit.

**Top gotchas:**
- Stale closure inside `useEffect`: omitting a dependency captures the value at render-time. Lint with `react-hooks/exhaustive-deps`.
- `useState` initializer runs on every render — wrap in a function for expensive setup.
- Server Components don't run in StrictMode double-invoke.

**Related:** see also react-router, react-query

**Full brief:** `~/.claude/data/tech-briefs/js/react.md`
```

**Status enum** (returned with the digest as metadata):

| Status | Trigger | Digest content |
|---|---|---|
| `ok` | Brief found, not stale | Full digest as above |
| `not_found` | Brief absent (and no alias hit) | Empty string — caller skips the section |
| `stale` | Brief found, `updated + stale_threshold_days < today` | Digest with `[stale]` prepended: `### tech-brief: react (js, v19.1.0, [stale], updated 2024-11-02)` |

Stale is evaluated at READ time against `stale_threshold_days` (frontmatter override) OR the ecosystem default from `.schema.json`. Stale briefs still return the full digest — the marker informs the caller; it does NOT trigger refresh.

**Top gotchas digest rule:** the first 3 bullets of the Gotchas section, each trimmed to its first sentence (or 120 chars, whichever is first).

**Mental model digest rule:** the first 2-3 sentences of the Mental model section. Stop at the second sentence-end period unless the third sentence completes within a 25-word budget.

**Related footer:** rendered only when `see_also` is non-empty. Format: `**Related:** see also <lib1>, <lib2>`. The skill does NOT auto-traverse — caller decides.

**Refusal cases:** none. `read_only` never refuses; `not_found` is a status, not a refusal.

## Intent 5: `archive`

Rename a brief from `<name>.md` to `<name>.archived-<YYYY-MM-DD>.md` and drop from the README index. Used when a library is abandoned, replaced, or split into multiple packages, or when a service/platform is superseded.

**Input payload:**

```yaml
intent: archive
name: request
kind: library                    # required
ecosystem: js
caller: user-direct
reason: "deprecated 2020; replaced by node-fetch/undici/axios"
```

**Validation rules:**

- `kind` must be present and valid. Refuse if missing.
- Brief must exist. Refuse if absent.
- `reason` must be a non-empty string. Refuse if missing.

**Effect:**

1. `mv ~/.claude/data/tech-briefs/<ecosystem>/<name>.md ~/.claude/data/tech-briefs/<ecosystem>/<name>.archived-<YYYY-MM-DD>.md`.
2. Audit log row:
   ```
   2026-05-14T16:20:00Z archive ecosystem=js name=request archived_as=request.archived-2026-05-14.md reason="deprecated 2020; replaced by node-fetch/undici/axios"
   ```
3. Regen README index (the archived file is NOT included in the active index).

**Output:**

```
~/.claude/data/tech-briefs/js/request.md → request.archived-2026-05-14.md (archived)
```

**Refusal cases:**

| Condition | Refusal message |
|---|---|
| Brief does not exist | `"no brief to archive at <path>"` |
| `reason` missing or empty | `"intent=archive requires a reason"` |
| Brief is already archived (`.archived-*.md` exists, no `.md`) | `"brief already archived; no action taken"` |

Future `read_only` calls for an archived library return `status: not_found` — the archived file is NOT probed for reads. It exists in the ecosystem dir for forensics. A new `research_new` for the same canonical name is permitted and would create a fresh brief alongside the archived one.

## Cycle guard

`caller=tech-brief` on ANY intent → log a single-line error to stderr and return without acting. No skill in this monorepo invokes tech-brief recursively; this guard exists for the case where a future skill chains through and accidentally lands back here.

## Sibling-installed check

Callers MUST probe before invoking:

```bash
test -f ~/.claude/skills/tech-brief/SKILL.md || \
  ls ~/.claude/plugins/cache/**/skills/tech-brief/SKILL.md 2>/dev/null
```

If absent, the caller proceeds without the brief and mentions the missing sibling once. Do NOT block on a missing sibling.
