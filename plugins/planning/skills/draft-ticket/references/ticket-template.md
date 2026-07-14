# Ticket body template

The audience for this ticket is another LLM (or another team) that will run `blueprint` (or equivalent) to produce a spec + implementation plan. The ticket gives them enough to *understand and pick up the problem* without re-interrogating the requester — the feature or bug, why it matters, any decisions already accepted, and pointers to the code. It does **not** contain the implementation plan; that's what the implementer produces after pulling the ticket in. Scope the problem, not the solution.

## Required sections, in order

### 1. Summary

One to three sentences. State what changes for the user / system when this lands. Plain language; no implementation prescription.

> Example: "Replace HMAC-signed admin requests to `service-x` with API-key auth. Today every admin call to `/admin/*` requires a signed-request header; we want a single bearer key per environment to simplify operator tooling."

### 2. Background

Context the next LLM needs to plan. 1–3 short paragraphs. Include:
- Why this is being done now (business / operational driver).
- Current behavior, with file paths or doc links when known.
- Verified findings if a verification sub-step ran. Quote the commands and redacted results.

> Example: "Verified 2026-05-21: the current admin endpoint accepts `X-Signature` header generated via `lib/sign.js:42-78`. Gateway URL is `https://gw.example.internal/api/v1/...` (note the `/api/` suffix; documented URL without `/api/` returns 404). Confirmed via `curl -sI https://gw.example.internal/api/v1/admin/health` → 200."

### 3. Scope

What's in. Bulleted; point at the affected services / files with absolute or repo-relative paths when known. These are *pointers to where the work lands*, not instructions for what to change there — the implementer decides the fix.

> Example:
> - `services/service-x/handlers/admin.go` — admin request auth is enforced here.
> - `services/service-x/middleware/auth.go` — current `HMACAuth` middleware; where request-auth methods are wired.
> - Operator tooling / runbook — a new admin key will need to be surfaced to operators.

### 4. Out of scope

What an implementer might worry about that we explicitly excluded. Skip the section if empty — don't pad.

> Example:
> - Non-admin routes — unchanged.
> - Key rotation tooling — separate ticket.

### 5. Acceptance criteria

Numbered. Behavior-level, independently verifiable. Not implementation prescriptions.

> Example:
> 1. Admin calls to `/admin/*` succeed when `Authorization: Bearer <SERVICE_X_ADMIN_KEY>` is present and match the env-configured key.
> 2. Admin calls to `/admin/*` continue to succeed with a valid HMAC `X-Signature` header during the cutover window (both methods accepted).
> 3. Admin calls with neither valid bearer nor valid signature return 401 with body `{"error":"unauthorized"}`.
> 4. Existing integration tests in `services/service-x/test/admin_test.go` pass without modification.

### 6. Asks for consideration *(non-blocking)*

Questions the implementer should think about but aren't blockers. Drives downstream `blueprint` discovery rather than answering it.

> Example:
> - How long should HMAC remain accepted after API-key launch? Suggest 30 days, but operator team should weigh in.
> - Should the env var be `SERVICE_X_ADMIN_KEY` or namespaced under a secret manager path? Both work.

### 7. References

File paths, sibling tickets, docs. Skip the section if empty.

> Example:
> - PROJ-1234 — earlier discussion of API-key rollout pattern.
> - `services/service-y/middleware/apikey.go` — reference implementation in a sibling service.
> - Internal API docs: <internal link>

## Formatting rules

- Plain markdown, no HTML. GitHub issues and JIRA descriptions both render markdown.
- File paths in backticks. Use `file:line` or `file:line-line` for ranges.
- No "TBD", no "N/A" — skip the section instead.
- Code blocks for commands, schemas, and example payloads — not for proposed implementation code.
- Describe the problem and desired outcome, not the implementation. "Swap X for Y", "add function Z", and step-by-step how-to belong to the implementer, not the ticket. Decisions already accepted are fine to state as decisions.
