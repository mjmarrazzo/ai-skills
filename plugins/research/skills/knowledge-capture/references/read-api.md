# read-api

The single READ operation knowledge-capture exposes. Callers (`blueprint` Phase 1, `pre-task-research`) fold the output into their own artifacts (handoff.md, research.md).

This is a long-lived contract. Bumps to the digest shape require a `.schema.json` version bump.

## Operation

```
read_entries(
  kind: "gotcha" | "pattern" | "stack-note" | "all" = "all",
  limit_total: int = 20,
  limit_per_kind: int = 6,
  since: ISO-date | null = null,
  output_path: <path> | null = null
) -> markdown digest
```

Implementation is grep over the three kind-files, using the pinned patterns in `entry-format.md`. The skill does not maintain an index — `README.md` is regenerated on every write but is for humans, not the read API.

If `output_path` is null, the digest is returned to the calling LLM as a string. If supplied, the skill writes the digest to that path and returns the path.

## Default limits

- `limit_total: 20` — across all kinds combined.
- `limit_per_kind: 6` — per kind section.

If a kind has more entries than `limit_per_kind`, the section header shows `(N of TOTAL)`:

```
### Gotchas (6 of 12)
```

The `(N of TOTAL)` always reflects the **non-superseded** total. Superseded entries are not counted toward total or shown in the digest by default.

If the combined total across kinds would exceed `limit_total`, the skill trims kinds proportionally, preserving at least 1 entry per non-empty kind. Stack-notes is the first to trim past `limit_per_kind` (they age fastest); gotchas is the last to trim (highest signal density).

## Ordering

- **Within a kind:** newest first by entry date (the `YYYY-MM-DD` prefix of the slug). Ties broken by file insertion order (later = newer).
- **Across kinds:** Gotchas first, then Patterns, then Stack notes. This order is fixed — readers like blueprint Phase 1 rely on it.

## Stale markers

Per-kind stale thresholds (pinned in `.schema.json`):

| Kind | Threshold |
|---|---|
| gotcha | 12 months |
| pattern | 12 months |
| stack-note | 3 months |

The threshold is measured from the entry's date (slug prefix) to the current date at read time.

A second source of staleness: **relative staleness.** If a newer entry shares ≥1 tag with an older entry of the same kind, the older one is also marked `[stale?]`. This catches the case where a newer pattern about `gradle` likely supersedes (informally) older gradle stack-notes.

Staleness is **advisory**. Entries are never auto-deleted. The marker surfaces inline in the digest so the user can decide.

The section header notes how many of the rendered entries are stale:

```
### Stack notes (1 of 3)  [stale?: 1]
```

If zero entries are stale, the `[stale?: N]` suffix is omitted.

## Superseded entries

Excluded from the digest by default. The kind-files retain the full history; the README index surfaces it for humans; the digest surfaces only the current head of each supersede chain.

When a supersede chain exists, the digest displays only the head (newest) entry, with its content. The fact that the head supersedes anything is NOT surfaced in the default digest — callers reading the digest care about current state, not history.

A future caller wanting the full history can pass `include_superseded: true` (deferred to dogfooding; not in v1).

## Empty digest

If `read_entries` finds zero entries (e.g. fresh repo, missing `.claude-knowledge/`, or all entries filtered out by `since`), the skill returns the **empty string**. No section header, no "(no entries yet)" placeholder. Callers like blueprint Phase 1 then skip the "Known about this repo" section entirely rather than emitting a misleading empty header.

This is load-bearing: the empty-digest contract is what lets every fresh clone behave the same as a populated one without special-casing.

## Missing directory

If `.claude-knowledge/` does not exist in the repo, `read_entries` returns the empty digest. No side effects. The directory is created on first WRITE, not first read.

## Schema version check

Before reading, the skill checks `.claude-knowledge/.schema.json` for `schema_version: 1`. If the version is unknown to this skill, the read FAILS with a clear error:

```
knowledge-capture: schema version <X> not supported by this skill (supports v1). Migrate .claude-knowledge/ first.
```

If `.schema.json` is missing on a populated directory (shouldn't happen in normal use, but defensive), the read assumes v1 and emits a warning. Writes refuse to proceed without `.schema.json` — they regenerate it first.

## Digest output shape (the load-bearing grammar)

```markdown
## Known about this repo (from .claude-knowledge/)

### Gotchas (3 of 12)
- **[2026-05-14] Gradle daemon hangs on M3 macs** — `rm -rf ~/.gradle/daemon/<v>/` and re-run; don't pkill. (tags: gradle, m3, daemon)
- **[2026-04-20] Yarn workspaces require root install** — `yarn install` at repo root before subdir tests. (tags: yarn, monorepo)
- **[2026-03-01] SQS visibility-timeout less than handler runtime causes double-delivery** — set timeout ≥ 6× p99. (tags: aws, sqs)

### Patterns (2 of 5)
- **[2026-04-01] Event handlers fan out via SNS topic** — every domain event publishes to one canonical SNS; handlers subscribe via SQS. (tags: aws, sns, events)
- **[2026-02-15] All HTTP handlers wrap in `withTrace()`** — adds Datadog span; do NOT call `tracer.startSpan` directly. (tags: datadog, tracing, http)

### Stack notes (1 of 3)  [stale?: 1]
- **[2025-08-01] [stale?] SAM local on port 5000** — port conflicts with Docker Desktop; use `-p 5001`. (tags: sam, docker)
```

Per-entry line shape:

```
- **[<date>] [stale?]?<title>** — <one-line lesson summary>. (tags: <tags>)
```

- Date: ISO `YYYY-MM-DD` from the slug.
- `[stale?]` marker: present only when the entry is past its per-kind threshold OR shares a tag with a newer same-kind entry.
- Title: verbatim from the heading line (no slug, no hash).
- Lesson summary: the first sentence of the entry's `**Lesson:**` field, truncated at the first period or 120 characters (whichever is first), with trailing punctuation re-added. NOT the full Lesson field.
- Tags: rendered in parentheses with `tags:` prefix and comma-separated values. Omitted if the entry has no tags.

## Folding into caller artifacts

**blueprint Phase 1:** the digest is appended to `handoff.md` under "Known about this repo" as the next section after the goal and context blocks. If the digest is empty (no entries), the section is **omitted entirely**. Callers MUST NOT add an empty section header.

**pre-task-research:** the digest is the first section of `research.md` under "Local knowledge". Same empty-handling rule — omit the section if empty.

**Other callers:** treat the digest as opaque markdown. Don't reformat. Don't reorder sections. Don't truncate further (the limits already trimmed at the source).

## Performance budget

A digest read is grep-bounded over three flat markdown files. Even at 1000 entries per kind, the read fits in a single tool call with no streaming. We do NOT cache the digest — every call re-greps. The files are small enough that caching would invite staleness bugs.

## What this API does NOT do

- It does not search by content. There is no full-text search; tags are the only structured filter (and we don't even support tag-filter in v1 — that's a v2 ask).
- It does not return entry IDs or any handle a caller could use to follow up. The digest is one-shot read for display.
- It does not expose the `source` block in the default digest. Provenance is in the kind-file for forensics; surfacing it in the digest would bloat every blueprint Phase 1 read.
- It does not validate that the supersede chain in the files is consistent. The write API enforces consistency at write time; the read API trusts the on-disk state.
