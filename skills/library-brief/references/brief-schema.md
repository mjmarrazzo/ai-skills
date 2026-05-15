# brief-schema

Pinned format spec for `~/.claude/data/library-briefs/<ecosystem>/<library>.md`. This is the long-lived parsing contract that callers (`blueprint` Phase 1, `pre-task-research`, the read-only API) rely on. Bumps require a `schema_version` increment in `.schema.json` and a migration path.

## File layout

```markdown
---
<YAML frontmatter — fields below>
---

# <Display name> — Brief

## TL;DR
## When to reach for it / When NOT to
## Mental model
## Common patterns
## Gotchas
## Version history (newest first)
## References
```

Order is fixed. The level-1 heading appears once after frontmatter close. Every `##` section is required even when empty; an empty section emits `_none yet_` so the absence is intentional rather than missing.

## Frontmatter fields

YAML between two `---` markers. Required fields are enforced at write time; the skill refuses writes missing any required field.

| Field | Required | Type | Example | Notes |
|---|---|---|---|---|
| `name` | yes | string | `react` | canonical lowercase kebab-case; matches the file basename |
| `display_name` | yes | string | `React` | human-friendly form for the digest heading |
| `ecosystem` | yes | enum | `js` | must match the closed enum in `.schema.json` |
| `homepage` | yes | URL | `https://react.dev` | resolves on WebFetch during research |
| `repo` | no | URL | `https://github.com/facebook/react` | omit when no public repo |
| `aliases` | no | list[string] | `[react-router-dom]` | alternative names; the skill probes these on read and `research_new` |
| `versions_explored` | yes | list[semver-or-tag] | `[18.3.0, 19.0.0, 19.1.0]` | append-only; insertion order = research order |
| `version_last_seen` | yes | semver-or-tag | `19.1.0` | computed as `semver_max(versions_explored)` at write time, NOT last-appended |
| `created` | yes | ISO date | `2025-09-02` | write date of the initial `research_new` |
| `updated` | yes | ISO date | `2026-05-14` | bumped on any write that materially changes the file; no-op refresh does NOT bump |
| `tags` | no | list[string] | `[ui, frontend, hooks]` | ≤6 tags; lowercase ASCII letters/digits/hyphens |
| `stale_threshold_days` | no | int>0 | `180` | overrides ecosystem default from `.schema.json`; rejected if ≤0 |
| `see_also` | no | list[string] | `[js/react-router, js/react-query]` | `<ecosystem>/<library>` form; surfaced in digest "Related" footer; NOT auto-traversed |
| `schema_version` | yes | int | `1` | matches `.schema.json` schema_version |

## Body section ordering and line budgets

The 200-line cap is **total** body lines (excluding frontmatter). Section budgets are advisory targets that, summed, leave headroom under the cap. If a section is empty, it emits `_none yet_` and counts as 1 line.

| Section | Target lines | Notes |
|---|---|---|
| TL;DR | ≤5 (one paragraph) | What the library is, in one paragraph. No bullets. |
| When to reach for it / When NOT to | ≤8 (bullets) | Two short sub-blocks: when to use, when NOT to. |
| Mental model | ≤40 (2-4 paragraphs) | Core concepts a user must hold in their head. Prose. |
| Common patterns | ≤60 (≤4 patterns, each ≤15 lines including code) | Illustrative snippets, not copy-paste libraries. ≤15 lines per snippet. |
| Gotchas | ≤30 (≤8 bullets, each ≤2 lines) | One sentence per gotcha, optionally with a fix-link. |
| Version history (newest first) | append-only table, no cap (rows are short) | One row per researched version. Append-only. |
| References | ≤15 (≤8 URLs + light annotation) | Pinned canonical URLs. ≤8 entries. |

Total target: ≈160 lines, leaving ≈40 lines of headroom under the 200-line cap.

`depth=deep` writes raise the soft cap to 350 lines; ref-file extraction is required up-front under `<ecosystem>/<library>/<ref-1>.md` etc., linked from the main brief.

## 200-line cap rule

Enforced at write time. Sequence:

1. Assemble body in memory.
2. Count non-frontmatter lines.
3. If >200, truncate in priority order:
   - **First:** drop References past the top 4 entries.
   - **Second:** truncate Common patterns to the single most-central pattern.
   - **Third:** truncate Mental model to 1 paragraph.
   Each truncation emits an audit log row: `cap_truncated section=<x> kept_lines=<n>`.
4. If still >200: REFUSE the write. Surface the assembled body to the user (interactive mode) or `open-questions.md` (auto mode). The brief is NOT persisted.

Pattern snippets longer than 15 lines are auto-truncated to the first 15 with `# ...` trailing comment.

## Version history table

```markdown
## Version history (newest first)
| Date examined | Version | Key changes since prior |
|---|---|---|
| 2026-05-14 | 19.1.0 | Async ref forwarding GA; Server Actions stable; ref no longer required as second arg of forwardRef. |
| 2025-09-02 | 19.0.0 | React Compiler beta; useFormStatus / useOptimistic shipped. |
| 2024-04-25 | 18.3.0 | (initial brief) |
```

Newest-first ordering by insertion. Each row is a single line of markdown table. Append-only — never edit a prior row. The `Key changes since prior` cell is 1-3 sentences in plain English ("what changes for the user"), not a changelog dump.

## Worked examples

### Example 1: fresh `research_new` for `react` v19.1.0

```markdown
---
name: react
display_name: React
ecosystem: js
homepage: https://react.dev
repo: https://github.com/facebook/react
aliases: []
versions_explored: [19.1.0]
version_last_seen: 19.1.0
created: 2026-05-14
updated: 2026-05-14
tags: [ui, frontend, hooks]
stale_threshold_days: 180
see_also: [js/react-router, js/react-query]
schema_version: 1
---

# React — Brief

## TL;DR
React is a declarative component library for building user interfaces. v19 introduces Server Components, Actions, and stabilizes the new compiler. Most apps still use Function Components + Hooks; class components and legacy lifecycle methods are de-emphasized.

## When to reach for it / When NOT to
- Reach for: stateful UI with frequent interaction, ecosystem of compatible libraries (router, query, forms), Server Components when the app has a Next.js/Remix-style server framework.
- NOT for: static content sites (use Astro/MDX), simple form pages (vanilla + a sprinkle), or apps where bundle size dominates the budget (consider Preact/Solid).

## Mental model
Components are pure functions of props that return JSX. React reconciles a virtual tree against the DOM. State lives inside components (via `useState`) or in a context (`useContext`); side effects run in `useEffect` after commit.

Hooks must run in the same order every render — never inside conditionals or loops. The dependency array of `useEffect`/`useMemo`/`useCallback` is the contract for re-runs; getting it wrong is the most common bug class.

Server Components run on the server and emit serialized output to the client; they cannot use hooks or state. Client Components (`"use client"`) opt into interactivity. The mental shift in v19 is "default to server; opt into client".

## Common patterns
- State + effect:
  ```tsx
  const [count, setCount] = useState(0);
  useEffect(() => { document.title = `${count}`; }, [count]);
  ```
- Custom hook (encapsulate effect logic):
  ```tsx
  function useDebounced<T>(value: T, ms: number) {
    const [v, setV] = useState(value);
    useEffect(() => {
      const t = setTimeout(() => setV(value), ms);
      return () => clearTimeout(t);
    }, [value, ms]);
    return v;
  }
  ```
- Server Action (v19):
  ```tsx
  async function submit(formData: FormData) {
    "use server";
    await db.users.create({ name: formData.get("name") });
  }
  ```
- `useOptimistic` for optimistic UI updates without manual rollback (v19).

## Gotchas
- Stale closure inside `useEffect`: omitting a dependency captures the value at render-time. Lint with `react-hooks/exhaustive-deps`.
- `useState` initializer runs on every render — wrap in a function for expensive setup: `useState(() => compute())`.
- Server Components don't run in StrictMode double-invoke; bugs that depend on double-call won't reproduce server-side.
- `useEffect` cleanup runs BEFORE the next effect, not after the previous render. Order matters for subscriptions.
- `ref` is now a regular prop in v19; legacy `forwardRef` shape still works but is no longer required.
- Server Actions run in a different process; closing over client-side variables won't work.

## Version history (newest first)
| Date examined | Version | Key changes since prior |
|---|---|---|
| 2026-05-14 | 19.1.0 | (initial brief) |

## References
- Docs: https://react.dev
- Server Components RFC: https://github.com/reactjs/rfcs/blob/main/text/0188-server-components.md
- v19 upgrade guide: https://react.dev/blog/2024/04/25/react-19-upgrade-guide
- Rules of Hooks: https://react.dev/reference/rules/rules-of-hooks
```

### Example 2: `refresh_existing` delta from React v19.0 → v19.1

The brief existed at v19.0.0 (`updated: 2025-09-02`). A refresh to v19.1.0 produces:

**Frontmatter diff (before → after):**

```diff
-versions_explored: [18.3.0, 19.0.0]
-version_last_seen: 19.0.0
-updated: 2025-09-02
+versions_explored: [18.3.0, 19.0.0, 19.1.0]
+version_last_seen: 19.1.0
+updated: 2026-05-14
```

**Version history table — appended row at TOP (newest first):**

```diff
 ## Version history (newest first)
 | Date examined | Version | Key changes since prior |
 |---|---|---|
+| 2026-05-14 | 19.1.0 | Async ref forwarding GA; ref no longer required as second arg of forwardRef; minor Server Actions hardening. |
 | 2025-09-02 | 19.0.0 | React Compiler beta; useFormStatus / useOptimistic shipped. |
 | 2024-04-25 | 18.3.0 | (initial brief) |
```

**Body edits (only where the delta materially changes content):**

In Gotchas, an existing bullet is superseded by a more accurate one. Append-only history means the original is NOT edited in place — the refresh adds a NEW bullet:

```diff
 ## Gotchas
 - Stale closure inside `useEffect`: omitting a dependency captures the value at render-time. Lint with `react-hooks/exhaustive-deps`.
 - `useState` initializer runs on every render — wrap in a function for expensive setup: `useState(() => compute())`.
 - Server Components don't run in StrictMode double-invoke; bugs that depend on double-call won't reproduce server-side.
 - `useEffect` cleanup runs BEFORE the next effect, not after the previous render. Order matters for subscriptions.
-- `forwardRef` is required to receive a `ref` prop in v19.0.
+- `ref` is now a regular prop in v19.1+; legacy `forwardRef` shape still works but is no longer required.
 - Server Actions run in a different process; closing over client-side variables won't work.
```

The Mental model section gets ONE sentence edit reflecting the ref change:

```diff
 ## Mental model
-Server Components run on the server and emit serialized output to the client; they cannot use hooks or state. Client Components (`"use client"`) opt into interactivity. In v19, `ref` must still go through `forwardRef`.
+Server Components run on the server and emit serialized output to the client; they cannot use hooks or state. Client Components (`"use client"`) opt into interactivity. The mental shift in v19 is "default to server; opt into client". As of v19.1, `ref` is a regular prop.
```

Other sections (TL;DR, When to reach for it, Common patterns, References) are unchanged — the v19.0 → v19.1 delta doesn't materially affect them. The skill does NOT rewrite them.

Audit log row:

```
2026-05-14T15:42:11Z refresh_existing ecosystem=js library=react version=19.1.0 from=19.0.0 caller=user-direct
```

### Example 3: `archive` rename of a deprecated library

The library `request` (Node HTTP client) is deprecated and abandoned. User invokes:

```yaml
intent: archive
library: request
ecosystem: js
caller: user-direct
reason: "deprecated 2020; replaced by node-fetch/undici/axios"
```

Effect:
- `~/.claude/data/library-briefs/js/request.md` → `~/.claude/data/library-briefs/js/request.archived-2026-05-14.md` (rename, no content change).
- README index regen drops `request` from the active js section.
- Audit log row:
  ```
  2026-05-14T16:20:00Z archive ecosystem=js library=request archived_as=request.archived-2026-05-14.md reason="deprecated 2020; replaced by node-fetch/undici/axios"
  ```

Future `read_only` calls for `library: request, ecosystem: js` return `status: not_found` (the archived file is NOT probed for reads — it's forensic state only). A new `research_new` for `request` is permitted and would create a fresh `request.md` (the archived file is in the dir for provenance, not the active path).
