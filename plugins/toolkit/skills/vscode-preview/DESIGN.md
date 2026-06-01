# vscode-preview — DESIGN

Status: draft. Replaces `SKILL.md` once user approves.

## Goal

Open a markdown deliverable in VSCode or Cursor so the user can review it rendered, not as raw text in chat. Called at blueprint's review gates (spec gate, plan gate, decision reviews) and anywhere else a markdown file is ready for human eyes. Small skill — it fires an editor command, prints a path and a keybinding hint, and returns control to the caller immediately.

## When to trigger

Trigger phrases:
- "open in preview", "show the preview", "open the spec", "open the plan", "view the diff"
- Implicitly when blueprint says "please review" at a spec or plan gate and a `vscode-preview` sibling is installed

Opt-out signals: "just print the path", "I'll open it myself", "no preview needed".

## Editor detection

Detection order (first match wins):

1. **`$TERM_PROGRAM`** — value `vscode` means the user is in VSCode's integrated terminal; value `cursor` means Cursor's. Prefer this because it identifies the editor the user is _actively working in_, not merely one that's installed.
2. **`command -v code`** — VSCode CLI on `$PATH`.
3. **`command -v cursor`** — Cursor CLI on `$PATH`.
4. **Neither** — fall back to printing the path (see Fallback section).

If both `code` and `cursor` are on `$PATH` but `$TERM_PROGRAM` is unset or neither, prefer `code`. The user can override by saying "use cursor".

## Open single-file preview

There is **no CLI flag** that opens the rendered markdown preview pane directly. `code` has no `--command` flag; `markdown.showPreview` is an editor command palette action, not a CLI entrypoint. The honest workaround:

```sh
# Open file in the existing window, then prompt the user to trigger preview
code -r /abs/path/to/spec.md
```

The `-r` flag reuses the currently open window (avoids spawning a new window for every gate). After running this, print:

```
Opened spec.md in VSCode.
To render: Cmd+K V (preview beside source)  — or Cmd+Shift+V (preview replaces editor)
```

Prefer the side-by-side hint (`Cmd+K V`) as the default — keeping source visible alongside the preview matches the "review and possibly mark up" intent. On Linux/Windows substitute `Ctrl` for `Cmd`.

For `cursor`, the invocation is identical:

```sh
cursor -r /abs/path/to/spec.md
```

Cursor is a VSCode fork; `--diff`, `-r`, `-g` flags are the same. This is inferred from lineage, not empirically tested — flag for the user if behavior diverges.

Do not attempt to trigger the preview keystroke programmatically via `osascript` or similar. That approach requires accessibility permissions, steals window focus, is macOS-only, and fails silently when the editor is not frontmost. The keybinding hint is more reliable.

## Open diff view

Both CLIs support diff natively:

```sh
code --diff /abs/path/to/spec.v1.md /abs/path/to/spec.md
cursor --diff /abs/path/to/spec.v1.md /abs/path/to/spec.md
```

Argument order: `<old> <new>`. This matches blueprint's versioning convention — `spec.v1.md` is the prior version, `spec.md` is current. The diff view opens in the editor; no keybinding hint needed since the diff pane renders automatically.

For the markdown preview limitation: the diff view shows raw text, not rendered markdown. There is no CLI path to a rendered-markdown diff. If the user wants rendered reading, they should use single-file preview on the current version, not the diff.

## Fallback

When no supported editor is detected:

```
No VSCode or Cursor CLI found. File is at:
  /abs/path/to/spec.md

If you have VSCode, run: code -r /abs/path/to/spec.md
```

Never block or error. The caller (blueprint, execute-plan, etc.) continues regardless. The user can still open the file manually.

For non-markdown files passed by mistake: print the path, do not attempt to open a preview, note "preview is markdown-only."

## Anti-patterns

- **Treating "preview opened" as user approval.** Opening the file is not a gate response. Blueprint owns the gate — it waits for the user's explicit "looks good" before proceeding. This skill just opens the file.
- **Spawning a new window per file.** Always use `-r` to reuse. Multiple orphaned editor windows are noise.
- **Using this for non-markdown files.** Out of scope. `.json`, `.html`, `.txt` — just print the path.
- **Trying `osascript` or GUI automation** to trigger the preview keystroke. Fragile, macOS-only, requires permissions. Use the hint instead.

## Composition

- **Callers:** blueprint at Phase 4 (spec gate) and Phase 6 (plan gate); any future review-gate skill.
- **Calls:** nothing.
- **Reads:** the absolute path(s) passed to it; `$TERM_PROGRAM` for editor detection; `PATH` for CLI detection.
- **Writes:** nothing.

The skill is a thin shell invocation. It does not read `.claude-plans/` directly — callers pass it the relevant path.

## Open questions

1. **Side-by-side vs replace as default hint.** Currently defaulting to `Cmd+K V` (side-by-side). If users find it disorienting to have both panes open, switch the default to `Cmd+Shift+V`. Call out on first use and record preference.
2. **Cursor CLI parity.** `cursor --diff` and `cursor -r` are inferred from VSCode-fork lineage. No empirical test available on this machine (Cursor not installed). If a Cursor user reports divergence, add a separate cursor-specific invocation table.
3. **`$EDITOR` fallback.** Currently ignoring `$EDITOR` — it's usually a terminal editor (`vim`, `nano`) with no rendered markdown support, defeating the purpose. Should we honor it anyway for completeness? Leaning no; print path instead.
