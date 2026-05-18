---
name: vscode-preview
description: Use this skill when the user wants to review a markdown file in a rendered view — "open the spec", "show me the plan", "review in preview", "open the diff", "diff the plans", "view the changes", "show the handoff". Also triggered implicitly at blueprint review gates (spec gate, plan gate) when a preview sibling is installed. Skip only if the user says "just print the path", "I'll open it myself", or "no preview".
---

# vscode-preview

Open a markdown file in VSCode or Cursor for rendered review. Small skill — it fires one CLI command, prints a keybinding hint, and returns control to the caller immediately.

**Announce at start:** "Opening in VSCode for preview."

## Editor detection

Check in this order; first match wins:

1. `$TERM_PROGRAM` — value `vscode` → use `code`; value `cursor` → use `cursor`. This identifies the editor the user is actively working in, not just what is installed.
2. `command -v code` — VSCode CLI on `$PATH`.
3. `command -v cursor` — Cursor CLI on `$PATH`.
4. Neither → fallback (see below).

If both `code` and `cursor` are on `$PATH` and `$TERM_PROGRAM` is unset or neither value, prefer `code`. The user can override with "use cursor".

## Single-file preview

There is no CLI flag that opens the rendered markdown preview pane directly. `code --command markdown.showPreview` is not a real flag — it is an editor command-palette action. The honest workaround:

```sh
code -r /abs/path/to/file.md
```

The `-r` flag reuses the existing window; it does not spawn a new editor window. After running, print:

```
Opened spec.md in VSCode.
To render: Cmd+K V  (preview beside source)
         — or —    Cmd+Shift+V  (preview replaces editor)
```

Prefer the side-by-side hint (`Cmd+K V`) as the default — keeping source visible alongside the preview matches the review-and-possibly-mark-up intent. On Linux/Windows substitute `Ctrl` for `Cmd`.

For Cursor, the invocation is identical (`cursor -r /abs/path/to/file.md`). Cursor is a VSCode fork; `-r` and `--diff` flags are inferred from lineage as equivalent. If a Cursor user reports divergence, surface it — empirical parity is not confirmed.

## Diff view

```sh
code --diff /abs/path/to/spec.v<N-1>.md /abs/path/to/spec.v<N>.md
```

Argument order: `<old> <new>` — older version on the left, newer on the right. The diff pane opens automatically; no keybinding hint is needed.

Note: the diff view renders raw text, not rendered markdown. There is no CLI path to a rendered-markdown diff. If the user wants rendered reading, use single-file preview on the current version instead.

## Fallback

When no supported editor is detected, print the path and do not block:

```
No VSCode or Cursor CLI found. File is at:
  /abs/path/to/spec.md

If you have VSCode or Cursor installed, run: code -r /abs/path/to/spec.md
```

The caller continues regardless. For non-markdown files passed by mistake, print the path and note: "preview is markdown-only — open this file in your editor directly."

## No GUI automation, ever

Never use any window-automation or focus-stealing mechanism — `osascript`, AppleScript, `xdotool`, `wmctrl`, `cliclick`, applescripted keypresses, or similar — to trigger the preview keystroke; the keybinding hint is the reliable alternative.

## Anti-patterns

- **Treating "preview opened" as approval.** Opening the file is not a gate response. Blueprint owns the gate — it waits for the user's explicit sign-off. This skill opens the file and returns.
- **Spawning a new editor window per file.** Always use `-r`. Multiple orphaned windows are noise.
- **Using this for non-markdown files.** Out of scope — `.json`, `.html`, `.txt`, source code. Print the path instead.
- **Faking a `--command` flag.** `code --command markdown.showPreview` is not a real CLI invocation. Do not attempt it.

## Composition

- **Callers:** blueprint at Phase 4 (spec gate) and Phase 6 (plan gate); any review-gate skill in the composition set.
- **Calls:** nothing.
- **Reads:** the absolute path(s) passed by the caller; `$TERM_PROGRAM`; `$PATH` for CLI detection.
- **Writes:** nothing.

The skill is a thin shell invocation. It does not discover `.claude-plans/` paths on its own — callers pass the relevant absolute path. To check whether this skill is installed before calling it, probe: `~/.claude/skills/vscode-preview/SKILL.md` OR `~/.claude/plugins/cache/**/skills/vscode-preview/SKILL.md`.
