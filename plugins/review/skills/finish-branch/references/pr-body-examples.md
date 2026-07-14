# PR Body Examples

Full rendered examples of the canonical PR body template.

## Ticket-prefixed feature PR (Datadog Orchestrion)

```markdown
## Summary

- Add Datadog Orchestrion for build-time APM instrumentation, replacing manual dd-trace wiring
- Covers all Lambda handlers in the payments and notifications services
- No runtime dependency changes; instrumentation is injected at build time

## Architecture context

Orchestrion operates as a Go build plugin; it rewrites imports at `go build` time rather than at
init(), which removes the need for any `import _ "gopkg.in/DataDog/dd-trace-go.v1/..."` lines.

## Test plan

- [ ] `make build` succeeds with `-toolexec orchestrion` flag
- [ ] `go test ./...` green locally
- [ ] APM traces visible in Datadog dev environment for a sample invocation
- [ ] Lambda cold-start duration within 5% of baseline (see load test in plan step 8)

## Non-goals / out of scope

- Replacing the existing RUM configuration — that is a separate ticket
- Adding custom spans; this ticket only covers automatic instrumentation

## Key decisions

- **Orchestrion over manual tracing** — eliminates 300+ lines of boilerplate across 12 handlers
- **Build-time injection** — safer than init() hooks; no runtime panic if dd-agent unreachable
- **Keep dd-trace-go as a direct dep** — Orchestrion still needs the type definitions at compile time

JIRA: https://example.atlassian.net/browse/PROJ-1234
```

## Ad-hoc PR — no blueprint workspace, no ticket convention

Repo has no `.claude-plans/` workspace and no ticket-prefixed branches; the body is built from `git log <base>..HEAD` alone. Branch `fix-retry-backoff`, title `Fix exponential backoff in webhook retry`. Sections with no source (Architecture context, Non-goals, Key decisions) are omitted — never padded with invented content. No `JIRA:` line without a ticket key.

```markdown
## Summary

- Fix webhook retry to use exponential backoff instead of a fixed 1s delay
- Cap retries at 5 attempts with jitter to avoid thundering-herd on recovery
- Log the final failure with the delivery ID before dropping the event

_No blueprint workspace found — summary generated from commits._

## Test plan

- [ ] `npm test -- webhook-retry` green locally
- [ ] Manual: kill the receiver, confirm delays log as ~1s/2s/4s/8s/16s
- [ ] Confirm dropped-event log line includes the delivery ID
```
