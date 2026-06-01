# Ticket body template

The audience for this ticket is another LLM (or another team) that will run `blueprint` (or equivalent) to produce a spec + implementation plan. Body must contain enough requirements to plan from without re-interrogating the original requester.

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

What's in. Bulleted; include affected services / files with absolute or repo-relative paths when known.

> Example:
> - `services/service-x/handlers/admin.go` — swap signature middleware for API-key middleware.
> - `services/service-x/middleware/auth.go` — add `APIKeyAuth` alongside existing `HMACAuth`; keep both during cutover.
> - Operator runbook update for the new env var `SERVICE_X_ADMIN_KEY`.

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
> - MSP-7019 — earlier discussion of API-key rollout pattern.
> - `services/service-y/middleware/apikey.go` — reference implementation in a sibling service.
> - Gov2Go API docs: <internal link>

## Formatting rules

- Plain markdown, no HTML. JIRA renders the description field as markdown.
- File paths in backticks. Use `file:line` or `file:line-line` for ranges.
- No "TBD", no "N/A" — skip the section instead.
- Code blocks for commands, schemas, and example payloads.
