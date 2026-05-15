---
name: knowledge-capture
description: Use this skill whenever the user says "remember this", "save that", "worth knowing for next time", "note that down", "lesson learned", "this bit me", or is wrapping up work and reflecting on what was learned. Also auto-invoked by `debug-loop` at non-obvious root cause, by `execute-plan` at end-of-plan with blocked-task notes, by `finish-branch` at the pre-flight gate, and read by `blueprint` Phase 1 and `pre-task-research` on entry. Writes to a per-repo gitignored `.claude-knowledge/`. NEVER writes silently — always asks the user before persisting. Default mode is interactive; autonomous opt-in via `mode=auto` or phrase "go full auto". Skip only when the user explicitly opts out ("don't bother", "skip the knowledge capture", "I'll remember it") or the work is a trivial one-line edit.
---

# Knowledge Capture

A per-repo, gitignored knowledge log that accumulates the small lessons a session is going to learn anyway — what bit us, how this codebase works, which tools have quirks — so the NEXT session doesn't relearn them. Never silently. Always at the user's word.

**Announce at start:** "Using knowledge-capture to record this so the next session has it."

## When to trigger

Auto-trigger when:
- User says "remember this", "save that for later", "worth knowing", "note that down", "this bit me", "lesson learned", or any phrase reflecting on something the session just discovered.
- `debug-loop` reaches Phase 7 with a non-obvious root cause (fix in a different module than the symptom, or more than one hypothesis required).
- `execute-plan` reaches end-of-plan with one or more tasks that were `BLOCKED` or exceeded their time budget.
- `finish-branch` reaches its pre-flight gate (single prompt: "anything new worth remembering before opening this PR?").
- `blueprint` Phase 1 or `pre-task-research` is gathering context for a new request — these READ the kind-files.

Skip when: user explicitly opts out ("don't bother", "skip the knowledge capture", "I'll remember it") or the work is a one-line edit with nothing to record.

## Default mode and autonomous opt-in

**Default: interactive.** Sibling-skill writes are queued during the session and presented as one batched prompt at session end (typically by `finish-branch` at its pre-flight gate). `TodoWrite` surfaces "N pending captures" mid-session so the user sees what's pending without being asked yet.

**Autonomous (opt-in):** triggered by explicit phrase ("go full auto", "autonomous", "no questions", "skip the gates") or caller param `mode=auto`. In auto mode, proposed entries are logged to `.claude-plans/<active>/open-questions.md` (or `./.claude-results/<ts>/open-questions.md` ad-hoc) as deferred reviewables. NO entry is persisted to the kind-files without an explicit user ack. The "always ask" rule is mode-agnostic for v1.

## Directory layout (pinned)

The knowledge tree lives at the **repo root** (cwd if not in a git repo), NOT inside `.claude-plans/<workspace>/`. Knowledge is per-repo, not per-workspace.

```
.claude-knowledge/
├── README.md       # auto-regenerated index — one line per entry, newest-first, superseded at bottom
├── gotchas.md      # "thing that bit me, what to do" — append-only
├── patterns.md     # "this is how X works in this repo" — append-only
├── stack-notes.md  # tooling quirks (gradle, mise, SAM, AWS profiles) — append-only
└── .schema.json    # schema version + per-kind stale thresholds + title charset rules
```

The directory is created on the **first WRITE** in a repo, not on first read. First-read on a missing dir returns an empty digest with no side effects. See `references/entry-format.md` and `references/schema.json` for the exact bootstrap.

## Read API (callers fold this into their own artifacts)

One operation: a markdown digest, grep-parsed from the kind-files. Full grammar in `references/read-api.md`.

Defaults: 20 entries total, 6 per kind, newest first, superseded entries excluded. Per-kind stale thresholds: gotcha 12mo, pattern 12mo, stack-note 3mo (advisory marker, never auto-delete). Empty result emits NO section at all — callers just skip it rather than printing "Known about this repo: nothing yet."

## Write API (the cross-skill contract)

Every cross-skill write passes a structured payload. ALL fields except `tags` are required. The skill rejects writes missing required fields:

```yaml
caller: <skill-name>            # required — also used for cycle guard
kind: gotcha | pattern | stack-note   # required
proposed:
  title: <string>               # required, ≤80 chars, no `[` or `]`
  context: <string>             # required, one sentence — what was happening
  lesson: <string>              # required, ≤2 sentences — the takeaway
  tags: [<string>, ...]         # optional, ≤4 tags
source:                         # required block — without it, entries become contextless
  files: [<path>, ...]          # git diff --name-only over the relevant range
  commit: <sha-or-null>         # git rev-parse HEAD
  session_marker: <string>      # caller-supplied, e.g. "debug-loop-task-3"
```

The `source` block is the graveyard guard. Without it, a year-old entry has no provenance and a future LLM cannot validate whether it's still true. The skill REJECTS writes missing required fields and prints what's missing — do not try to route around it.

## Entry format (pinned)

```markdown
## 2026-05-14-gradle-daemon-hang-a1b2c3 — Gradle daemon hangs on M3 macs  [tags: gradle, m3, daemon]
**Context:** Running `./gradlew :app:build` after `mise use java@21` left a daemon on the old JDK.
**Lesson:** `rm -rf ~/.gradle/daemon/<v>/` and re-run. Don't `pkill -f gradle` — corrupts the lock file.
**Source:** session: `debug-loop-task-3`, files: [build.gradle.kts], commit: `abc1234`
```

Slug: `<YYYY-MM-DD>-<kebab(title)>-<6char-content-hash>`. Separator is em-dash (U+2014). Titles MUST NOT contain `[` or `]`. Full grammar, grep patterns, and supersede chain examples in `references/entry-format.md`.

**Append-only.** Corrections supersede:

```markdown
## 2026-05-14-gradle-daemon-hang-b2c3d4 — Gradle daemon hangs on M3 macs  [tags: gradle, m3, daemon]
**Supersedes:** 2026-05-14-gradle-daemon-hang-a1b2c3
**Context:** ...
**Lesson:** ...
```

NEVER edit a prior entry in place. The history is the data.

## Confirmation flow

The skill NEVER writes silently. Three paths converge on one rule:

1. **Sibling-skill write (interactive mode):** queue the proposed entry. Surface via `TodoWrite` as "pending capture". Batch with other queued entries and present at session end via `AskUserQuestion`:

   > I noted 3 things worth remembering during this session:
   > 1. [debug-loop] Gradle daemon hangs on M3 macs — kill ~/.gradle/daemon
   > 2. [execute-plan] Yarn workspaces require root install before subdir tests
   > 3. [debug-loop] SAM local port conflict when Docker Desktop running
   >
   > Save these? (Yes all / Choose each / Skip all / Edit)

2. **Sibling-skill write (auto mode):** append to `.claude-plans/<active>/open-questions.md` as a deferred reviewable. No prompt mid-session. User reviews at end of run.

3. **User-initiated phrase** ("remember this", "save that"): one immediate question — "OK, what's the gotcha (or pattern or stack-note)?" — synthesize the entry, queue it the same way a sibling-skill write would be queued. Same batched gate at session end. The user already asked, so we ask back; we still don't persist without an ack.

`caller=knowledge-capture` is a no-op (cycle guard). Log a single-line error to stderr and return without acting.

## First-write bootstrap

On the first write in a repo:

1. `mkdir -p .claude-knowledge/`.
2. Write `.schema.json` from `references/schema.json` (literal initial content, schema-version 1).
3. Write empty `gotchas.md`, `patterns.md`, `stack-notes.md` with single-line headers.
4. Write empty `README.md` with the auto-index header.
5. Append `.claude-knowledge/` to `.gitignore` if absent. Create `.gitignore` if missing in a git repo.
6. Then append the actual entry.

Idempotent — subsequent writes skip steps 1-5.

## Active workspace and ad-hoc behaviour

`.claude-knowledge/` is **per-repo**, at the repo root, NOT under `.claude-plans/<workspace>/`. Knowledge spans workspaces.

Auto-mode deferred entries DO go to the active workspace's `open-questions.md`, resolved per the canonical algorithm in `.claude-plans/2026-05-14-composition-skills/decisions.md` (briefly: `WORKSPACE_PATH` first, then enumerate `.claude-plans/*/` containing `plan.md` or `spec.md`, prefer matching branch ticket key, fall back to most-recent mtime, ad-hoc if zero matches).

## MSP repo detection

Per the triangulated check in `.claude-plans/2026-05-14-composition-skills/decisions.md` (remote URL contains `nicusa`/`tylertech` OR branch matches `^MSP-\d+/` OR `user.email` ends in `@tylertech.com`). When MSP-detected, bias `source.session_marker` to include the branch ticket key. No other behaviour change.

## Composition

| Posture | Skill | Direction |
|---|---|---|
| Callees | (none — leaf) | — |
| Callers | blueprint, pre-task-research | read |
| | debug-loop, execute-plan, finish-branch | write |
| Cycle guard | `caller=knowledge-capture` | log error, no-op |

Sibling-installed check (callers MUST run before invoking): `~/.claude/skills/knowledge-capture/SKILL.md` exists OR `~/.claude/plugins/cache/**/skills/knowledge-capture/SKILL.md` exists. If absent, the caller proceeds without writing and mentions the missing sibling once.

## References

- `references/entry-format.md` — pinned grep patterns, slug rules, em-dash separator, tag bracket syntax, supersede mechanics, worked examples for each kind.
- `references/read-api.md` — full digest output grammar, default limits, ordering rules, stale thresholds, empty-digest no-op.
- `references/schema.json` — the literal `.schema.json` content shipped on first-write.

## Anti-patterns

- **Silent writes "to save the user a prompt."** The whole skill's value evaporates the moment a user finds an entry they didn't approve. The batched gate exists precisely so we ask LESS often, not so we ask never. If you're tempted to skip the prompt, defer to the batched gate — never bypass it. The "always ask" rule is permanent for v1.
- **In-place edits to "correct" a prior entry.** ALWAYS supersede. The history is the data — a future LLM reading the file needs to see what we used to think to understand why we now think differently. The skill's parser treats the file as append-only; editing breaks slug stability.
- **Skipping `source.files` / `source.commit` / `session_marker` to look concise.** An entry without provenance is a graveyard one-liner. Future readers have no way to navigate back to the captured state. The skill rejects writes missing these — surface the missing fields back to the caller, do not write a partial entry.
- **Auto-fabricating an entry from session context** without the user's explicit phrase or a sibling-skill structured payload. We never invent knowledge. The LLM rephrasing a complaint as a gotcha is not the user saying "remember this."
- **Long entries.** ≤6 lines total (heading + 3 body fields ≤2 lines each). Anything longer is two entries or a wiki page, not a gotcha.
- **Treating `.claude-knowledge/` as project documentation.** It's gitignored by default. Users opt in to committing per-repo by removing the line — we do not push them.
- **Mid-session per-checkpoint prompts.** Three prompts during one debug session is skip-fatigue. Queue and batch. Exception: user-initiated capture gets one immediate "what should I write?" because the user already asked.
- **Reading the file with a markdown parser.** The grep patterns in `references/entry-format.md` are the parsing contract. Future LLMs use them. Anything fancier breaks across renderers.
- **Materializing the directory on first READ.** Blueprint Phase 1 reads against fresh clones constantly. First-read on missing dir is an empty digest with zero side effects.
- **Promoting auto-mode writes past the deferred-review log.** Auto-mode means "log to `open-questions.md` and let the user review later," not "write to kind-files without asking."
