# FDM Core Doctrine

The seven load-bearing concepts of functional domain modeling, with the doctrine quoted as written and a canonical 3-file example at the end. This file is self-contained — nothing here requires looking anything up externally.

---

## 1. Pushing I/O to the Edge

The organizing principle of the whole approach: move all I/O — database calls, HTTP requests, notifications, clock reads, randomness, file reads, environment-variable reads — to the outermost boundary of the system, so the core is pure computation.

> Dependencies point inward. The domain core imports nothing from handlers, repositories, or infrastructure. It has zero knowledge of DynamoDB, Okta, or HTTP. The handler depends on the domain. The repositories depend on the handler accepting their results. But the domain depends on nothing outside itself. This is what makes it testable without mocks — the domain has no dependencies to mock.

Three concentric rings:

```
┌─────────────────────────────────────────────────────────┐
│  I/O Edge      (repositories, infrastructure clients,    │
│                 external APIs, fetch wrappers)           │
│   ┌──────────────────────────────────────────────────┐   │
│   │  Orchestration   (handlers — thin glue,          │   │
│   │                   no logic)                      │   │
│   │   ┌──────────────────────────────────────────┐   │   │
│   │   │  Domain Core (pure functions, no I/O)    │   │   │
│   │   └──────────────────────────────────────────┘   │   │
│   └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

All arrows point inward. Nothing in the domain ring reaches outward.

**The litmus test:** can you call the domain function in a test with no database, no HTTP client, no environment variables, no DOM, no React renderer? If yes, it is properly shaped.

---

## 2. The Domain Function

Domain functions are pure — no I/O, no side effects, no database, no HTTP. They validate input, enforce business rules, and construct entities.

> You cannot create an invalid entity because validation and construction are a single atomic operation.

The canonical result type is binary: `{ errors }` on failure or `{ entity }` on success.

> There is no third state.

Callers destructure the result and branch on which key is present — no exceptions, no status codes, no null checks.

Two sub-patterns exist:

- **Entity pattern** (`create` function): for objects with identity (`id`), lifecycle, persisted state. Returns `{ entity: { id, ...fields } }` or `{ errors }`. The factory generates domain-owned values (IDs, codes, timestamps that the *domain* defines as part of construction, initial status). Note: timestamps that come from "now" are conventionally injected as a parameter (`now: Date`) so the function stays pure — see the open question on clocks in `SKILL.md`.
- **Value object pattern** (`validate` function): for operations that validate and normalize input without creating a new persistent record (e.g., query parameters, derived view state). Returns the clean values directly (not wrapped in `{ entity }`) or `{ errors }`.

---

## 3. The Handler

> Handlers are thin orchestration. They wire together domain, persistence, and infrastructure. No validation or business logic lives here.

The handler calls a domain function for decisions, then acts on the result.

> The handler reads like a recipe: create the entity, save it, send the email, return the response. Each step is one line.

The handler is a thin sequencer — it alternates between calling pure domain functions for decisions and calling I/O for effects.

Complex handlers exist. They orchestrate external IDPs, persist to multiple tables, clean up ephemeral records, log alarms on orphaned states. The complexity is "sequencing and error routing, not decision-making." The difference between sequencing and deciding is what keeps a long handler readable.

> A complex handler's complexity is sequencing and error routing, not decision-making... a workflow script: fetch, validate, create, persist, clean up. That's inherently sequential and readable top-to-bottom.

---

## 4. The Repository (I/O Boundary)

Repositories and infrastructure clients are the boundary between the system and external services.

> They translate in both directions — mapping domain entities to storage/API formats on the way out, and mapping storage/API responses back to domain-shaped data on the way in. No validation, no business rules — just translation and I/O.

The handler never sees storage-specific keys (`pk`, `sk` in DynamoDB) or vendor-specific shapes (Okta's nested `profile` object).

> If Okta renames a field, only the client changes. If the team switches from Okta to Auth0, a new client maps Auth0's response to the same shape — the handler doesn't change.

This is what "dependencies point inward" means in practice: I/O layers conform to the domain's data contracts, not the other way around. The domain owns the shape; the repository conforms.

---

## 5. Exceptions to the Rule

Some rules belong in the database, not in domain functions. Uniqueness constraints enforced by a conditional put are the clearest example — checking uniqueness in the domain layer first introduces race conditions and an extra round-trip.

> If the rule is always 'constraint violation = reject' with no conditional logic, the handler catches it and maps it to an error response.

If the response depends on context — upsert vs. reject vs. merge — that decision belongs in a domain function.

**The test:** is the catch block doing thin mapping (one error → one response, no logic) or running a decision tree?

> Decision trees in catch blocks are domain logic hiding in error handling.

---

## 6. Testing Implications

Because domain functions are pure, tests are plain assertions against return values:

> No test framework dependencies, no mocking library, no DynamoDB stubs.

Each test is 3-4 lines.

> Tests break only when business rules change (signal), never from structural refactoring (noise).

The contrast is explicit in the doctrine: in a codebase where business logic lives inside the endpoint alongside I/O calls, testing one validation rule can require wiring 9 mock dependencies — and if any mock's interface changes (renamed method, new constructor parameter), the test breaks even when the behavior is identical.

> Tests couple to structure, not behavior. Mocks encode your assumptions, not the real contract — when an external service changes its response format, all mock tests still pass green.

The two-layer test strategy: **domain unit tests** (pure function calls, no mocks, comprehensive business-logic coverage) + **E2E tests** (real HTTP against a deployed environment, catches contract drift and integration issues). The handler is thin enough that E2E coverage is sufficient for it — there is no logic in it to unit-test separately.

Full stack-specific recipes live in `testing.md`.

---

## 7. Presentation / Q&A Framing

Four anticipated objections, with the doctrine's answers:

1. **"The pattern doesn't work for complex rules."** Complex rules (e.g. "reject if verified 3 times today") just pass more data to the domain function as arguments.
   > The domain function gains a parameter; it doesn't gain a database dependency.

2. **"What about cross-entity business rules?"** Same pattern. The handler gathers inputs from multiple queries and passes them all to the domain function.
   > The handler is the one that knows how to gather the inputs; the domain function is the one that knows what they mean together.

3. **"Won't this make handlers complicated?"** Handler complexity is sequencing, not deciding.
   > A workflow script: fetch, validate, create, persist, clean up. That's inherently sequential and readable top-to-bottom.

4. **"How do we adopt this in an existing OOP codebase?"** Incrementally.
   > You don't rewrite. You extract.
   Pull validation out of service methods into pure functions one PR at a time. Service methods converge toward the handler pattern incrementally.

---

## The shape of an FDM module

A well-formed FDM unit has three files in coordination:

```
signup/
  email-verification.js              ← domain function (pure)
  email-verification-repository.js   ← I/O boundary (translation only)
  handler.js                         ← orchestration (thin glue)
```

### Domain function (`email-verification.js`)

```js
export const create = ({ email, tenantId, idpId, registration = {} }) => {
    const errors = [];

    if (!email) {
        errors.push({ field: "email", message: "Email is required" });
    } else if (!EMAIL_REGEX.test(email)) {
        errors.push({ field: "email", message: "Email is not a valid email address" });
    }

    if (errors.length > 0) return { errors };

    const ttlMinutes = registration.verificationTtlMinutes || 10;
    const code = String(crypto.randomInt(100000, 1000000));

    return {
        entity: {
            id: uuidv7(),
            tenantId,
            idpId,
            email,
            code,
            status: STATUS.PENDING,
            ttl: Math.floor(Date.now() / 1000) + (ttlMinutes * 60),
        },
    };
};
```

Note: `crypto.randomInt`, `uuidv7`, and `Date.now()` are technically impure. In a strict reading they would be injected as parameters; in practice, the doctrine treats them as domain-owned construction primitives (randomness and time the *domain* defines, not external state it reads). The test for purity is "can I call this in a unit test with no mocks and assert on the result shape" — `Date.now()` doesn't break that, but a `fetch` call would.

### Handler (`signup/handler.js`)

```js
api.post("/v1/tenants/:tenantId/idps/:idpId/signup/verify",
    async (request, response) => {
        const { registration, notifications } = request.idpConfig;

        // 1. Domain: validate + build entity (pure)
        const { errors, entity: verification } = emailVerification.create({
            email: request.body.email,
            tenantId: request.params.tenantId,
            idpId: request.params.idpId,
            registration,
        });

        if (errors) {
            return response.status(400).json(responseBody.validationError({ violations: errors }));
        }

        // 2. Repository: persist (I/O)
        await save(verification);

        // 3. Infrastructure: send email (I/O)
        await sendTemplatedEmail({ /* ... */ });

        return response.status(200).json({ verificationId: formatUuid(verification.id) });
    }
);
```

Read top-to-bottom: gather inputs, decide (pure), branch on the decision, act (I/O), respond.

### Repository (`email-verification-repository.js`)

```js
export const save = async (verification) => {
    const id = formatUuid(verification.id);
    await client.send(new PutCommand({
        TableName: process.env.DB_TABLE,
        Item: {
            pk: `TENANT#${verification.tenantId}#IDP#${verification.idpId}#EMAIL_VERIFICATION#${id}`,
            sk: "EMAIL_VERIFICATION",
            ...verification,
            id,
        },
    }));
};

export const findById = async (tenantId, idpId, id) => {
    const { Item } = await client.send(new GetCommand({ /* ... */ }));
    if (!Item) return undefined;
    const { pk, sk, ...entity } = Item;
    return entity;  // handler never sees pk/sk
};
```

Storage keys (`pk`, `sk`) are constructed on the way in and stripped on the way out. The handler operates on the clean domain entity.

---

## The flow, in two sentences

The handler gathers inputs, calls the domain function to make decisions, then calls I/O to act on those decisions. The domain function is always a leaf — it never calls back into the handler or into any I/O layer.
