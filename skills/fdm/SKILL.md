---
name: fdm
description: Use this skill whenever the user is about to implement, build, structure, or design code — a new endpoint, a new feature, a new component, a new module, a refactor that creates new units of behavior, an "add X" or "wire up Y" task. Trigger phrases include "implement", "build the feature", "add the endpoint", "write the component", "structure this code", "design this module", "where should this logic live", "how should I shape this", "functional domain modeling", "FDM", "domain function", "handler", "repository", "push IO to the edge". Applies in any language and any layer — backend (Go, Java/Spring, TypeScript/Node, Python/FastAPI) and frontend (React, Vue, Svelte). Skip only when the user explicitly opts out ("just patch it", "skip FDM", "hot fix"), the change is a single trivial edit (typo, rename, one-line bugfix), or the file being modified is configuration with no logic.
---

# FDM — Functional Domain Modeling

Apply a small, opinionated discipline when shaping code: push I/O to the edge, keep business rules in pure functions, treat handlers as thin sequencers, and let the test strategy fall out of the architecture instead of being bolted on afterward.

**Announce at start:** "Using fdm to apply functional domain modeling — pushing I/O to the edge, keeping decisions pure."

## What FDM is (in one paragraph)

FDM is a way of carving up a unit of code into three concentric rings: **Domain Core** (pure functions that validate input, enforce business rules, and construct entities — no database, no HTTP, no clock if avoidable), **Orchestration** (handlers — thin glue that calls domain functions for decisions and calls I/O for effects, no logic of its own), and **I/O Edge** (repositories, infrastructure clients, fetch wrappers — translation between domain shapes and external shapes, nothing more). All dependency arrows point inward: the domain imports nothing from the I/O ring, the handler depends on both, the I/O ring conforms to the domain's contracts. This is what makes the domain testable without mocks, and what makes the I/O layer swappable without rippling through business logic.

## When to trigger, when to skip

Trigger whenever a request would otherwise produce a single file that mixes I/O calls with validation, business rules, or decision logic — i.e. most "implement X" requests. The default bias is to apply FDM: the cost is small (a few extra files, a few more function calls), the payoff compounds (testability without mocks, replaceable I/O, readable handlers).

Skip when:

- The user explicitly opts out ("just patch it", "skip FDM", "hot fix", "quick one-liner").
- The change is genuinely trivial: a typo, a rename, a single-line bugfix, a one-shot script, a config tweak.
- The file is genuinely all infrastructure — e.g. a deployment manifest, a build script, a migration that's just `ALTER TABLE`.
- The "feature" is a passthrough wrapper that genuinely has no domain decisions to make (rare; double-check before assuming this).

If you're not sure whether to apply it, apply it. Splitting a file into three when two would have done is recoverable; tangling I/O into a domain function in production is not.

## Phases

### Phase 1 — Detect the stack

Before applying the shape, identify what you're working in. The doctrine is language-agnostic; the syntax is not.

Inspect:

- **Repo manifests**: `package.json` (Node/TS/React/Vue/Svelte), `go.mod` (Go), `pyproject.toml` / `requirements.txt` (Python), `pom.xml` / `build.gradle{,.kts}` (Java/Kotlin), `Cargo.toml` (Rust).
- **Framework signals**: `@nestjs/*`, `express`, `fastify`, `hono` (Node web frameworks); `fastapi` / `flask` / `django` (Python); `org.springframework.boot` (Spring); `react`, `vue`, `svelte` packages; route file layout (Next.js `app/`, Remix `routes/`, SvelteKit `+page.svelte`).
- **Layer signals**: where does the file you're modifying live? `controllers/`, `routes/`, `handlers/`, `lambda/` → orchestration layer. `components/`, `views/`, `pages/` → UI layer. `services/`, `domain/`, `core/` → existing domain layer (good — extend it). `repository/`, `dao/`, `clients/`, `db/` → I/O edge.
- **Existing conventions**: if the codebase already has an FDM-like split (a `domain/` directory with no DB imports), follow it. Don't impose the canonical 3-file structure onto a codebase that has a working alternative shape.

For per-language detail and code examples, see:

- Backend → `references/backend-stacks.md`
- Frontend → `references/frontend-stacks.md`

If the repo's existing convention conflicts with the canonical FDM shape, note the conflict explicitly to the user (one sentence, e.g. "this codebase uses a Spring `@Service` pattern that mixes I/O and logic — I'll extract the pure pieces but the file layout will be hybrid") and proceed with the closest viable translation.

### Phase 2 — Apply the FDM shape

Read `references/core-doctrine.md` for the rules and the canonical 3-file example. The decisions you make in this phase are:

1. **Identify the domain function(s).** What decisions, validations, or constructions does this feature involve? Each becomes a pure function. Two sub-patterns:
   - **Entity pattern** (`create`): something with identity, lifecycle, persisted state. Returns `{ entity }` or `{ errors }`.
   - **Value object pattern** (`validate`): something that validates and normalizes input but creates no persistent record (query params, derived view state). Returns the cleaned values or `{ errors }`.
2. **Identify the I/O boundary.** Every database call, HTTP call, file read, env-var read, clock read, random read goes through a named function on the edge. The handler calls these; the domain function never does.
3. **Wire the handler.** The handler reads like a recipe: gather inputs, call domain function for the decision, branch on `errors` vs `entity`, call I/O for effects, return response. No `if` statements that aren't just routing on the domain function's result.

In the language-specific reference, pick the closest idiomatic translation. Spring will use a sealed interface for the result type; React will return `{ errors }` / `{ validated }` from a plain TS function; Go will return `(entity, errors)` as two return values. The shape stays the same — the syntax adapts.

**Litmus test before moving on:** can the domain function be called from a test file with zero setup — no test DB, no env vars, no HTTP mock, no React rendering? If yes, the shape is right. If no, I/O is still leaking in; split again.

### Phase 3 — Design the tests

FDM dictates the test split, not the other way around. See `references/testing.md` for stack-specific recipes (Go testify, Java JUnit 5, TypeScript vitest / jest, Python pytest, React + vitest + Testing Library + msw, Vue + vitest + Testing Library, Svelte + vitest + Testing Library).

The split is always two layers:

- **Domain unit tests** — pure function calls, plain assertions, zero mocks. Cover all validation rules, all entity-construction paths, all business-rule branches. Each test is 3-4 lines. Fast, deterministic, breaks only when business rules change.
- **E2E / component-level tests** — real HTTP for backend, real DOM render for frontend (with `msw` intercepting network at the wire level rather than mocking the fetch function). Cover the wiring, contract drift, integration. Not where you exhaustively test validation rules.

The handler layer is intentionally not unit-tested in the canonical FDM strategy. The doctrine acknowledges this gap honestly: handlers are thin enough that E2E coverage is sufficient. If the team has no E2E pipeline, repository-level fakes injected into the handler are a reasonable fill-in — but the domain tests remain mock-free regardless.

**Write the domain tests before the implementation** if practical (TDD), or at least alongside it. Domain tests are cheap enough that the cost of writing them first is negligible, and they pin the contract.

### Phase 4 — Anti-pattern scan

Before declaring the feature done, scan the change for the canonical drift patterns. Full list with examples and frontend translations in `references/anti-patterns.md`. The five that show up most often when an LLM (you) is applying FDM:

1. **A "domain function" that calls `fetch`, opens a DB connection, reads `process.env`, calls `Date.now()`, or imports a logger.** Not pure. Move the impure pieces to the handler/edge and pass the resulting values in as arguments.
2. **A handler with an `if` that's not just `if (errors) return 400`.** Decisions other than routing on the domain function's result are domain logic in disguise. Hoist them into a (new or existing) domain function.
3. **A repository that does anything other than translation.** No validation, no defaulting, no business rules in the I/O layer. If it computes something, that computation belongs in a domain function.
4. **Returning `null` / throwing a `ValidationError` from a domain function.** Use the binary `{ entity } | { errors }` result shape (or the language's idiomatic equivalent — sealed interface, discriminated union, two-value return). No third state.
5. **Tests that mock the repository to test a business rule.** If a test for "reject email without `@`" requires a mock DB, the rule isn't in a pure function — it's in the handler. Refactor before writing more tests.

When the active workspace is a blueprint workspace (a `.claude-plans/<dir>/` directory with `plan.md` or `spec.md` — see the active-workspace resolution algorithm in `decisions.md`), append findings to `.claude-plans/<active>/decisions.md` as a short ADR-style entry. Otherwise surface them in chat directly. Do not write to ad-hoc result paths unless a structured artifact is genuinely needed.

## Composition

FDM is a discipline, not an orchestrator — it doesn't fan out to other skills. It composes by being applied **inside** other workflows:

- **With `blueprint`:** when blueprint is drafting `spec.md`'s architecture section or `plan.md`'s task breakdown, apply FDM's shape to the proposed module decomposition. The spec's "data model" and "contracts" sections should already think in domain-function / handler / repository terms. If blueprint isn't installed, FDM still works standalone — just apply it directly when implementing.
- **With `execute-plan`:** if a plan task says "implement endpoint X", apply FDM's 3-file shape inside that task. Write the domain tests as part of the same task (TDD style) so the verify-before-done gate is meaningful.
- **With `verify-before-done`:** FDM-shaped code has fast, mock-free domain tests that should run in the `tests` check class. Slow integration / E2E tests run separately. If domain tests are slow, something is wrong — probably I/O has leaked in.

**Cycle prevention:** if invoked by another skill, accept a `caller=<name>` context parameter. This skill does not currently fan out to other skills, but if a future version does (e.g. delegating language detection to a sub-skill), pass `caller=fdm` so the receiver can break any cycle. See `decisions.md` for the convention.

**Sibling-installed detection:** none of FDM's behavior depends on a sibling. It works as a standalone discipline. If a referenced sibling (blueprint, execute-plan, verify-before-done) isn't installed, FDM degrades to "I'll apply the discipline here and now in this session", no announcement needed.

## Active workspace resolution

When findings need to be logged durably (e.g. an anti-pattern was caught and re-fixing it warrants a decision-log entry), use the canonical active-workspace resolution algorithm pinned in `decisions.md`. In brief: if a `.claude-plans/<dir>/` exists with `plan.md` or `spec.md`, log findings to its `decisions.md`. Otherwise surface findings in chat and don't write artifacts — FDM's outputs are code, not logs.

## Anti-patterns specific to applying FDM via an LLM

These are the failure modes you (the model) drift into when applying FDM. Read them; the discipline is more about avoiding these than about following a positive recipe.

- **Inventing a "domain function" that still does I/O.** You renamed `signupHandler` to `signupDomain` and moved the file, but it still calls the database. Not FDM. The litmus test is "can it run in a unit test with no setup", not "is it in a folder called `domain/`".
- **Mocking the repository to test a domain rule.** If your test for "reject invalid email" needs a mock DB, the validation isn't in a pure function — it's in the handler. The doctrine is explicit: domain tests have zero mocks. If you reach for one, refactor instead.
- **Putting the result-type into a separate utility module before writing the first domain function.** Don't over-engineer the scaffolding. Start with the domain function returning `{ errors } | { entity }` inline. Generalize the type only after a second function adopts it.
- **Translating the doctrine literally onto a framework that fights it.** Spring's `@Service`, NestJS's `@Injectable`, Django class-based views — they encode I/O-coupled assumptions. Adapt: put the pure logic in classes/modules without those decorators, then have the framework-decorated class delegate to the pure one. Don't pretend the framework's idioms don't exist; route around them deliberately. See `references/backend-stacks.md`.
- **Treating "push I/O to the edge" as "no I/O anywhere".** I/O still happens — at the edge. The handler still calls `await save(entity)`. The bug to avoid is I/O *inside the domain*, not I/O in the system.
- **Testing implementation details instead of behavior.** "Call `getUser` was made with these args" is a structure test, not a behavior test. Domain tests assert on return values; component tests assert on what the user sees. If you reach for a spy / a mock-call assertion, you're at the wrong level.
- **Skipping the anti-pattern scan because the code "looks fine".** It probably does — and the drift is probably subtle. Run the scan as a deliberate phase, not a vibe check.
- **Reflexively splitting trivial code into three files.** The cost of three files for a 10-line passthrough is higher than the benefit. FDM applies when there are decisions to extract. Pure passthrough wrappers can stay one file.

## Open questions

- **Where does middleware live?** Cross-cutting concerns (auth, IDP config resolution, request logging, rate limiting) are typically framework-level middleware that runs before the handler. They are not domain functions and don't fit cleanly in any of the three rings. The pragmatic rule: middleware is its own layer outside the rings, and the handler treats middleware-injected values (authenticated user, resolved IDP config) as inputs it gathers, same as it gathers query params. Open to refinement.
- **Multi-step domain decisions with conditional I/O.** When step 1 is "cheap validation" and step 2 needs an external lookup before deciding, split into two pure functions: `validateInputs(...)` returns errors or a `validated` value object; `applyBusinessRules(validated, externalLookupResult)` returns the final decision. The handler runs the cheap check first, gates the expensive I/O on its passing, then runs the second check.
- **State machine transitions.** Entity lifecycle transitions (`PENDING → CONFIRMED`, `PENDING → EXPIRED`) are domain functions on the existing entity (`confirm(verification, code) → { errors } | { entity }`). Complex state machines may warrant a dedicated state-transition function per transition; the doctrine doesn't prescribe a full state-machine library, and `references/core-doctrine.md` only sketches the pattern.
- **Testing the I/O boundary itself.** Domain tests cover the domain; E2E tests cover the wiring. Repository translation logic (does `pk`/`sk` get formatted correctly?) is implicitly covered by E2E. If a team has no E2E, lightweight integration tests against a real local DB / a testcontainers DB / a recorded HTTP fixture are a reasonable fill-in. The doctrine is silent here; `references/testing.md` notes the gap honestly.
