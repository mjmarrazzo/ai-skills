# Installing the SessionStart hook

The caveman skill's *session-only* toggle works the moment the skill is installed. The *persistent* toggle (`/caveman persist`) needs one more step: a `SessionStart` hook in `~/.claude/settings.json` that re-injects the caveman rules on every new/cleared/compacted session.

## Prerequisite

`link.sh` (or `ln -s "$PWD/skills/caveman" ~/.claude/skills/caveman`) has already been run, so `~/.claude/skills/caveman/scripts/session-start.sh` resolves.

## The snippet

Add this entry under `hooks.SessionStart` in `~/.claude/settings.json`:

```json
{
  "matcher": "",
  "hooks": [
    {
      "type": "command",
      "command": "bash ${HOME}/.claude/skills/caveman/scripts/session-start.sh"
    }
  ]
}
```

If `hooks.SessionStart` doesn't exist yet, create it as an array containing this single object:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${HOME}/.claude/skills/caveman/scripts/session-start.sh"
          }
        ]
      }
    ]
  }
}
```

## Why `matcher: ""`?

Empty matcher fires on all `SessionStart` sources — `startup`, `resume`, `clear`, and `compact`. Caveman needs all four: rules scrolling out of context after compaction would silently break persistence. Restricting to `startup` only would defeat the persistent mode.

## Verifying

Open a new Claude Code session and run `/caveman status`. If the hook is installed, status reports `hook: installed`. If not, status reports `hook: missing — see references/hook-snippet.md`.
