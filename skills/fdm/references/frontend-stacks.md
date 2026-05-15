# FDM — Frontend Stacks

FDM translates to frontend with one core mapping:

> "Pushing I/O to the edge" maps to **"pushing fetch, localStorage, sessionStorage, and external state to the edge."**

The domain function becomes the **pure state-derivation function** (validation, normalization, computing the model the UI renders from the raw data it received). The handler becomes the **component or custom hook** that fetches data and then passes it to pure functions. The repository becomes the **API client / fetch wrapper / query function**.

## The mapping table

| Backend FDM concept | Frontend analog |
|---|---|
| Domain function | Pure function: validates form input, derives display state from API data, computes UI props from raw entity |
| Handler | Component or custom hook (or composable / store) — fetches, calls pure functions, dispatches results |
| Repository | API client / `fetch` wrapper / React Query queryFn / Vue composable's fetch / SvelteKit `load` function |
| "Push I/O to the edge" | `useEffect`, `onMount`, React Query, SWR, form submit handlers, store subscriptions — these are the edge; pure functions hold the logic |
| Result type `{ errors } \| { entity }` | Same shape in pure validation functions; UI components branch on which key is present |

## The shape of an FDM frontend unit

A login form, structured FDM-style:

```
auth/
  validate-login.ts          ← pure: { email, password } → { errors } | { validated }
  derive-login-state.ts      ← pure: API response → UI model
  api-client.ts              ← I/O: signup, login, fetch — the only file that calls fetch
  LoginForm.tsx              ← handler: renders, wires submit, calls pure fns then API
  useLoginSubmit.ts          ← optional hook: extracts the submit orchestration if the component grows
```

`validate-login.ts` and `derive-login-state.ts` import **nothing** from React, Vue, Svelte, or any HTTP library. They are plain TypeScript modules and run in tests with zero setup.

---

## React

**The translation:** the React component is the handler. A custom hook (e.g. `useSignupSubmit`) is where I/O lives at the edge — it calls `fetch` (or React Query / SWR / RTK Query). Pure functions hold validation and state-derivation.

**Domain function** (`auth/validate-signup.ts`) — pure, no React imports:

```ts
export type ValidationError = { field: string; message: string };
export type ValidateResult =
    | { errors: ValidationError[] }
    | { validated: { email: string; password: string } };

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const validateSignup = (input: {
    email: string;
    password: string;
}): ValidateResult => {
    const errors: ValidationError[] = [];
    if (!input.email) errors.push({ field: "email", message: "Email is required" });
    else if (!EMAIL_REGEX.test(input.email)) errors.push({ field: "email", message: "Invalid email" });

    if (!input.password) errors.push({ field: "password", message: "Password is required" });
    else if (input.password.length < 8) errors.push({ field: "password", message: "At least 8 characters" });

    if (errors.length > 0) return { errors };
    return { validated: { email: input.email.trim().toLowerCase(), password: input.password } };
};
```

**Repository** (`auth/api-client.ts`) — the only file that touches the network:

```ts
export async function signup(input: { email: string; password: string }): Promise<{ userId: string }> {
    const res = await fetch("/api/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
    });
    if (!res.ok) throw new Error(`Signup failed: ${res.status}`);
    return res.json();
}
```

**Handler** (`auth/SignupForm.tsx`) — React component, thin glue:

```tsx
import { useState } from "react";
import { validateSignup, ValidationError } from "./validate-signup";
import { signup } from "./api-client";

export function SignupForm() {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [errors, setErrors] = useState<ValidationError[]>([]);
    const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");

    const onSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        // 1. Domain: validate (pure)
        const result = validateSignup({ email, password });
        if ("errors" in result) {
            setErrors(result.errors);
            return;
        }

        // 2. Repository: persist (I/O)
        setStatus("submitting");
        try {
            await signup(result.validated);
            setStatus("success");
        } catch {
            setStatus("error");
        }
    };

    return (
        <form onSubmit={onSubmit}>
            <label>
                Email
                <input value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label>
                Password
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            {errors.map((err) => (
                <p key={err.field} role="alert">{err.message}</p>
            ))}
            <button type="submit" disabled={status === "submitting"}>
                {status === "submitting" ? "Signing up..." : "Sign up"}
            </button>
            {status === "success" && <p>Account created</p>}
        </form>
    );
}
```

Read the `onSubmit` like a recipe: gather inputs, call validation (pure), branch on result, call I/O. No business logic in the component beyond the routing on the validate result.

**When the component grows past ~80 lines**, extract the orchestration to a hook:

```ts
// useSignupSubmit.ts
export function useSignupSubmit() {
    const [errors, setErrors] = useState<ValidationError[]>([]);
    const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");

    const submit = async (input: { email: string; password: string }) => {
        const result = validateSignup(input);
        if ("errors" in result) {
            setErrors(result.errors);
            return { ok: false as const };
        }
        setErrors([]);
        setStatus("submitting");
        try {
            await signup(result.validated);
            setStatus("success");
            return { ok: true as const };
        } catch {
            setStatus("error");
            return { ok: false as const };
        }
    };

    return { errors, status, submit };
}
```

The hook is the I/O edge; the component becomes a renderer of state.

**Display-state derivation** — when an API response is shaped for the server's convenience but the UI wants something different, write a pure derivation function:

```ts
// users/derive-user-display.ts
export type UserDisplay = {
    initials: string;
    fullName: string;
    membershipBadge: "free" | "pro" | "enterprise" | null;
};

export function deriveUserDisplay(user: ApiUser): UserDisplay {
    return {
        initials: `${user.first_name[0] ?? ""}${user.last_name[0] ?? ""}`.toUpperCase(),
        fullName: `${user.first_name} ${user.last_name}`.trim(),
        membershipBadge: user.subscription?.tier ?? null,
    };
}

// UserCard.tsx
export function UserCard({ user }: { user: ApiUser }) {
    const display = deriveUserDisplay(user);
    return <div>{display.fullName} — {display.initials}</div>;
}
```

The component renders. The derivation is testable without a renderer.

---

## Vue 3 (Composition API)

The Vue 3 composition API maps cleanly to FDM. **Composables** are where I/O and reactive state live (the edge). **Plain `.ts` modules** hold the pure logic.

**Domain function** — identical to the React example, plain TS:

```ts
// auth/validate-signup.ts  — same as React, no Vue imports
export const validateSignup = (input: {...}): ValidateResult => {...};
```

**Repository** (`auth/api-client.ts`) — also identical:

```ts
export async function signup(input: {...}): Promise<{ userId: string }> {...}
```

**Composable (the handler)** (`auth/useSignupForm.ts`):

```ts
import { ref } from "vue";
import { validateSignup, type ValidationError } from "./validate-signup";
import { signup } from "./api-client";

export function useSignupForm() {
    const email = ref("");
    const password = ref("");
    const errors = ref<ValidationError[]>([]);
    const status = ref<"idle" | "submitting" | "success" | "error">("idle");

    const onSubmit = async () => {
        const result = validateSignup({ email: email.value, password: password.value });
        if ("errors" in result) {
            errors.value = result.errors;
            return;
        }
        errors.value = [];
        status.value = "submitting";
        try {
            await signup(result.validated);
            status.value = "success";
        } catch {
            status.value = "error";
        }
    };

    return { email, password, errors, status, onSubmit };
}
```

**Component** (`auth/SignupForm.vue`) — pure render binding:

```vue
<script setup lang="ts">
import { useSignupForm } from "./useSignupForm";
const { email, password, errors, status, onSubmit } = useSignupForm();
</script>

<template>
    <form @submit.prevent="onSubmit">
        <label>Email <input v-model="email" /></label>
        <label>Password <input type="password" v-model="password" /></label>
        <p v-for="err in errors" :key="err.field" role="alert">{{ err.message }}</p>
        <button type="submit" :disabled="status === 'submitting'">
            {{ status === "submitting" ? "Signing up..." : "Sign up" }}
        </button>
        <p v-if="status === 'success'">Account created</p>
    </form>
</template>
```

The composable is the handler ring. The component is a thin renderer. The validation function is the domain ring. The API client is the I/O ring.

---

## Svelte (and SvelteKit)

Svelte stores at the edge, derived stores + plain `.js`/`.ts` functions for the domain.

**Domain function** (`auth/validate-signup.ts`) — same as the others, plain TS:

```ts
export const validateSignup = (input: {...}): ValidateResult => {...};
```

**Repository** (`auth/api-client.ts`) — same:

```ts
export async function signup(input: {...}) {...}
```

**SvelteKit pattern:** in form-heavy routes, the `+page.server.ts` action is the handler (server-side); on the client, the `+page.svelte` component owns submit. With Svelte 5 runes:

```svelte
<!-- auth/+page.svelte -->
<script lang="ts">
    import { validateSignup, type ValidationError } from "./validate-signup";
    import { signup } from "./api-client";

    let email = $state("");
    let password = $state("");
    let errors = $state<ValidationError[]>([]);
    let status = $state<"idle" | "submitting" | "success" | "error">("idle");

    async function onSubmit(e: SubmitEvent) {
        e.preventDefault();
        const result = validateSignup({ email, password });
        if ("errors" in result) {
            errors = result.errors;
            return;
        }
        errors = [];
        status = "submitting";
        try {
            await signup(result.validated);
            status = "success";
        } catch {
            status = "error";
        }
    }
</script>

<form onsubmit={onSubmit}>
    <label>Email <input bind:value={email} /></label>
    <label>Password <input type="password" bind:value={password} /></label>
    {#each errors as err}
        <p role="alert">{err.message}</p>
    {/each}
    <button type="submit" disabled={status === "submitting"}>Sign up</button>
    {#if status === "success"}<p>Account created</p>{/if}
</form>
```

**For larger applications**, hoist state and orchestration into a store module:

```ts
// auth/signup-store.ts
import { writable, derived } from "svelte/store";
import { validateSignup } from "./validate-signup";
import { signup } from "./api-client";

export function createSignupStore() {
    const email = writable("");
    const password = writable("");
    const errors = writable<ValidationError[]>([]);
    const status = writable<"idle" | "submitting" | "success" | "error">("idle");

    async function submit() {
        let e = "", p = "";
        email.subscribe(v => e = v)();
        password.subscribe(v => p = v)();
        const result = validateSignup({ email: e, password: p });
        if ("errors" in result) {
            errors.set(result.errors);
            return;
        }
        errors.set([]);
        status.set("submitting");
        try {
            await signup(result.validated);
            status.set("success");
        } catch {
            status.set("error");
        }
    }

    return { email, password, errors, status, submit };
}
```

Same shape: store = handler ring, plain function = domain ring, API client = I/O ring.

**SvelteKit `load` functions** are also I/O — they live at the edge. The data they return flows into a component that calls pure derivation functions to compute its render shape.

---

## What changes vs. backend FDM

A few things are genuinely different on the frontend:

1. **Validation runs locally before submit**, not only on the server. The pure validation function is called in the client before the API request goes out. The server then re-validates (its own pure function) — it never trusts the client. Two callers, one pure function each side, sometimes shared (in a monorepo with shared types) or sometimes duplicated.
2. **State-derivation functions are very common** on the frontend (less common on the backend). They turn raw API data into the model the UI renders. Treat them as domain functions: pure, no React/Vue/Svelte imports, exhaustively unit-testable.
3. **The "handler" is reactive** — it doesn't run once and return; it lives as long as the component does, responding to events. The "recipe" pattern still applies per-event: each `onSubmit`, `onClick`, `useEffect` callback reads like a backend handler — gather, decide, branch, act.
4. **There's no clean "repository interface in the domain package" convention** on the frontend. The API client module is the repository; it just exports functions. The convention is "this is the only module that calls `fetch`" rather than a formal interface. That's fine — the discipline is the dependency direction, not the formalism.
5. **External state stores (Redux, Pinia, Zustand, Svelte stores) are I/O**. Reading from or writing to them inside a "pure" derivation function makes it impure. Pass the store's current value as an argument; let the component subscribe.

---

## Common drift patterns

- **A pure validation function that imports `useState`.** Not pure. Move state to the component; the validation takes plain arguments and returns a plain result.
- **A pure derivation function that calls `fetch` to "enrich" the data.** Not pure. The handler fetches; the derivation receives both pieces and combines them.
- **`useEffect` with business logic inside.** The effect calls the API (I/O — fine) and *then* decides what to do based on the response (logic — not fine). Extract the decision into a pure function: `decideNextStep(response)` returns the action enum; the effect dispatches it.
- **localStorage / sessionStorage reads inside a derivation.** Read it once at the edge, pass the value in.

Frontend FDM is the same discipline applied to a different I/O surface. The litmus test is the same: can you call the domain function in a test with zero setup — no DOM, no fetch, no router, no React/Vue/Svelte renderer? If yes, the shape is right.

See `testing.md` for the test recipes (vitest + Testing Library + msw).
