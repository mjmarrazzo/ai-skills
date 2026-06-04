# ai-skills

A composable spine of Claude skills for engineering work, packaged as a **Claude Code plugin marketplace**. Skills are grouped by lifecycle phase — research → planning → executing → verifying → review — plus a toolkit of cross-cutting utilities. Each skill stands on its own and composes by referencing siblings *by name*, never by nesting; every skill degrades gracefully when its siblings aren't installed.

## Install (marketplace)

Add the marketplace, then install the phases you want:

```
/plugin marketplace add mjmarrazzo/ai-skills
/plugin install planning@ai-skills
/plugin install verifying@ai-skills
```

Install all six for the full spine, or à-la-carte. Skills activate by description — no extra wiring.

## Layout

```
ai-skills/
├── .claude-plugin/
│   └── marketplace.json          # the "ai-skills" marketplace, lists the 6 plugins
├── plugins/
│   └── <group>/
│       ├── .claude-plugin/
│       │   └── plugin.json
│       └── skills/
│           └── <skill-name>/
│               ├── SKILL.md       # required: frontmatter + body
│               ├── references/    # optional: detail docs loaded on demand
│               ├── scripts/       # optional: executable helpers
│               └── assets/        # optional: templates, fixtures
├── link.sh
└── README.md
```

## Local development

To dev against the live skills without going through the marketplace, symlink them into `~/.claude/skills/`:

```bash
bash link.sh
```

`link.sh` globs `plugins/*/skills/*`, prunes stale links pointing back into this repo, and skips any name that already exists as a real directory.

## Plugins (6) → Skills (17)

Skills are grouped around a research → planning → executing → verifying → review spine, plus cross-cutting utilities. Default mode for every skill is **interactive** (front-heavy questions before any writes); autonomous mode is opt-in via `mode=auto` or phrases like "go full auto", "skip the gates".

### `research` — Research & knowledge
- [`pre-task-research`](plugins/research/skills/pre-task-research/SKILL.md) — optional Phase 0 before blueprint. Parallel research subagents (library briefs, Confluence, JIRA, recent PRs, AWS docs, MS Learn, local knowledge) with hard token budgets. Produces `research.md` that blueprint folds into `handoff.md`.
- [`knowledge-capture`](plugins/research/skills/knowledge-capture/SKILL.md) — per-repo gitignored `.claude-knowledge/` (gotchas, patterns, stack-notes) read by blueprint and pre-task-research on every run; written at checkpoints by debug-loop, execute-plan, finish-branch. Append-only with supersede; never silent writes.
- [`tech-brief`](plugins/research/skills/tech-brief/SKILL.md) — central, durable per-tech briefs at `~/.claude/data/tech-briefs/<ecosystem>/<name>.md`, covering libraries, managed services (AWS Lambda, DSQL), platforms (GitHub Actions), and CLI tools. Researches a piece of technology once and stores a terse mental model + gotchas + version history that survives across projects. Read by blueprint Phase 1 and pre-task-research as a never-dropped Priority-2 source.

### `planning` — Planning
- [`blueprint`](plugins/planning/skills/blueprint/SKILL.md) — discovery questionnaire → parallel-reviewed spec → bite-sized implementation plan, all gitignored under `.claude-plans/`. Phase 1 reads knowledge-capture, offers pre-task-research, runs visual-digest on attached mockups. The entry point for substantive engineering work.
- [`draft-ticket`](plugins/planning/skills/draft-ticket/SKILL.md) — light discovery → optional verification → high-level bullets → workshop loop → JIRA create, for work the user is scoping but **not** implementing themselves. Produces ONE ticket whose body is detailed enough for another team or LLM to plan and implement from. Interactive only — no auto mode.
- [`grill-me`](plugins/planning/skills/grill-me/SKILL.md) — relentless one-question-at-a-time interview that stress-tests a plan, design, or proposal. With-docs variants sharpen domain language into `CONTEXT.md` and offer ADRs sparingly. Pokes holes before you commit.

### `executing` — Executing
- [`execute-plan`](plugins/executing/skills/execute-plan/SKILL.md) — walks `plan.md` task-by-task in one of two modes (subagent-per-task with two-stage review, or inline batch with checkpoints). Owns `progress.json` for resume across sessions.
- [`isolated-work`](plugins/executing/skills/isolated-work/SKILL.md) — wraps risky execution in a git worktree (via `EnterWorktree` or `git worktree add` fallback). Plans path-resolve before entering so the cleared cwd cache doesn't strand it.

### `verifying` — Debugging & verification
- [`debug-loop`](plugins/verifying/skills/debug-loop/SKILL.md) — disciplined root-cause analysis (reproduce → localize → hypothesize → test → fix → verify) with named playbooks per failure class and 9 explicit anti-patterns. Called by execute-plan on failure.
- [`verify-before-done`](plugins/verifying/skills/verify-before-done/SKILL.md) — pre-commit gate that detects tooling per stack, runs format/lint/typecheck/tests/plan-verifications/UI in order, writes the authoritative `verify.json` that finish-branch reads.
- [`ui-validation`](plugins/verifying/skills/ui-validation/SKILL.md) — Playwright-driven browser checks (real repo tests, ad-hoc spec, or MCP-only fallback). Look-then-ask credential flow, per-viewport screenshots, pixelmatch diff in Path C.
- [`visual-digest`](plugins/verifying/skills/visual-digest/SKILL.md) — schema-forced screenshot/mockup analyzer. Returns structured YAML (regions, elements, hierarchy, flows) instead of prose, with blank-canvas detection FIRST and independent-then-diff compare mode. Stops "looks good" vibes on incomplete UI.

### `review` — Code review lifecycle
- [`finish-branch`](plugins/review/skills/finish-branch/SKILL.md) — clean-state gates → triangulated MSP detection → PR title + 5-section body from spec/handoff/decisions → `gh pr create --draft`. Always opens a draft, then watches CI checks and bot reviewers settle, dispatches red checks to `ci-check-triage` and comments to `pr-review-triage`, and promotes to ready (pinging human reviewers) only once it's clean. Refuses to PR from main; `--force-with-lease` only.
- [`pr-review-triage`](plugins/review/skills/pr-review-triage/SKILL.md) — pulls PR comments via `gh` (Copilot, CodeRabbit, Codex, humans), grades each against plan/spec/decisions, proposes fix or won't-fix, gets your approval, applies, commits, comments back with the hash, resolves the thread. The post-PR review loop you actually run.
- [`ci-check-triage`](plugins/review/skills/ci-check-triage/SKILL.md) — the status-check mirror of pr-review-triage: pulls failed checks via `gh`, reads the failing logs, classifies each (real failure / flaky-or-infra / external blocker), hands real failures to `debug-loop` for a root-cause fix, offers a re-run for flaky ones, pushes. Auto-invoked by finish-branch when the watch goes red; biased toward "real failure" so re-running never masks a defect.

### `toolkit` — Cross-cutting utilities
- [`fdm`](plugins/toolkit/skills/fdm/SKILL.md) — applies Functional Domain Modeling discipline to feature work: pushes I/O to the edge, keeps domain functions pure, three-file (handler / domain / repository) decomposition, mock-free domain tests. References cover backend stacks (Go, Java/Spring, TypeScript/Node, Python/FastAPI) and frontend stacks (React, Vue, Svelte).
- [`vscode-preview`](plugins/toolkit/skills/vscode-preview/SKILL.md) — opens markdown rendered preview or diff in VSCode/Cursor at review gates. Uses `code -r` + a keybinding hint.
- [`caveman`](plugins/toolkit/skills/caveman/SKILL.md) — togglable terse-output register. `/caveman on` for this session, `/caveman persist` to survive new sessions (requires a one-time SessionStart hook install). Code, URLs, paths, and sibling-skill templates preserved verbatim. Default OFF.

## Composition

Skills compose by name, not by nesting. Cross-skill invocations pass `caller=<skill-name>` to prevent cycles (e.g., debug-loop ↔ ui-validation). Shared conventions (active-workspace resolution, ad-hoc artifact root, sibling-installed detection, MSP repo triangulation, TodoWrite as the in-session progress tool) are pinned across all skills.

Workspace artifacts (handoff, spec, plan, decisions, screenshots, verify logs, progress.json, **open-questions.md**) live under `.claude-plans/<YYYY-MM-DD>-<slug>/`. Always gitignored, never committed. `open-questions.md` is the running log of deferred decisions (auto mode) or things the user wants to revisit (interactive mode) — surfaced at end of run and read by Phase 1 of any continuation workspace.

Because skills are grouped into phase plugins but still reference each other by name, a cross-phase pointer (e.g. blueprint → ui-validation) simply no-ops if that phase's plugin isn't installed. Install the whole spine for the full experience, or pick the phases you need.
