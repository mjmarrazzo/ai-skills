# FDM — Testing

The architecture drives the test strategy, not the other way around. FDM-shaped code has a particular test split that falls out of the dependency direction: the domain is pure, so it gets unit tests with zero mocks; the I/O is at the edge, so it gets integration / E2E tests against real-ish services. The handler is thin enough that it doesn't get its own layer of unit tests in the canonical strategy — the gap is acknowledged honestly.

This file gives the recipe for each backend test stack and each frontend test stack, with a worked example.

---

## The two-layer strategy

### Domain unit tests (the inner loop)

- **Pure function calls.** `const result = create({ email, tenantId, idpId })`, then assert on `result.errors` or `result.entity`.
- **Zero mocks. Zero setup. Zero teardown.** No test DB. No HTTP mock. No DI container. No React renderer. No fake clocks unless the domain explicitly takes a clock argument (in which case you pass `() => fixedTimestamp`).
- **3-4 lines per test case.** One line to construct input, one to call, one or two to assert.
- **Coverage:** every validation rule, every entity-construction path, every business-rule branch, every edge case (empty input, boundary values, etc.).
- **Speed:** milliseconds. Run them all on every save.
- **Break only when business rules change.** Renaming an internal helper, adding a new constructor parameter, switching from DynamoDB to Postgres — none of these touch a domain test. That's the signal-to-noise ratio FDM is buying.

### E2E tests (the outer loop, the CI safety net)

- **Real HTTP** against a deployed environment (or a local stack with real services).
- **Coverage:** full request flows, service contracts, persistence round-trips, integration correctness.
- **Catches contract drift.** If the real DynamoDB schema or the real Okta API response format changes, E2E tests fail where mock-tests would silently pass green.
- **Not where business logic is tested.** That's what the domain layer is for. *If someone's running E2E locally to test a validation rule, they're doing it wrong.*

### The handler layer — honestly

> There's genuinely no integration-level tests between domain and E2E in this project — the handler is thin enough that the gap is small, but it's an honest trade-off, not a free lunch.

For teams without E2E, **repository-level fakes** injected into the handler are a reasonable way to fill that gap (the handler is tested with a hand-rolled in-memory implementation of the repository interface; the domain tests remain mock-free regardless). Repository fakes are not the same as mocking libraries — a fake is a hand-written test double that implements the interface fully, not a recorded "expect this method to be called with these args" assertion.

---

## Backend stacks

### Go — `testing` + `testify`

The standard library's `testing` package is enough. Add `testify` for cleaner assertions.

```go
// signup/email_verification_test.go
package signup

import (
    "testing"
    "time"

    "github.com/stretchr/testify/assert"
)

func TestCreate_RejectsMissingEmail(t *testing.T) {
    _, errs := Create(CreateInput{
        Email:    "",
        TenantID: "t1", IDPID: "i1",
        Now:     func() time.Time { return time.Unix(1700000000, 0) },
        NewID:   func() string { return "fixed-id" },
        NewCode: func() string { return "123456" },
    })
    assert.Equal(t, []ValidationError{{"email", "Email is required"}}, errs)
}

func TestCreate_BuildsEntityWithCorrectTTL(t *testing.T) {
    entity, errs := Create(CreateInput{
        Email:                  "user@example.com",
        TenantID:               "t1", IDPID: "i1",
        VerificationTTLMinutes: 5,
        Now:                    func() time.Time { return time.Unix(1700000000, 0) },
        NewID:                  func() string { return "fixed-id" },
        NewCode:                func() string { return "123456" },
    })
    assert.Nil(t, errs)
    assert.Equal(t, "fixed-id", entity.ID)
    assert.Equal(t, int64(1700000000+300), entity.TTL)
}
```

Run with `go test ./...`. No DB, no HTTP, no mocking library.

### Java — JUnit 5

Mockito is fine **only at the repository boundary** for the (optional) handler tests. Domain tests use plain assertions.

```java
class EmailVerificationTest {
    @Test
    void rejectsMissingEmail() {
        var result = EmailVerification.create(new CreateInput(
            "", "t1", "i1", 10,
            ZonedDateTime.parse("2024-01-01T00:00:00Z"),
            () -> "fixed-id", () -> "123456"));

        assertThat(result).isInstanceOf(CreateResult.Failure.class);
        var failure = (CreateResult.Failure) result;
        assertThat(failure.errors())
            .containsExactly(new ValidationError("email", "Email is required"));
    }

    @Test
    void buildsEntityWithComputedTtl() {
        var result = EmailVerification.create(new CreateInput(
            "user@example.com", "t1", "i1", 5,
            ZonedDateTime.parse("2024-01-01T00:00:00Z"),
            () -> "fixed-id", () -> "123456"));

        assertThat(result).isInstanceOfSatisfying(CreateResult.Success.class, s -> {
            assertThat(s.entity().id()).isEqualTo("fixed-id");
            assertThat(s.entity().status()).isEqualTo(Status.PENDING);
        });
    }
}
```

No `@SpringBootTest`. No `@MockBean`. The domain function is plain Java; the test is plain JUnit.

### TypeScript / Node — vitest (preferred) or jest

Vitest is fast (Vite-native, no transpile setup) and Jest-compatible. Use whichever the repo already has; for greenfield, prefer vitest.

```ts
// auth/validate-signup.test.ts
import { describe, it, expect } from "vitest";
import { validateSignup } from "./validate-signup";

describe("validateSignup", () => {
    it("returns error when email is missing", () => {
        const result = validateSignup({ email: "", password: "abcdefgh" });
        expect(result).toEqual({
            errors: [{ field: "email", message: "Email is required" }],
        });
    });

    it("returns validated values when input is well-formed", () => {
        const result = validateSignup({ email: "User@Example.com", password: "abcdefgh" });
        expect(result).toEqual({
            validated: { email: "user@example.com", password: "abcdefgh" },
        });
    });
});
```

Run with `npx vitest`. The test file imports the function and asserts on its return value. Nothing else.

### Python — pytest

Plain `assert`. No fixtures unless the test genuinely needs them (it shouldn't for a domain function).

```python
# signup/test_email_verification.py
from datetime import datetime, timezone
from signup.email_verification import create, Failure, Success, ValidationError

def fixed_now():
    return datetime(2024, 1, 1, tzinfo=timezone.utc)

def fixed_id():
    return "fixed-id"

def fixed_code():
    return "123456"

def test_rejects_missing_email():
    result = create(
        email="",
        tenant_id="t1",
        idp_id="i1",
        now=fixed_now,
        new_id=fixed_id,
        new_code=fixed_code,
    )
    assert isinstance(result, Failure)
    assert result.errors == [ValidationError("email", "Email is required")]

def test_builds_entity_with_pending_status():
    result = create(
        email="user@example.com",
        tenant_id="t1",
        idp_id="i1",
        now=fixed_now,
        new_id=fixed_id,
        new_code=fixed_code,
    )
    assert isinstance(result, Success)
    assert result.entity.id == "fixed-id"
    assert result.entity.status == "PENDING"
```

Run with `pytest`. No `pytest-mock`, no `unittest.mock`, no test DB.

---

## Frontend stacks

This section is deliberately educational, since FDM applied to frontend testing is less familiar than the backend equivalent. The canonical setup is **vitest + @testing-library/react + msw** for React (analogously: `@testing-library/vue` or `@testing-library/svelte` for the others). The pattern is the same in all three frameworks; the API surface differs.

### Why vitest, Testing Library, and msw

- **vitest** — runs your tests. Fast (Vite-native, no babel/jest transformer dance), Jest-API-compatible, watch mode by default. The standard for new Vite-based projects; works in any TS/JS project.
- **@testing-library/react** (and `/vue`, `/svelte`) — renders the component and provides queries like `getByRole`, `getByLabelText`. The philosophy is "test what the user sees, not what the component does internally" — you never assert on implementation details like component state or render counts.
- **@testing-library/user-event** — simulates real user input (`type`, `click`, `tab`) with realistic event sequencing. Always prefer over the lower-level `fireEvent`.
- **msw (Mock Service Worker)** — intercepts `fetch` (and XHR) at the network level. The component / hook under test makes real `fetch` calls; msw handles the response. The test exercises the real fetch path, not a `jest.fn()` mock of your API client. This is the frontend analog of the honest trade-off the backend doctrine makes: msw tests the wire, not an assumption about the wire.

### The two test layers, mapped to frontend

| Backend layer | Frontend layer | Tool |
|---|---|---|
| Domain unit test | Pure function test — `validateSignup`, `deriveDisplayState`, etc. | vitest, no DOM |
| E2E test | Component integration test — render, interact, assert on DOM | vitest + @testing-library/react + msw |

The first layer is identical to a backend domain test. The second tests the wiring: does the form submit correctly, does the error message render, does the success state appear after the API responds.

### React — full worked example

**Setup** (`vitest.config.ts`, `src/setupTests.ts`):

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
    plugins: [react()],
    test: {
        environment: "jsdom",
        setupFiles: ["./src/setupTests.ts"],
    },
});
```

```ts
// src/setupTests.ts
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { setupServer } from "msw/node";

export const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

**Pure function test** (the domain layer — no React, no DOM):

```ts
// auth/validate-signup.test.ts
import { describe, it, expect } from "vitest";
import { validateSignup } from "./validate-signup";

describe("validateSignup", () => {
    it("returns error when email is missing", () => {
        const result = validateSignup({ email: "", password: "abcdefgh" });
        if (!("errors" in result)) throw new Error("expected errors");
        expect(result.errors).toContainEqual({ field: "email", message: "Email is required" });
    });

    it("normalizes email to lowercase on success", () => {
        const result = validateSignup({ email: "USER@example.com", password: "abcdefgh" });
        if (!("validated" in result)) throw new Error("expected validated");
        expect(result.validated.email).toBe("user@example.com");
    });

    it("rejects passwords shorter than 8 characters", () => {
        const result = validateSignup({ email: "user@example.com", password: "abc" });
        if (!("errors" in result)) throw new Error("expected errors");
        expect(result.errors).toContainEqual({ field: "password", message: "At least 8 characters" });
    });
});
```

These tests run in milliseconds, exercise every validation branch, never touch React, never need msw.

**Component test** (the integration layer — uses DOM and msw):

```tsx
// auth/SignupForm.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../setupTests";
import { SignupForm } from "./SignupForm";

describe("SignupForm", () => {
    it("shows error message when form submitted with invalid email", async () => {
        render(<SignupForm />);
        await userEvent.type(screen.getByLabelText("Password"), "abcdefgh");
        await userEvent.click(screen.getByRole("button", { name: "Sign up" }));

        // The pure validation function ran inside onSubmit; no fetch was needed.
        expect(screen.getByRole("alert")).toHaveTextContent("Email is required");
    });

    it("shows success state after API responds 200", async () => {
        server.use(
            http.post("/api/signup", () =>
                HttpResponse.json({ userId: "u-1" })),
        );
        render(<SignupForm />);
        await userEvent.type(screen.getByLabelText("Email"), "user@example.com");
        await userEvent.type(screen.getByLabelText("Password"), "abcdefgh");
        await userEvent.click(screen.getByRole("button", { name: "Sign up" }));

        expect(await screen.findByText("Account created")).toBeInTheDocument();
    });

    it("shows error state when API returns 500", async () => {
        server.use(
            http.post("/api/signup", () =>
                new HttpResponse(null, { status: 500 })),
        );
        render(<SignupForm />);
        await userEvent.type(screen.getByLabelText("Email"), "user@example.com");
        await userEvent.type(screen.getByLabelText("Password"), "abcdefgh");
        await userEvent.click(screen.getByRole("button", { name: "Sign up" }));

        // ... assert error display, depending on component design
    });
});
```

**What's load-bearing here:**

- The validation test runs zero mocks. It's the same shape as a backend domain test.
- The component test renders the real component and exercises a real submit. msw intercepts `fetch` at the network level — the component's `signup()` call from `api-client.ts` runs unchanged. There is no `vi.mock("./api-client")`.
- Tests assert on what the user sees (`screen.getByText`, `getByRole`), not on component state or which function was called.

**Why this matters:** in a non-FDM codebase where all logic is in the component, you can't test "Email is required" without rendering the form, typing, clicking, and waiting. In FDM, you test it in 3 lines without any of that — *and* you still write the component test for the rendering/submit integration.

### Vue — quick recipe

```ts
// auth/validate-signup.test.ts — IDENTICAL to React, plain TS
import { validateSignup } from "./validate-signup";
// ... same tests

// auth/SignupForm.test.ts — component test with @testing-library/vue
import { render, screen } from "@testing-library/vue";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../setupTests";
import SignupForm from "./SignupForm.vue";

it("shows error when submitted with missing email", async () => {
    render(SignupForm);
    await userEvent.type(screen.getByLabelText("Password"), "abcdefgh");
    await userEvent.click(screen.getByRole("button", { name: "Sign up" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Email is required");
});
```

Setup is the same: vitest, msw, jsdom environment. Swap `@testing-library/react` for `@testing-library/vue`.

### Svelte — quick recipe

```ts
// auth/validate-signup.test.ts — IDENTICAL again
// ... same tests

// auth/SignupForm.test.ts
import { render, screen } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import SignupForm from "./SignupForm.svelte";
// ... same shape
```

Vitest, msw, jsdom. The pure function tests are identical across all three frameworks because the pure functions don't depend on any framework.

---

## Worked example: a backend domain test vs. a mock-heavy equivalent

To make the contrast concrete, here's the same business rule tested two ways.

**The rule:** reject signup if email is already verified 3 times in the last 24 hours.

### FDM version

```ts
// signup/check-rate-limit.ts  (pure)
export function checkRateLimit(input: {
    email: string;
    verificationsInLast24h: number;
}): { errors: ValidationError[] } | { ok: true } {
    if (input.verificationsInLast24h >= 3) {
        return { errors: [{ field: "email", message: "Too many verification attempts today" }] };
    }
    return { ok: true };
}
```

```ts
// signup/check-rate-limit.test.ts  (pure)
it("rejects when 3 verifications in last 24h", () => {
    expect(checkRateLimit({ email: "u@e.com", verificationsInLast24h: 3 }))
        .toEqual({ errors: [{ field: "email", message: "Too many verification attempts today" }] });
});

it("allows when below limit", () => {
    expect(checkRateLimit({ email: "u@e.com", verificationsInLast24h: 2 }))
        .toEqual({ ok: true });
});
```

The handler is responsible for fetching `verificationsInLast24h` from the database and passing it in. The rule itself is a pure function.

### Mock-heavy version (what FDM rejects)

```ts
// signup-handler.ts  (logic inline with I/O)
async function signupHandler(req, res) {
    const recent = await db.query(`SELECT COUNT(*) FROM verifications WHERE email = $1 AND created_at > NOW() - INTERVAL '24 hours'`, [req.body.email]);
    if (recent.count >= 3) {
        return res.status(400).json({ error: "Too many verification attempts today" });
    }
    // ... rest of handler
}
```

```ts
// signup-handler.test.ts  (mock-heavy)
import { signupHandler } from "./signup-handler";
import { db } from "./db";

vi.mock("./db");
vi.mock("./mailer");
vi.mock("./idp-client");

it("rejects when 3 verifications in last 24h", async () => {
    (db.query as Mock).mockResolvedValueOnce({ count: 3 });
    const req = mockRequest({ body: { email: "u@e.com" } });
    const res = mockResponse();
    await signupHandler(req, res);
    expect(res.status).toHaveBeenCalledWith(400);
    expect(res.json).toHaveBeenCalledWith({ error: "Too many verification attempts today" });
});
```

Look at what the second test has to do: mock `db`, `mailer`, `idp-client`. Construct a fake request and response. Set up `mockResolvedValueOnce` matching the SQL the handler happens to run. **If the SQL query changes** (a refactor adds a `WHERE deleted_at IS NULL` clause), this test breaks — even though the behavior is unchanged. The test is coupled to the handler's structure, not the business rule.

The FDM version's test breaks only if "3 attempts in 24h" itself changes. That's the signal-to-noise difference.

---

## Contrast in a few bullets

**Mock-heavy testing:**
- Tests live at the endpoint layer.
- Each test mocks every I/O dependency (DB, HTTP client, message queue, etc.).
- Tests break when *anything* about the handler's structure changes — renamed methods, new constructor params, query rewrites.
- Mocks encode assumptions about external APIs; when the real API changes, mocks stay green.
- Slow to write (setup is heavy), slow to maintain (every refactor cascades).

**FDM testing:**
- Tests live at the domain function layer.
- Zero mocks.
- Tests break only when business rules change.
- E2E tests catch contract drift because they hit real services.
- Fast to write (3-4 lines), fast to maintain (refactors don't break behavior tests).

---

## Open questions

- **Testing the I/O boundary in isolation.** Domain tests cover the domain; E2E covers the wiring. Repository translation logic — does the `pk`/`sk` get formatted correctly? does the response shape get stripped correctly? — is implicitly covered by E2E. If a team has no E2E pipeline, lightweight tests of the repository against a real local DB (testcontainers, ephemeral DynamoDB local, etc.) are a reasonable fill-in. The doctrine is silent here.
- **Snapshot tests for component output.** Sometimes useful, often noisy. The Testing Library philosophy ("test what the user sees") tends to discourage snapshots in favor of explicit queries. Use them sparingly; prefer `getByRole` / `getByText` assertions.
- **Visual regression testing.** Out of scope here — see the `ui-validation` skill for screenshot diffing.
