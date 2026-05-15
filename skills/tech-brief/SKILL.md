---
name: tech-brief
description: Use this skill when the user says "research X", "library brief for Y", "brief on Z", "how does <lib> work", "how does <service> work", "AWS Lambda brief", "DSQL brief", "research <service>", "GitHub Actions brief", "research <platform>", "brief on <CLI tool>", "tech brief for", or "build me a brief on". Also auto-invoked by `blueprint` Phase 1 (read existing briefs; offer to research un-briefed) and read by `pre-task-research` as a Priority-2 source. Writes durable, central, append-only tech briefs to `~/.claude/data/tech-briefs/<ecosystem>/<name>.md` covering libraries, managed services (AWS Lambda, DSQL, S3), platforms (GitHub Actions, Vercel), and CLI tools — so the NEXT project does not relearn the same tech. Default mode is interactive; autonomous opt-in via `mode=auto` or phrase "go full auto". Skip only on explicit opt-out: "skip the brief", "no brief", "don't research".
---

# Tech Brief

A central, cross-project, durable knowledge store for libraries, managed services, platforms, and CLI tools. Researches a piece of technology once, writes a terse brief outside any single repo, and treats every subsequent re-encounter as an append-only delta rather than a rewrite. Tech-scoped, not repo-scoped — `knowledge-capture` is the repo-scoped sibling.

**Announce at start:** "Using tech-brief to capture this so the next project starts ahead of zero."

## When to trigger

Auto-trigger when:
- User says "research X", "library brief for Y", "brief on Z", "build me a brief on Q", "how does <library> work", "tech brief for Q" — for **libraries**.
- User says "how does <service> work", "AWS Lambda brief", "DSQL brief", "research <service>" — for **services**.
- User says "GitHub Actions brief", "research <platform>", "Vercel brief" — for **platforms**.
- User says "brief on <CLI tool>", "research terraform CLI" — for **tools**.
- `blueprint` Phase 1 reads existing briefs for any library, service, or tool named in the request or detected in repo manifests (`package.json`, `pyproject.toml`, `go.mod`, `pom.xml`, `Cargo.toml`, `Gemfile`) or recognized cloud service names (Lambda, DSQL, S3, Step Functions, etc.). Phase 1 also OFFERS (ONE batched AskUserQuestion) to research un-briefed tech that shows up in both request and manifests.
- `pre-task-research` reads matching briefs as its **Priority-2** source (between local-knowledge and Confluence). Never dropped on budget overflow.

Skip when: user opts out ("skip the brief", "no brief", "don't research") or the dep is genuinely trivial (one-line glue lib).

## Default mode and autonomous opt-in

**Default: interactive.** Before any research run, the skill fires a two-question wave (see "Interactive question wave" below). The user gates the methodology.

**Autonomous (opt-in):** explicit phrase ("go full auto", "autonomous", "no questions") or caller param `mode=auto`. In auto mode the skill infers library, ecosystem, version, and source set; runs the fan-out; writes the brief. Every non-trivial inference is logged to `.claude-plans/<active>/open-questions.md` (or `./.claude-results/<ts>/tech-brief/open-questions.md` ad-hoc) per the canonical format:

```markdown
## <date> — tech-brief — <topic>
**Question we'd have asked:** <one sentence>
**What we rolled with:** <decision>
**Why:** <reasoning>
**You might want to revisit if:** <signal>
```

Auto mode never silently skips persistence — the brief assembly is deterministic from sources. "Silence" only applies to whether the user is prompted on inputs.

## Storage (pinned)

Briefs live at:

```
~/.claude/data/tech-briefs/
├── README.md           # auto-regenerated index (atomic tmpfile + rename); grouped by kind then ecosystem
├── .schema.json        # schema_version + kind enum + ecosystem enum + stale thresholds
├── .audit.log          # append-only write log; rotates at 10 MiB
└── <ecosystem>/
    └── <name>.md       # one brief per tech item; kind discriminates behavior
```

Override the root with `CLAUDE_TECH_BRIEFS_DIR=<absolute-path>`. Use cases: dotfiles symlink, testing, multi-user box. When set, the skill treats the env var verbatim and skips the `~/.claude/data/...` default.

Brief file shape (full spec in `references/brief-schema.md`):

```markdown
---
name: react
display_name: React
kind: library                      # library | service | platform | tool
ecosystem: js
homepage: https://react.dev
repo: https://github.com/facebook/react
aliases: []
versions_explored: [18.3.0, 19.0.0, 19.1.0]
version_last_seen: 19.1.0
created: 2025-09-02
updated: 2026-05-14
tags: [ui, frontend, hooks]
stale_threshold_days: 180
see_also: [js/react-router, js/react-query]
schema_version: 2
---

# React — Brief

## TL;DR
## When to reach for it / When NOT to
## Mental model
## Common patterns
## Gotchas
## Specifics worth remembering
## Version history (newest first)
## References
```

`kind` discriminator: `library | service | platform | tool`. Drives which body sections appear, version semantics, and source-prompt selection. Required on every brief.

Service briefs (`kind: service`) get three additional sections inserted after Common patterns: **Pricing model** (billing dimensions in one paragraph — NOT a price quote), **Quotas & limits** (bullets, append-only), and **IAM / permissions cheatsheet** (common actions/resources block). These do NOT appear for library, platform, or tool kinds.

All kinds get a **Specifics worth remembering** section (before References): flexible long-tail bullets that don't fit a primary section. Append-only. This is NOT a duplicate of Gotchas — Gotchas are footguns ("you WILL hit this"); Specifics are accumulated lore ("worth noting").

Hard cap: body ≤200 lines for library/tool, ≤280 for service, ≤220 for platform (excluding frontmatter). Enforced at write time. Overflow falls through truncation → refuse per `references/api-contract.md`.

## API (5 intents)

Full contract in `references/api-contract.md`. Brief summary:

| Intent | Effect | Requires |
|---|---|---|
| `research_new` | Fresh brief from scratch | `library`, `ecosystem`, `caller`; refuses if brief exists |
| `research_new + clobber=true` | Archive existing to `<library>.v<N>.md`, then write fresh | `reason` (free text) |
| `refresh_existing` | Append delta row + edit-mode body changes between `prior_v` and `target_version` | `library`, `ecosystem`; `fresh=true` to bypass same-version no-op |
| `read_only` | Return markdown digest. NEVER triggers research. | `library`, `ecosystem` |
| `archive` | Rename `<library>.md` → `<library>.archived-<YYYY-MM-DD>.md`; drop from README index | `reason` (free text) |

`read_only` returns a **markdown** digest (not YAML) matching the knowledge-capture-style shape:

```markdown
### tech-brief: react (js, v19.1.0, updated 2026-05-14)

**TL;DR:** <paragraph from the brief's TL;DR>

**Mental model (digest):** <2-3 sentences from Mental model>

**Top gotchas:**
- <bullet 1>
- <bullet 2>
- <bullet 3>

**Full brief:** `~/.claude/data/tech-briefs/js/react.md`
```

Stale briefs prepend `[stale]` to the version: `### tech-brief: react (js, v19.1.0, [stale], updated 2024-11-02)`. Staleness is evaluated at READ time, never baked into the index.

## Interactive question wave (2 questions, not 4)

Fire ONE `AskUserQuestion` wave before any write:

1. **Confirm name + kind + ecosystem + version/snapshot** — structured options for all four detected values. Example: "tech-brief for `lambda`, kind=service, ecosystem=aws-service, snapshot=2026-05-14 — yes / edit one / cancel". Choices: `yes / edit one / cancel`.
2. **Sources + depth** — single 4-option question:
   - `standard` (all sources, ≤200 lines) — DEFAULT
   - `shallow` (homepage + README only, ≤80 lines)
   - `deep` (all sources + recent blog posts, ≤350 lines — requires ref-file extraction)
   - `custom` (let me pick sources) — drops to a follow-up question

The wave is load-bearing in interactive mode. Do NOT skip it to look efficient.

## TodoWrite — the 4-step research walk

In interactive mode, surface progress via `TodoWrite`:

```
[ ] Read prior brief (if any) + canonicalize name
[ ] Fan out research subagents (Priority order from references/source-prompts.md)
[ ] Assemble body + apply per-kind line cap (library=200, service=280, platform=220, tool=180)
[ ] Write brief + regen README + audit log row
```

In auto mode the same steps run without the surface — but failure to find any of (homepage / README / changelog) refuses the write rather than hallucinating.

## Composition

| Posture | Skill | Direction |
|---|---|---|
| Callees | `knowledge-capture` (read only — pull library-tagged gotchas) | read |
| Callers | `blueprint` Phase 1 | `read_only` always; `research_new` interactive-with-confirmation |
| | `pre-task-research` | `read_only` only (Priority 2; NEVER dropped on overflow) |
| | user direct | all 5 intents |
| Cycle guard | `caller=tech-brief` | log error, no-op |

Cycle posture (walked in `DESIGN.md`):
- `blueprint → tech-brief (read_only) → knowledge-capture (read_only)` — safe.
- `pre-task-research → tech-brief (read_only)` — read-only never invokes pre-task-research.
- `tech-brief → tech-brief` — no-op cycle guard.
- `see_also` links inside briefs are READ-ONLY metadata; the skill does NOT auto-traverse them.

Sibling-installed check before invoking (callers): `~/.claude/skills/tech-brief/SKILL.md` exists OR `~/.claude/plugins/cache/**/skills/tech-brief/SKILL.md` exists. If absent, the caller proceeds without and mentions the missing sibling once.

## Bootstrap

First write in a fresh `$HOME`:

1. `mkdir -p ~/.claude/data/tech-briefs/<ecosystem>/` (idempotent).
2. Create `~/.claude/data/tech-briefs/.schema.json` if absent (literal content from `references/schema.json`).
3. Create `~/.claude/data/tech-briefs/README.md` stub if absent (full regen happens after the first brief writes).
4. `.audit.log` is created on first append; nothing to bootstrap.

Subsequent writes skip steps 2 and 3.

## References

- `references/brief-schema.md` — frontmatter + body section grammar, line budgets, 200-line cap rule, 3 worked examples.
- `references/source-prompts.md` — per-source subagent prompts, structured-record format, token budgets, drop order.
- `references/api-contract.md` — the 5 intents in full: input payload, validation, output, refusal cases.
- `references/schema.json` — literal initial `.schema.json` shipped on first write.

## Anti-patterns

- **Don't rewrite existing briefs.** Append-only history; edit-only body for material deltas. Full rewrite is the failure mode this skill exists to prevent. `research_new + clobber=true` exists as the explicit escape hatch (requires `reason`).
- **Don't paraphrase upstream docs.** The brief is a *mental model* + *gotchas*. URLs handle the depth. Prose paraphrase is bloat.

  > Example: a brief that copies React's hooks rules verbatim is a tutorial. Brief should say "follow the Rules of Hooks" + the link, not restate them.

- **Don't auto-trigger silently.** Default is interactive — every research run starts with the 2-question wave. Auto mode logs every inference to `open-questions.md`; it does NOT bypass user gating of the methodology.
- **Don't write per-repo briefs.** Per-repo is `knowledge-capture`'s namespace (`.claude-knowledge/`). This skill is global (`~/.claude/data/tech-briefs/`).
- **Don't bloat the brief past the per-kind body line cap.** Caps: library=200, service=280, platform=220, tool=180. Enforced at write time. Overflow truncates References → Common patterns → Mental model in order; if still over, the skill refuses the write and surfaces the assembled body to the user or `open-questions.md`.
- **Don't trust "latest" without naming it.** `version_last_seen` is required on every write. The string "latest" gets resolved to a semver via WebFetch at write time and the resolved value is written.
- **Don't run on every blueprint Phase 1.** Phase 1 READS existing briefs and OFFERS research (ONE batched prompt) for un-briefed libraries. Mass-briefing every dep in a project is bloat.
- **Tutorial-creep.** Don't grow the brief into a tutorial. Briefs are mental-model documents; tutorials live upstream.
- **Code-listing-creep.** Pattern snippets are illustrative, not copy-paste libraries. ≤15 lines per snippet; no full examples.

  > Example: a "common pattern" entry showing a 60-line React component is wrong. The brief shows the 8-line shape that captures the idea; the user clicks through for the full code.

- **Paraphrase-creep.** Don't paraphrase the upstream docs section-by-section. Link them.
- **No-op refresh bumping `updated`.** If `refresh_existing` finds zero body diffs and zero new version-history rows, do NOT bump `updated` — the file is unchanged.
- **Conflation with knowledge-capture.** Tech-brief is tech-scoped (cross-project, any kind). knowledge-capture is repo-scoped (per-project). A gotcha specific to "this repo's use of React" is knowledge-capture. A React gotcha that affects every project is tech-brief.
- **Auto-traversing `see_also` links.** Read-only metadata. The user/caller decides whether to read linked briefs; the skill does not chain.
- **Cross-machine sync assumption.** `~/.claude/data/tech-briefs/` is local. Out of scope for v1. If the user moves machines, they copy or symlink the dir themselves.
