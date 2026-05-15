# Isolated-work risky signals

Full enumeration for the isolated-work suggestion heuristic in execute-plan. Any one signal triggers the suggestion (provided `inside_worktree=false`).

| Signal | Condition |
|---|---|
| **File count** | Plan's `Files` section lists > 15 distinct files. |
| **Root config touched** | `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `tsconfig.json`, `next.config.*`, `vite.config.*`, `tailwind.config.*` at repo root. |
| **Migration present** | Any path matching `migrations/`, `*.sql`, `schema.prisma`, `alembic/versions/`. |
| **Auth/security paths** | Paths under `auth/`, `security/`, `middleware/`, or matching `*permission*` / `*authz*`. |
| **Architectural verbs** | `rename`, `extract`, `consolidate`, `rewrite`, `migrate`, `deprecate` in the plan header's `**Goal:**` line. |
| **Deletion-heavy** | More `Delete:` than `Create:` entries in the file map. |

After matching, surface the specific signal to the user in the prompt (e.g. "This plan touches 18 files including `package.json` at repo root").
