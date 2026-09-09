# Triage contract

Triage gathers facts; it does not pick a tier. The tier-mapping heuristic runs on the orchestrator model, against the JSON below. Keep judgment out of the worker.

## Dispatch

One `Explore` subagent, `model: sonnet`, read-only. Give it the user's request verbatim and the repo root. It returns ONLY this JSON, in one fenced block — no prose before or after.

```json
{
  "files_likely_touched": 3,
  "files": ["plugins/planning/skills/blueprint/SKILL.md", "README.md"],
  "new_infra": false,
  "new_external_contract": false,
  "migration": false,
  "cross_cutting": ["auth"],
  "fan_in": "low | medium | high",
  "unfamiliar_area": false,
  "ambiguity": "low | medium | high",
  "notes": "<= 3 lines of what it found that the numbers don't carry"
}
```

## Field semantics

- **`cross_cutting`** — list drawn from: auth/authz, billing/payments, session/token/crypto/secrets, migrations, root config, shared infrastructure, widely-imported shared module. Empty when none apply.
- **`ambiguity`** — about the *request*, not the code. `low` = one obvious correct change. `medium` = a real choice the user hasn't made. `high` = the goal itself is underspecified.

## `fan_in` procedure

Blast radius, which file count does not carry. Grep importers and references of every file in `files` — language imports, `@import`/`@use`, template includes, exported-symbol references. Calibrate:

- `low` — few or no importers.
- `medium` — some.
- `high` — a module most of the codebase pulls in: a design-system stylesheet or token file, a base component, a root type or config module, a shared client.

`fan_in: "high"` **requires** adding `widely-imported shared module` to `cross_cutting`. A two-line edit to a token file is a two-file diff and a whole-app blast radius — sizing it as `direct` on file count alone is the exact mistake this signal exists to prevent.

## Tier-mapping heuristic

| Condition | Tier |
|---|---|
| Any of: `new_infra`, `new_external_contract`, `migration`, non-empty `cross_cutting`, `ambiguity == "high"`, `files_likely_touched > 10` | `full` |
| None of the above **and** `files_likely_touched <= 2` **and** `ambiguity == "low"` **and** `unfamiliar_area == false` | `direct` |
| Anything else | `plan-only` |

`ambiguity == "medium"` on an otherwise-`direct` shape lands at `plan-only` — ambiguity is the cheapest thing to be wrong about, and a plan is where a wrong assumption gets caught for free.

Do not add a fourth row. Do not soften `fan_in`'s obligation into a suggestion.

## Override

An explicit user instruction outranks the heuristic at every oversight level: "just make the change" → `direct`; "plan this properly" / "I want a spec" → `full`. Log the override to `hive.json.last_event`.

## Unparseable output

Re-dispatch once with the schema restated. A second failure is a halt condition.

## Source of truth for `cross_cutting`

Reuses execute-plan's existing auth/session/token/crypto/secret + migrations + root-config set for tier selection. Adds no new category beyond `widely-imported shared module` (from `fan_in`).
