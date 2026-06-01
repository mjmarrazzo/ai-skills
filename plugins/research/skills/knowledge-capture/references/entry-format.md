# entry-format

Pinned format spec for entries in `.claude-knowledge/{gotchas,patterns,stack-notes}.md`. This is the parsing contract every reader (this skill, blueprint Phase 1, pre-task-research, any future caller) relies on. Bumps to this format require a `.schema.json` version bump and a migration path.

## File structure

Each kind-file is plain markdown:

```markdown
# <Kind name>

## <slug> — <title>  [tags: ...]
**Context:** ...
**Lesson:** ...
**Source:** session: ..., files: [...], commit: ...

## <slug> — <title>  [tags: ...]
...
```

Entries are separated by a blank line. The level-1 heading (`# Gotchas`, `# Patterns`, `# Stack notes`) is the file header — present once at the top, never repeated.

Order on disk is **append-only insertion order** (newest at the bottom of the file). The README index handles newest-first display ordering for human consumption.

## Slug

Format: `<YYYY-MM-DD>-<kebab(title)>-<6char-content-hash>`.

- Date: ISO `YYYY-MM-DD`, the write date (NOT the date the underlying issue was first observed — captures stamp themselves at write time).
- Kebab(title): lowercase, ASCII letters and digits only, separators `-`. Strip punctuation; collapse runs of `-` to a single `-`; trim leading/trailing `-`. Max 60 characters of title in the slug; truncate at a word boundary.
- 6-char content hash: lowercase hex slice over `sha256(context + "\n" + lesson + "\n" + source_block)`, taking the first 6 characters of the hex digest.

Two writes with identical titles on the same day still produce different slugs as long as their body differs. Slugs are stable references — superseded chains use them verbatim.

Example: title "Gradle daemon hangs on M3 macs" written 2026-05-14 with body hash starting `a1b2c3...` →

```
2026-05-14-gradle-daemon-hangs-on-m3-macs-a1b2c3
```

## Heading line

```
## <slug> — <title>  [tags: tag1, tag2]
```

- Literal `## ` prefix (level-2 heading).
- Separator between slug and title is **em-dash** (U+2014, `—`), with single spaces on either side. NOT a hyphen-minus (`-`), NOT an en-dash (U+2013).
- Title is the human-readable phrase. ≤80 characters. MUST NOT contain `[` or `]` (those are reserved for the tag bracket on the same line).
- Tags bracket: literal `  [tags: ` (two spaces, `[tags: `), comma-separated tag names, literal `]`. ≤4 tags. Tags are lowercased ASCII; we do not normalize case across entries (treat `gradle` and `Gradle` as distinct, leave it to the user). Omit the bracket entirely when there are no tags.

## Body fields

Each entry body has exactly three required field lines, in order:

```
**Context:** <one sentence — what was happening at the moment of capture>
**Lesson:** <one or two sentences — the takeaway>
**Source:** session: `<session-marker>`, files: [<path>, <path>], commit: `<sha-or-null>`
```

And one optional field line (when superseding an earlier entry):

```
**Supersedes:** <slug-of-prior-entry>
```

When present, `Supersedes:` is the FIRST body line (above Context).

Field rules:

- Field prefix is bold-wrapped literally: `**Context:**`, `**Lesson:**`, `**Source:**`, `**Supersedes:**`.
- Single space after the colon.
- `Context` and `Lesson` are free-form text; line breaks within a field are tolerated by the parser but discouraged — keep each field to a single line where possible.
- `Source.files` is a markdown-style list inside square brackets, comma-separated. Paths are repo-relative. Empty list `[]` is legal.
- `Source.commit` is either a hex SHA in backticks or the literal `null` (unquoted) when the capture happened outside a git context.
- `Source.session_marker` is a free-form caller-supplied string, conventionally wrapped in backticks.

## Pinned grep patterns

These are the **canonical** patterns every reader uses. Do not invent variations.

```bash
# Match an entry heading (slug + em-dash + title + optional tag bracket):
grep -nE "^## [0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]+-[a-f0-9]{6} — " <file>

# Extract the tag bracket from a heading line:
grep -oE "\[tags: [^]]+\]" <heading-line>

# Match a body field line (one of Context, Lesson, Source, Supersedes):
grep -E "^\*\*(Context|Lesson|Source|Supersedes):\*\* " <file>

# Match only Supersedes lines (to follow chains):
grep -E "^\*\*Supersedes:\*\* " <file>

# Extract source.commit:
grep -oE "commit: \`[a-f0-9]+\`|commit: null" <source-line>

# Extract source.files (the path list inside square brackets):
grep -oE "files: \[[^]]*\]" <source-line>
```

The em-dash in the heading regex is U+2014. When constructing a regex programmatically, use the literal character; do not substitute `-` or `—` escapes in shell.

## Title charset rules

Enforced at write time. The skill rejects titles violating any of these and asks the user to revise:

- Length: 1-80 characters (inclusive).
- Forbidden characters: `[`, `]`, newline, tab. (Brackets are reserved for the tag suffix; newlines/tabs break line-prefix parsing.)
- Recommended: avoid markdown special characters (`*`, `_`, `` ` ``) inside titles for legibility; not forbidden.
- Em-dashes inside titles are fine — the parser splits on the FIRST ` — ` (space-em-dash-space) after the slug, so additional em-dashes later in the title are preserved.

## Tag rules

- ≤4 tags per entry.
- Each tag: 1-30 characters, lowercase ASCII letters/digits/hyphens.
- No comma inside a tag (commas are the in-bracket separator).
- The skill does NOT normalize tag spelling. `gradle`, `Gradle`, `gradle-8` are distinct. Tags are conventions, not taxonomy.

## Supersede mechanics

To correct a prior entry, append a new entry that:

1. Has its own fresh slug (new date or new content hash — the supersede chain doesn't reuse slugs).
2. Begins its body with `**Supersedes:** <slug-of-prior-entry>` as the first body field.
3. Provides full Context, Lesson, Source as if it were a fresh entry (do NOT abbreviate — readers may surface this entry standalone).

The original entry is **never edited**. It stays exactly as written. The README index marks it `[superseded by <new-slug>]` and sorts it below current entries within its kind section.

If the supersede target slug is missing from any kind-file, or matches multiple entries (shouldn't happen with the content-hash slug rule, but defensive), the skill REFUSES the write and asks the user to disambiguate. We do not guess which entry to chain.

Stale-marker logic explicitly **skips** superseded entries: a superseded entry is not stale, it's intentionally archived. Only the current (head-of-chain) entry can carry a `[stale?]` marker in the digest.

## Worked examples

### Gotcha

```markdown
## 2026-05-14-gradle-daemon-hangs-on-m3-macs-a1b2c3 — Gradle daemon hangs on M3 macs  [tags: gradle, m3, daemon]
**Context:** Running `./gradlew :app:build` after `mise use java@21` left an orphan daemon pinned to the previous JDK.
**Lesson:** `rm -rf ~/.gradle/daemon/<version>/` and re-run. Don't `pkill -f gradle` — it corrupts the lock file and forces a full re-resolve.
**Source:** session: `debug-loop-task-3`, files: [build.gradle.kts, gradle/wrapper/gradle-wrapper.properties], commit: `abc1234`
```

### Pattern

```markdown
## 2026-04-01-event-handlers-fan-out-via-sns-topic-d4e5f6 — Event handlers fan out via SNS topic  [tags: aws, sns, events]
**Context:** Investigating how `OrderPlaced` reaches the email sender service.
**Lesson:** Every domain event publishes to one canonical SNS topic; handlers subscribe via SQS. Don't add direct SQS→Lambda wiring — it bypasses the audit log subscription.
**Source:** session: `blueprint-phase1-exploration`, files: [infra/sns.tf, services/email/main.go], commit: `def5678`
```

### Stack-note

```markdown
## 2026-05-01-sam-local-conflicts-with-docker-desktop-port-5000-1a2b3c — SAM local conflicts with Docker Desktop port 5000  [tags: sam, docker, local-dev]
**Context:** `sam local start-api` failed on macOS with "port already in use" after Docker Desktop's update enabled its own service on 5000.
**Lesson:** Run SAM on an alternate port: `sam local start-api -p 5001` and update `gradle.properties`'s `localBaseUri=http://localhost:5001`. Disabling the Docker setting also works but is sticky across reboots.
**Source:** session: `debug-loop-task-1`, files: [tests/gradle.properties], commit: `null`
```

### Supersede chain

The original entry — left untouched after correction:

```markdown
## 2026-03-15-yarn-workspaces-require-root-install-1a2b3c — Yarn workspaces require root install before subdir tests  [tags: yarn, monorepo]
**Context:** Running `yarn test` in `apps/web/` after `git checkout` failed because root deps weren't hoisted yet.
**Lesson:** Always `yarn install` at the repo root before running tests in a workspace.
**Source:** session: `debug-loop-task-2`, files: [package.json, apps/web/package.json], commit: `abc1234`
```

The correcting entry — appended later:

```markdown
## 2026-05-10-pnpm-migration-replaces-yarn-workspaces-rule-4d5e6f — pnpm migration replaces yarn workspaces rule  [tags: pnpm, monorepo]
**Supersedes:** 2026-03-15-yarn-workspaces-require-root-install-1a2b3c
**Context:** Repo migrated to pnpm. The "yarn install at root" rule no longer applies; `pnpm install` at root has the same hoisting behaviour but `pnpm -F web test` runs without requiring it explicitly.
**Lesson:** After the pnpm migration: `pnpm -F <workspace> <task>` works from anywhere. The prior root-install rule is obsolete.
**Source:** session: `execute-plan-task-7`, files: [pnpm-workspace.yaml, .npmrc], commit: `def5678`
```

Both entries are visible in the file forever. The README index displays the supersede relationship; the digest API surfaces only the head entry by default.
