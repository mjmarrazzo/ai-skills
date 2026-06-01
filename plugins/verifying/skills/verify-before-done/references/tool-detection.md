# Tool Detection Tables

Detection runs once before any check. Inspect the workspace root and each package whose files appear in the diff. Stop at first match per category. Use the `scripts` field as ground truth; fall back to direct invocations only when scripts are absent.

## TypeScript / JavaScript

| Detection signal | Check | Command |
|---|---|---|
| `package.json` `scripts.lint` | Lint | `npm run lint` / `pnpm lint` |
| `package.json` `scripts.typecheck` | Typecheck | `npm run typecheck` |
| `tsconfig.json` (no explicit script) | Typecheck fallback | `npx tsc --noEmit` |
| `vitest.config.*` or `jest.config.*` | Tests | `npx vitest run` / `npx jest` |
| `eslint.config.*` / `.eslintrc*` (no script) | Lint fallback | `npx eslint .` |
| `prettier.config.*` / `.prettierrc*` | Format check | `npx prettier --check .` |

## Python

| Detection signal | Check | Command |
|---|---|---|
| `pyproject.toml` `[tool.ruff]` | Lint | `ruff check .` |
| `pyproject.toml` `[tool.mypy]` or `[tool.pyright]` | Typecheck | `mypy .` / `pyright` |
| `pytest.ini`, `pyproject.toml [tool.pytest]`, `conftest.py` | Tests | `pytest` |
| `setup.cfg [flake8]` (no ruff) | Lint legacy | `flake8 .` |

Prefer ruff over flake8 when both present.

## Go

| Detection signal | Check | Command |
|---|---|---|
| `go.mod` | Build + vet | `go build ./...` then `go vet ./...` |
| `go.mod` | Tests | `go test -short ./...` |
| `.golangci-lint.yml` / `.golangci.yml` | Lint | `golangci-lint run` |

## Rust

| Detection signal | Check | Command |
|---|---|---|
| `Cargo.toml` | Check | `cargo check` |
| `Cargo.toml` | Lint | `cargo clippy -- -D warnings` |
| `Cargo.toml` | Tests | `cargo test` |
| `rustfmt.toml` / `.rustfmt.toml` | Format | `cargo fmt -- --check` |

`cargo check` is faster than `cargo build` and still catches type errors; run it before clippy.

## JVM / Kotlin (Gradle)

| Detection signal | Check | Command |
|---|---|---|
| `build.gradle.kts` / `build.gradle` | Build + tests | `./gradlew build` |
| Gradle build with ktlint plugin | Lint | `./gradlew ktlintCheck` |
| Gradle build with detekt | Static analysis | `./gradlew detekt` |

For MSP repos: if `AWS_PROFILE` / `AWS_REGION` are unset before running integration-flavored test tasks, print a one-line reminder before proceeding.

## Multi-language / monorepo orchestration

Check for a repo-level orchestrator first:
- **nx**: `nx.json` → `npx nx affected --target=lint,typecheck,test --base=origin/main`
- **Turborepo**: `turbo.json` → `npx turbo run lint typecheck test --filter=...[origin/main]`
- **Lerna**: `lerna.json` → `npx lerna run lint test --since=origin/main`
- **None**: run per-package detection (see polyglot section in SKILL.md)

Prefer the orchestrator's "affected" mode — it avoids rebuilding the whole graph.
