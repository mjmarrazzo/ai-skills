# FDM Anti-Patterns

The canonical patterns the doctrine explicitly rejects, plus their frontend translations and the LLM-specific drift modes that show up when an agent applies FDM mechanically. Provenance preserved as inline italics so the skill stays self-contained — the wiki is not required reading.

`SKILL.md` inlines the five most common drift patterns at the top of the Phase 4 scan. This reference is the full canonical set + frontend translations + the broader LLM failure modes.

---

## Backend-canonical anti-patterns

### 1. Business logic in the handler

**Wrong:** `if (!email.includes("@")) return res.status(400).send("invalid email")` inside the request handler. The handler is making a decision.

**Why it's wrong:** Decisions are domain logic. Handlers are sequencers. *"No validation or business logic lives here" — FDM-The-Handler.* Logic in the handler can't be unit-tested without spinning up the whole request pipeline, and the same rule will get duplicated the next time someone adds an endpoint that does the same thing.

**Correct alternative:** Hoist the decision into a domain function returning `{ errors } | { entity }`. Handler becomes one line of routing:

```ts
const result = createUser({ email, tenantId });
if (result.errors) return res.status(400).json({ errors: result.errors });
const saved = await users.put(result.entity);
return res.json(saved);
```

*Originally from FDM-The-Handler.*

---

### 2. I/O calls inside domain functions

**Wrong:** `function createUser(input) { const existing = await db.users.findByEmail(input.email); ... }`. The domain function reaches out to the database.

**Why it's wrong:** *"The domain core imports nothing from outside — no database clients, no HTTP, no infrastructure" — FDM-Pushing-IO-to-the-Edge.* Dependencies point inward; the domain depends on nothing. The moment a domain function does I/O, you can no longer unit-test it without mocks, and you've broken the discipline that makes the rest of the architecture work.

**Correct alternative:** The handler gathers inputs first (queries the DB, fetches from the IDP, reads from env), then passes them to a pure domain function:

```ts
// handler
const existing = await users.findByEmail(input.email);
const result = createUser({ ...input, existingUser: existing });

// domain — pure
function createUser({ email, tenantId, existingUser }) {
  if (existingUser) return { errors: { email: "already registered" }};
  ...
}
```

*Originally from FDM-Pushing-IO-to-the-Edge and FDM-The-Domain-Function.*

---

### 3. Decision trees in catch blocks

**Wrong:**
```ts
try {
  await db.put({ Item, ConditionExpression: "attribute_not_exists(pk)" });
} catch (e) {
  if (e.code === "ConditionalCheckFailed") {
    if (input.allowUpsert) { return upsert(...); }
    else if (input.mergeStrategy === "newer") { return merge(...); }
    else { return { errors: ... }; }
  }
}
```

**Why it's wrong:** *"That's domain logic hiding in error handling" — FDM-Exceptions-to-the-Rule.* The catch block is now branching on business rules.

**Correct alternative:** Thin mapping in the catch, decision in a domain function:

```ts
const decision = resolveConflict(input, existing);  // pure
if (decision.action === "upsert") { ... }
```

The catch block is allowed to do one job: map "constraint violated" to "the conflict happened, here's the existing record". Anything more is domain logic. *Originally from FDM-Exceptions-to-the-Rule.*

---

### 4. Returning `null` / throwing exceptions for validation failures

**Wrong:** `if (!isValid(input)) throw new ValidationError("bad email")` or `if (!isValid) return null;`.

**Why it's wrong:** *"There is no third state" — FDM-The-Domain-Function.* `null` is a third state. Thrown exceptions are a third state — they create control flow the caller has to know about without seeing it in the type, and they encourage `catch (e) { ... }` decision trees (see #3).

**Correct alternative:** Binary result shape, idiomatic per language:

- TypeScript: `{ errors: {...} } | { entity: {...} }` (discriminated union)
- Go: `(entity, errors)` two-value return; `errors` is a structured type, not a bare `error`
- Java: a sealed interface `Result` with `Ok(entity)` and `Errors(errors)` variants (records + pattern matching in modern Java)
- Python: a `dataclass` union `Result = Ok | Errors` (or a `Union[Ok, Errors]` type alias)
- Rust: `Result<Entity, Errors>` is already this — the standard library encodes it

*Originally from FDM-The-Domain-Function.*

---

### 5. Repositories applying business rules

**Wrong:** `function saveUser(user) { if (user.email.endsWith("@spam.com")) throw ...; ... }` inside the repository.

**Why it's wrong:** *"No validation, no business rules — just translation and I/O" — FDM-The-Repository.* Repositories translate; they don't decide. If the rule moves to a new persistence layer (DynamoDB → Postgres), you'll re-implement it; worse, you'll forget to.

**Correct alternative:** Validation lives in a domain function called before the repository. The repository accepts a valid entity and stores it; the only failure modes it should surface are translation errors (the data doesn't fit the schema) or I/O errors (the network exploded). Both are surfaced as errors back to the handler, not decided on inside the repo.

*Originally from FDM-The-Repository.*

---

### 6. OOP service classes that mix I/O and logic

**Wrong:** `class UserService { constructor(db, mailer, logger, idp) { ... } async create(input) { /* validates, persists, emails, logs */ } }`.

**Why it's wrong:** *Functional-Domain-Modeling-and-Testing: "OOP's hidden state, temporal coupling, and mixed concerns are what FDM is designed to avoid."* The service class is a handler + domain + I/O bundle. Unit tests require mocking every constructor dependency. Refactoring one method ripples through the test suite.

**Correct alternative:** Three-file decomposition. The service class becomes (a) a handler function that gathers I/O and sequences calls, (b) a pure `createUser` domain function, (c) a repository module for persistence. Each is independently testable. If your language idiomatically demands a class wrapper (Spring `@Service`, NestJS `@Injectable`), the class becomes the handler shell; the pure logic still lives in a function the class calls.

*Originally from Functional-Domain-Modeling-and-Testing.*

---

### 7. Mocking domain dependencies to test business rules

**Wrong:** `const mockDb = { findByEmail: jest.fn().mockResolvedValue(null) }; const service = new UserService(mockDb, ...);`. Then assert on a validation rule.

**Why it's wrong:** *"When business logic is pure, you don't [need mocks]" — FDM-How-This-Impacts-Testing.* If a test for "reject email without @" requires wiring a mock database, the rule isn't in a pure function — it's tangled with I/O. The test is now coupled to the structure of the code, not the behavior. Renaming `findByEmail` or adding a constructor parameter breaks tests that don't care about either.

**Correct alternative:** Pull the rule into a pure domain function and test it directly: `expect(createUser({ email: "bad" }).errors).toEqual({ email: "..." });`. Zero mocks. Three lines. The test breaks only when the business rule changes — that's signal.

*Originally from FDM-How-This-Impacts-Testing.*

---

### 8. Vendor-shaped data leaking past the I/O boundary

**Wrong:** Handler code that does `user.profile.idp.provider.name` (Okta's nested response shape leaking into orchestration).

**Why it's wrong:** *"The handler never sees Okta's nested `profile` object… If Okta renames a field, only the client changes" — FDM-The-Repository.* The repository's job is bidirectional translation. If vendor shapes reach the handler, switching vendors becomes a refactor across files instead of a single client rewrite.

**Correct alternative:** The repository maps Okta/Auth0/whatever responses to domain-shaped types on the way in, and domain entities to vendor-shaped requests on the way out. The handler sees only domain types. A new vendor = a new client module + same domain types; nothing else changes.

*Originally from FDM-The-Repository.*

---

## Frontend translations

The doctrine reads as backend (Go services, AWS Lambdas, repository pattern). It translates cleanly to frontend with a vocabulary substitution: **handler → component or route**, **repository → fetch/storage layer (hook/composable/store)**, **domain function → pure state-derivation or reducer function**, **"push I/O to the edge" → "push fetch + storage + local state mutation to the outermost layer"**.

### Frontend equivalents of the canonical anti-patterns

- **(#1) Business logic in the handler** → **Business logic inside the component's render branch.** A component that does `if (user.role === "admin" && featureFlag.x && now > expiresAt) { ... }` inline. Pull it into a pure `canAccess({ user, flag, now })` function tested in isolation. The component just renders the result.

- **(#2) I/O in domain functions** → **`fetch` or `localStorage` calls inside a reducer or state-derivation function.** A reducer is supposed to be pure. The moment it calls `fetch` or `localStorage.setItem`, it can't be unit-tested without a JSDOM/MSW setup. Move I/O into the calling hook; pass the resulting values into the pure function.

- **(#3) Decision trees in catch blocks** → **`try/catch` around a fetch with branchy logic.** A `.catch(e => { if (e.status === 401) router.push(...); else if (...) ... })` is a decision tree disguised as error handling. Replace with a pure `handleFetchResult(response)` returning a discriminated union (`{ kind: "ok", data } | { kind: "needs-login" } | { kind: "rate-limited" }`).

- **(#4) `null` / thrown exceptions for validation** → **Form validation that throws or returns `undefined`.** Use a binary `validateForm(input) → { errors } | { values }` shape. React-hook-form's resolver pattern already encourages this; lean into it. Don't throw from a validator.

- **(#5) Repository business rules** → **Custom hook that filters / mutates response data based on business rules.** A `useUsers()` that filters out inactive users *inside the hook* puts a business rule where data fetching belongs. The hook fetches; a separate pure `filterActiveUsers(list)` decides. Test that separately.

- **(#6) OOP service classes** → **The "big container component" that fetches, validates, persists, and renders.** A single component that does everything. Split: a `useXyz()` hook owns I/O; pure functions own derivation/validation; the component renders the result.

- **(#7) Mocking to test rules** → **Mocking `fetch` globally to test a state-derivation function.** If your test for `formatUser(raw) → display` mocks `fetch`, you've coupled the rule to I/O. The rule should be a pure function; test it with literal inputs. Save MSW for testing the *hook* that does the fetching, not the function that derives display state.

- **(#8) Vendor shapes leaking** → **Component code that references the API response shape directly.** A component reading `data.results[0].attributes.profile.name` is reading the vendor's shape. The fetch layer (the hook, the API client) should normalize into a domain type the component sees; if the API changes, the hook changes, not 40 components.

### Frontend testing — the trap the user flagged

The user said they don't know React unit testing well but suspected it could mirror backend. It can — exactly. The split is identical:

- **Pure-function tests (zero mocks, zero setup):** test `formatUser`, `validateForm`, `canAccess`, `filterActiveUsers` directly with literal inputs. No JSDOM, no `render()`, no fetch mocking. These are the FDM "domain unit tests" for frontend code. Tooling: `vitest` running plain functions.

- **Hook + component tests (msw at the network boundary, no global `fetch` mocking):** test the hook with `@testing-library/react`'s `renderHook` and intercept the network with `msw`. This is the FDM "E2E for the I/O edge" — testing that the hook fetches correctly, transforms correctly, and surfaces errors correctly. The hook's pure derivation logic is *not* tested here; that was already covered in the first bullet.

When something tries to test a derivation rule by rendering the full component with mocked APIs, it's the frontend version of testing a domain rule through a mocked repository. Refactor first.

See `references/testing.md` for the full setup with worked examples.

---

## LLM-specific drift modes

Different from the canonical doctrine — these are patterns *you* (the model applying FDM mechanically) will slide into. The user said the discipline is "more about avoiding these than about following a positive recipe." Treat this list as the actual Phase 4 scan.

### A. Inventing a "domain function" that still does I/O

You renamed `signupHandler` to `signupDomain.ts` and moved it under `src/domain/`. But it still calls `await db.users.findOne(...)` and `await ses.sendEmail(...)`. The folder name is FDM; the function is not.

**Detection:** Open the file. Search for `await`, `process.env`, `Date.now()`, `Math.random()`, `console.log`, any logger import, any I/O client import. Any one of those is a violation. The function should be deterministic given its arguments.

**Why you do this:** It "looks right" because the structure superficially resembles the doctrine. The litmus test isn't structure — it's "can I run this in a unit test with literal inputs and no setup."

### B. Translating the doctrine literally onto a framework that fights it

Spring's `@Service`, NestJS's `@Injectable`, Django CBVs, Rails ActiveRecord — they encode I/O-coupled assumptions. Translating "handler = thin orchestration" onto a Spring `@RestController` annotated with `@Transactional(Propagation.REQUIRED)` and constructor-injected with five `@Repository` beans is going to fight you.

**The move:** Adapt, don't surrender. The framework's annotated class becomes the *outer shell* (handler). The pure logic lives in a separate module/file without annotations. The annotated class calls it. The annotations don't disappear, but the domain logic doesn't carry them.

**Why you do this:** Easier to follow the framework's idioms than to fight them. But FDM's whole point is that the framework's idioms hide the seams that make logic testable.

### C. Mocking the repository in tests "because that's what FDM says"

FDM does not say this. FDM rejects mocks for domain tests; it uses **fakes** when needed at the *handler* level (because handlers do I/O sequencing).

**The distinction:**
- **Mock:** a fake object whose method signatures and return values you script per-test. Brittle — breaks when interfaces evolve.
- **Fake:** a real working implementation backed by in-memory state, written once, behaves like the real thing but doesn't touch the network. Reusable across tests.

If you reach for `jest.fn()` / `mock.patch()` while testing a domain function, the rule isn't pure — refactor. If you reach for it testing a *handler*, ask whether a `fakeUserRepo()` (real Map-backed implementation) would serve.

### D. Skipping the anti-pattern scan because the code "looks fine"

The drift is subtle. You read the diff, everything seems FDM-shaped, you move on. Three months later someone audits and finds five domain functions calling `Date.now()` and two repositories that "just normalize a few fields" with business rules baked in.

**The move:** Run the Phase 4 scan as a deliberate, named step. Don't ad-hoc it. Use this reference open while reading the diff. Each item has a "look for" sentence — those are the grep-able / mentally-grep-able cues.

### E. Testing implementation details instead of behavior

A domain function returns `{ entity: { id, email, status: "PENDING" } }`. The test asserts `result.entity.id === "uuid-1234"`. Now the test is coupled to the ID-generation strategy, not the entity creation rule.

**The move:** Assert on what the doctrine cares about — the *shape* (presence of `id` as a non-empty string) and the *business invariants* (status is `PENDING`, not `ACTIVE`; email is normalized to lowercase) — not the specific values of domain-generated fields. Use matchers like `expect.any(String)` for generated IDs.

### F. Over-engineering the result-type scaffolding before writing the first function

You read the doctrine and immediately reach to write a `Result<T, E>` utility module with `map`, `flatMap`, `unwrap`, `chain`, `match`, generic type parameters, currying. None of which is needed for the first domain function.

**The move:** Start with the result inline (`{ errors } | { entity }`). Generalize the type only after a second function adopts it. The doctrine is small on purpose — adding a monad library on top of it is the LLM's tell.

### G. Putting "validation" code in a `validators/` folder separate from the entity construction

The doctrine: *"You cannot create an invalid entity because validation and construction are a single atomic operation."* If your `createUser` function calls `validateUser` first, then constructs, you've added a code path where someone can call `constructUser` without validation.

**The move:** One function. It validates and constructs together; it returns `{ errors }` if any rule fails, `{ entity }` if all pass.

### H. Adding "thin" abstraction layers between handler and domain

A wrapper service that "just delegates to the domain function but also logs / measures / wraps errors". Every such layer is a place where logic can creep in without you noticing.

**The move:** Logging and metrics are I/O. They live at the handler boundary, not as wrappers around domain calls. If you genuinely need an instrumentation layer, name it as such and keep it dumb — `withTiming(domainFn, args)` that calls `Date.now()` before and after, nothing else.

---

## How to use this reference

When the `fdm` skill is running Phase 4 (anti-pattern scan), open this file alongside the diff. Walk through the 8 canonical patterns first, then the 8 LLM-specific drift modes. Each has a one-line "wrong" example and a "look for" cue — use those as the actual scan items. Log findings to the active workspace's `decisions.md` if a blueprint workspace is active.

Triage findings at the end:
- **Trivial fixes:** apply in the same task that introduced the drift.
- **Substantive fixes:** call them out and hand off — they probably warrant a follow-up plan rather than getting bundled into the current task.

---

## Provenance

This reference was distilled from the user's identity-service FDM doctrine:
- *FDM-The-Domain-Function* — items #1, #4, the binary result shape, validation-with-construction (G)
- *FDM-The-Handler* — item #1, handler-as-sequencer
- *FDM-The-Repository* — items #5, #8, no-business-rules-at-the-edge
- *FDM-Pushing-IO-to-the-Edge* — item #2, dependencies-point-inward
- *FDM-Exceptions-to-the-Rule* — item #3, decision-trees-in-catches
- *FDM-How-This-Impacts-Testing* — item #7, mock-vs-fake distinction (LLM drift C)
- *Functional-Domain-Modeling-and-Testing* — item #6, the OOP critique
- *FDM-Presentation-QA-Prep* — clarifications on cross-entity rules and complexity

The LLM-specific drift modes (A–H above) are synthesized — they're not in the original doctrine. They're the failure modes that show up when an agent applies FDM mechanically. Cite the doctrine for the canonical items; own the LLM-drift items as a contribution from the skill itself.

The skill is self-contained. Do not link out.
