---
name: caveman
description: Use this skill when the user wants Claude's free-form output compressed into a terse "caveman" register — fragments, no filler, code/URLs/paths preserved verbatim. Triggers on "/caveman", "/caveman on", "/caveman off", "/caveman persist", "/caveman status", "talk like caveman", "caveman mode", "compressed output", "drop the filler", "stay terse". Supports a session-only toggle and a persistent toggle backed by `~/.claude/state/caveman.on` plus a SessionStart hook. Default state is OFF; the user opts in. Skip when the user asks for a one-shot short answer ("be terse" alone, "shorter please") — that's a one-time request, not a register switch.
---

# Caveman

Togglable terse-output register for Claude Code. Compresses free-form narration; preserves code, URLs, paths, identifiers, and templated sibling-skill output verbatim.

**Announce at start:** none — caveman's whole purpose is to reduce output. The activation confirmation is a single line (`caveman on`) and nothing more.

## Actions

| Invocation | Effect |
|---|---|
| `/caveman`, `/caveman on`, "talk like caveman", "caveman mode" | Session-only mode on. Apply `references/caveman-rules.md` to all subsequent free-form output in this session. |
| `/caveman persist`, "make caveman persistent" | Same as `on` PLUS `mkdir -p ~/.claude/state && touch ~/.claude/state/caveman.on` so the `SessionStart` hook re-injects the rules on every new session. |
| `/caveman off`, "caveman off", "stop talking like caveman" | `rm -f ~/.claude/state/caveman.on`. Drop the caveman rules from the current session's working register. |
| `/caveman status` | Report persistent-flag presence, current-session register, and whether the SessionStart hook is installed. |

If the action is ambiguous (bare `/caveman` with no arg), treat as `on`.

## The rule-set

`references/caveman-rules.md` is the actual compression rule-set. Read it when activating. Apply it to free-form narration only — never to fenced code, URLs, file paths, identifiers, error messages, sibling-skill template output, or tool-call arguments.

## Flag-file contract

- **Path:** `~/.claude/state/caveman.on`.
- **Format:** zero-byte empty file. Presence = persistent mode on.
- **Writers:** `/caveman persist` (create), `/caveman off` (delete).
- **Readers:** `/caveman status`, `scripts/session-start.sh`.

When creating the flag the first time, `mkdir -p ~/.claude/state` first — the directory may not exist.

## Status-check logic

For `/caveman status`:

1. Check flag: `[[ -f ~/.claude/state/caveman.on ]] && echo present || echo absent`.
2. Check hook install: parse `~/.claude/settings.json` with `jq`, walk `.hooks.SessionStart[].hooks[].command`, look for substring `session-start.sh`. If `jq` errors (malformed JSON), report "could not parse settings.json".
3. Current session register: track in conversation context — `on` if `/caveman on|persist` was invoked this session, `off` otherwise.

Report format:

```
persistent flag: <present|absent>
this session:    <on|off>
hook installed:  <yes|no|unverified>
```

If `persistent flag: present` but `hook installed: no`, also print:

```
warning: persistent flag set but SessionStart hook missing — see references/hook-snippet.md to enable.
```

## Activation behavior

- On first activation in a session, emit exactly: `caveman on`. (Or `caveman on (persistent — applies to new sessions)` for `persist`.)
- After that, do not narrate the mode. The whole point is to shorten output, not announce it.
- Free-form output following the rule-set: fragments OK, drop filler, but preserve everything in the verbatim list.

## Composition with sibling skills

- **blueprint, execute-plan, verify-before-done, finish-branch, debug-loop, ui-validation, pr-review-triage, knowledge-capture, tech-brief, pre-task-research, visual-digest, vscode-preview, fdm, isolated-work:** their templated output is exempt — emit those templates verbatim. Compress only the narration around them.
- Caveman never invokes a sibling. Siblings never invoke caveman.

## Anti-patterns

- **Don't auto-toggle on phrase detection alone.** The frontmatter `description` makes Claude route to this skill, but the skill itself performs the explicit action — never silently flip state.
- **Don't compress fenced code, error messages, or tool-call arguments.** Breaks tool use.
- **Don't narrate the mode every turn.** One line on activation, then silence.
- **Don't compress sibling-skill template output.** Their shapes are load-bearing for downstream parsing.
- **Don't write to `~/.claude/state/caveman.on` without an explicit `/caveman persist`.** Silent persistence violates the human-in-the-loop default.

## When to skip

- The user says "be terse" alone, or "shorter please", or "tl;dr" — those are one-shot requests for the *next* answer, not register switches. Answer shorter; don't toggle.
- The user is inside a planning gate (`blueprint` Phase 4/6) and wants to read the full spec/plan — caveman exempts that output already, but be alert: if the user pushes back on a gate, free-form narration around the next iteration should still be terse only if the toggle is on.
