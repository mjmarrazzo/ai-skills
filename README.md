# ai-skills

A monorepo of composable Claude skills. Each skill lives under `skills/<name>/` and stands on its own — skills compose by referencing each other by name, not by nesting.

## Layout

```
ai-skills/
├── README.md
├── .gitignore
└── skills/
    └── <skill-name>/
        ├── SKILL.md          # required: frontmatter + body
        ├── references/       # optional: detail docs loaded on demand
        ├── scripts/          # optional: executable helpers
        └── assets/           # optional: templates, fixtures
```

## Installing locally

Symlink any skill into `~/.claude/skills/`:

```bash
ln -s "$PWD/skills/<name>" ~/.claude/skills/<name>
```

Or symlink the whole `skills/` directory contents in one shot:

```bash
for s in skills/*/; do
  ln -sfn "$PWD/$s" ~/.claude/skills/"$(basename "$s")"
done
```

## Composition

Skills here are intended to compose freely. A skill may reference a sibling skill (e.g. `blueprint` defers UI verification to `ui-validation`), but never nests it. If you want a skill to use another, write the integration point as a clear pointer in the SKILL.md body — the user (or Claude) decides whether to invoke it.

## Skills

The set composes around a planning → executing → verifying → shipping spine, with cross-cutting utilities. Every skill stands alone and degrades gracefully when its siblings aren't installed.

### Planning
- [`blueprint`](skills/blueprint/SKILL.md) — discovery questionnaire → parallel-reviewed spec → bite-sized implementation plan, all gitignored under `.claude-plans/`. The entry point for substantive engineering work.

### Executing
- [`execute-plan`](skills/execute-plan/SKILL.md) — walks `plan.md` task-by-task in one of two modes (subagent-per-task with two-stage review, or inline batch with checkpoints). Owns `progress.json` for resume across sessions.
- [`isolated-work`](skills/isolated-work/SKILL.md) — wraps risky execution in a git worktree (via `EnterWorktree` or `git worktree add` fallback). Plans path-resolves before entering so the cleared cwd cache doesn't strand it.

### Debugging & verifying
- [`debug-loop`](skills/debug-loop/SKILL.md) — disciplined root-cause analysis (reproduce → localize → hypothesize → test → fix → verify) with named playbooks per failure class and 9 explicit anti-patterns. Called by execute-plan on failure.
- [`verify-before-done`](skills/verify-before-done/SKILL.md) — pre-commit gate that detects tooling per stack, runs format/lint/typecheck/tests/plan-verifications/UI in order, writes the authoritative `verify.json` that finish-branch reads.

### UI verification
- [`ui-validation`](skills/ui-validation/SKILL.md) — Playwright-driven browser checks (real repo tests, ad-hoc spec, or MCP-only fallback). Look-then-ask credential flow, per-viewport screenshots, pixelmatch diff in Path C.

### Shipping
- [`finish-branch`](skills/finish-branch/SKILL.md) — clean-state gates → triangulated MSP detection → PR title + 5-section body from spec/handoff/decisions → `gh pr create`. Refuses to PR from main; `--force-with-lease` only.
- [`pr-review-triage`](skills/pr-review-triage/SKILL.md) — pulls PR comments via `gh` (Copilot, CodeRabbit, Codex, humans), grades each against plan/spec/decisions, proposes fix or won't-fix, gets your approval, applies, commits, comments back with the hash, resolves the thread. The post-PR loop you actually run.

### Discipline
- [`fdm`](skills/fdm/SKILL.md) — applies Functional Domain Modeling discipline to feature work: pushes I/O to the edge, keeps domain functions pure, three-file (handler / domain / repository) decomposition, mock-free domain tests. Self-contained doctrine — references cover backend stacks (Go, Java/Spring, TypeScript/Node, Python/FastAPI), frontend stacks (React, Vue, Svelte), testing patterns, and anti-patterns including frontend translations.

### Utilities
- [`vscode-preview`](skills/vscode-preview/SKILL.md) — opens markdown rendered preview or diff in VSCode/Cursor at review gates. Honest about the `code --command markdown.showPreview` flag not being real; uses `code -r` + keybinding hint.

## Composition

Skills compose by name, not by nesting. Cross-skill invocations pass `caller=<skill-name>` to prevent cycles (e.g., debug-loop ↔ ui-validation). Shared conventions (active-workspace resolution, ad-hoc artifact root, sibling-installed detection, MSP repo triangulation, TodoWrite as the in-session progress tool) are pinned across all skills.

Workspace artifacts (handoff, spec, plan, decisions, screenshots, verify logs, progress.json) live under `.claude-plans/<YYYY-MM-DD>-<slug>/`. Always gitignored, never committed.
