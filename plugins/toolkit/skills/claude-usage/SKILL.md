---
name: claude-usage
description: Use this skill when the user asks "check my usage", "how much quota/headroom is left", "am I near my limit", or "claude usage", and before an agent fans out parallel subagents or starts a long batch or autonomous run. Reads the Claude subscription's five-hour and seven-day utilization so the agent can decide whether to proceed. Skip for a one-off small task.
---

# claude-usage

Reads the subscription's five-hour (5h) and seven-day (7d) utilization with one command that fails loudly.

## When to run

- Before parallel fan-out (several subagents at once).
- Before a long batch or autonomous run.
- When the user asks about usage, quota, or headroom.

## How to run

```
sh <this skill's base directory>/scripts/usage.sh          # one summary line
sh <this skill's base directory>/scripts/usage.sh --json   # raw response body
```

The base directory is shown when the skill loads.

## Reading the output

```
5h 51% (resets in 2h13m) · 7d 27% (resets in 4d6h) · opus 12% · sonnet 3%
```

Values are utilization on a 0-100 scale. `opus` / `sonnet` appear only when the account has those buckets. `5h n/a` means the five-hour reading is unknown.

## Thresholds

- 5h above 80%: do not spawn new subagents or parallel fan-out. Finish the current work serially.
- 5h above 90%: stop, write a handoff/resume note, and tell the user.
- 7d above 90%: tell the user before any fan-out.
- 5h `n/a`: treat usage as unknown, the same as exit 1 or 4.

## Failure handling

- Exit 3: tell the user they are not logged in via OAuth (or the setup is unusable); the message says what is missing.
- Exit 1 or 4: usage is unknown, which is not headroom. Report the error, then continue only with ordinary serial work. Do not start a large fan-out on an unknown reading.

## Caveats

- The endpoint is undocumented and may change or disappear.
- Results are cached for up to 3 minutes; a 429 backs off for 5 minutes.
- If the endpoint goes away, a status-line tee that records usage is a possible fallback.
- On macOS the first run may show a keychain prompt; choose "Always Allow".
