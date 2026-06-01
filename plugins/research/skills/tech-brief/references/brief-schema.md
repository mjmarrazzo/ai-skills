# brief-schema

Pinned format spec for `~/.claude/data/tech-briefs/<ecosystem>/<name>.md`. This is the long-lived parsing contract (schema_version: 2) that callers (`blueprint` Phase 1, `pre-task-research`, the read-only API) rely on. Bumps require a `schema_version` increment in `.schema.json` and a migration path.

## File layout

```markdown
---
<YAML frontmatter — fields below>
---

# <Display name> — Brief

## TL;DR
## When to reach for it / When NOT to
## Mental model
## Common patterns
## Pricing model         ← kind=service ONLY
## Quotas & limits       ← kind=service ONLY
## IAM / permissions cheatsheet  ← kind=service ONLY
## Gotchas
## Specifics worth remembering   ← ALL kinds
## Version history (newest first)
## References
```

Order is fixed. The level-1 heading appears once after frontmatter close. Every `##` section is required even when empty; an empty section emits `_none yet_` so the absence is intentional rather than missing. Service-only sections (`Pricing model`, `Quotas & limits`, `IAM / permissions cheatsheet`) are OMITTED entirely for `kind: library | platform | tool` — do NOT emit them with `_none yet_`.

## Frontmatter fields

YAML between two `---` markers. Required fields are enforced at write time; the skill refuses writes missing any required field.

| Field | Required | Type | Example | Notes |
|---|---|---|---|---|
| `name` | yes | string | `react` | canonical lowercase kebab-case; matches the file basename |
| `display_name` | yes | string | `React` | human-friendly form for the digest heading |
| `kind` | yes | enum | `library` | `library \| service \| platform \| tool`; drives section visibility, version semantics, source-prompt selection |
| `ecosystem` | yes | enum | `js` | must match the closed enum in `.schema.json`; new v2 values: `aws-service`, `gcp-service`, `azure-service`, `platform` |
| `homepage` | yes | URL | `https://react.dev` | resolves on WebFetch during research |
| `repo` | no | URL | `https://github.com/facebook/react` | omit when no public repo |
| `aliases` | no | list[string] | `[react-router-dom]` | alternative names; the skill probes these on read and `research_new` |
| `versions_explored` | yes (kind=library\|tool\|platform) | list[semver-or-tag] | `[18.3.0, 19.0.0, 19.1.0]` | append-only; insertion order = research order; use `snapshots_explored` for kind=service |
| `version_last_seen` | yes (kind=library\|tool\|platform) | semver-or-tag | `19.1.0` | computed as `semver_max(versions_explored)` at write time for library/tool; most recent entry for platform; use `snapshot_last_seen` for kind=service |
| `snapshots_explored` | yes (kind=service) | list[string] | `[dsql-preview-2024-12, dsql-ga]` | append-only; milestone IDs or ISO dates; NOT semver — use for kind=service only |
| `snapshot_last_seen` | yes (kind=service) | string | `dsql-ga` | most recently appended entry (chronologically by Date examined); NOT semver-max — use for kind=service only |
| `created` | yes | ISO date | `2025-09-02` | write date of the initial `research_new` |
| `updated` | yes | ISO date | `2026-05-14` | bumped on any write that materially changes the file; no-op refresh does NOT bump |
| `tags` | no | list[string] | `[ui, frontend, hooks]` | ≤6 tags; lowercase ASCII letters/digits/hyphens |
| `stale_threshold_days` | no | int>0 | `180` | overrides ecosystem default from `.schema.json`; rejected if ≤0 |
| `see_also` | no | list[string] | `[js/react-router, js/react-query]` | `<ecosystem>/<library>` form; surfaced in digest "Related" footer; NOT auto-traversed |
| `schema_version` | yes | int | `2` | matches `.schema.json` schema_version; must be ≤ the schema_version in `.schema.json` |

## Body section ordering and line budgets

Per-kind body line caps (excluding frontmatter): `library`=200, `service`=280, `platform`=220, `tool`=180. Section budgets are advisory targets. If a section is empty, it emits `_none yet_` and counts as 1 line. Service-only sections are OMITTED (not emitted) for non-service kinds.

| Section | Target lines | Kinds | Notes |
|---|---|---|---|
| TL;DR | ≤5 (one paragraph) | all | What the tech is, in one paragraph. No bullets. |
| When to reach for it / When NOT to | ≤8 (bullets) | all | Two short sub-blocks: when to use, when NOT to. |
| Mental model | ≤40 (2-4 paragraphs) | all | Core concepts a user must hold in their head. Prose. |
| Common patterns | ≤60 (≤4 patterns, each ≤15 lines including code) | all | Illustrative snippets, not copy-paste libraries. ≤15 lines per snippet. |
| Pricing model | ≤10 (one paragraph) | service only | Billing dimensions — NOT a price quote. Example: "per-request + per-GB-second; free tier: 1M req/mo + 400k GB-sec/mo." |
| Quotas & limits | ≤20 (bullets, append-only) | service only | Hard/soft limits. Append-only. Example: "15-min function timeout hard cap." |
| IAM / permissions cheatsheet | ≤15 (block) | service only | Common actions/resources block. Example: "`lambda:InvokeFunction`, execution role needs `logs:CreateLogGroup`." |
| Gotchas | ≤30 (≤8 bullets, each ≤2 lines) | all | One sentence per gotcha, optionally with a fix-link. |
| Specifics worth remembering | ≤20 (bullets, append-only) | all | Long-tail lore that doesn't fit a primary section. NOT a duplicate of Gotchas. Append-only. |
| Version history (newest first) | append-only table, no cap (rows are short) | all | One row per researched version/snapshot. Append-only. For service kinds, column header is "Snapshot". |
| References | ≤15 (≤8 URLs + light annotation) | all | Pinned canonical URLs. ≤8 entries. |

Total target (library): ≈160 lines, leaving ≈40 lines of headroom. Total target (service): ≈230 lines, leaving ≈50 lines of headroom.

`depth=deep` writes raise the soft cap to 350 lines; ref-file extraction is required up-front under `<ecosystem>/<name>/<ref-1>.md` etc., linked from the main brief.

## Per-kind line cap rule

Enforced at write time. Caps: `library`=200, `service`=280, `platform`=220, `tool`=180. Sequence:

1. Assemble body in memory.
2. Count non-frontmatter lines.
3. Determine cap from `kind`. If over cap, truncate in priority order:
   - **First:** drop References past the top 4 entries.
   - **Second:** truncate Common patterns to the single most-central pattern.
   - **Third:** truncate Mental model to 1 paragraph.
   Each truncation emits an audit log row: `cap_truncated section=<x> kept_lines=<n>`.
4. If still over cap: REFUSE the write. Surface the assembled body to the user (interactive mode) or `open-questions.md` (auto mode). The brief is NOT persisted.

Pattern snippets longer than 15 lines are auto-truncated to the first 15 with `# ...` trailing comment.

## Version history table

```markdown
## Version history (newest first)
| Date examined | Version | Key changes since prior |
|---|---|---|
| 2026-05-14 | 19.1.0 | Async ref forwarding GA; Server Actions stable; ref no longer required as second arg of forwardRef. |
| 2025-09-02 | 19.0.0 | React Compiler beta; useFormStatus / useOptimistic shipped. |
| 2024-04-25 | 18.3.0 | (initial brief) |
```

Newest-first ordering by insertion. Each row is a single line of markdown table. Append-only — never edit a prior row. The `Key changes since prior` cell is 1-3 sentences in plain English ("what changes for the user"), not a changelog dump.

## Worked examples

### Example 1: fresh `research_new` for `react` v19.1.0 (`kind: library`)

```markdown
---
name: react
display_name: React
kind: library
ecosystem: js
homepage: https://react.dev
repo: https://github.com/facebook/react
aliases: []
versions_explored: [19.1.0]
version_last_seen: 19.1.0
created: 2026-05-14
updated: 2026-05-14
tags: [ui, frontend, hooks]
stale_threshold_days: 180
see_also: [js/react-router, js/react-query]
schema_version: 2
---

# React — Brief

## TL;DR
React is a declarative component library for building user interfaces. v19 introduces Server Components, Actions, and stabilizes the new compiler. Most apps still use Function Components + Hooks; class components and legacy lifecycle methods are de-emphasized.

## When to reach for it / When NOT to
- Reach for: stateful UI with frequent interaction, ecosystem of compatible libraries (router, query, forms), Server Components when the app has a Next.js/Remix-style server framework.
- NOT for: static content sites (use Astro/MDX), simple form pages (vanilla + a sprinkle), or apps where bundle size dominates the budget (consider Preact/Solid).

## Mental model
Components are pure functions of props that return JSX. React reconciles a virtual tree against the DOM. State lives inside components (via `useState`) or in a context (`useContext`); side effects run in `useEffect` after commit.

Hooks must run in the same order every render — never inside conditionals or loops. The dependency array of `useEffect`/`useMemo`/`useCallback` is the contract for re-runs; getting it wrong is the most common bug class.

Server Components run on the server and emit serialized output to the client; they cannot use hooks or state. Client Components (`"use client"`) opt into interactivity. The mental shift in v19 is "default to server; opt into client".

## Common patterns
- State + effect:
  ```tsx
  const [count, setCount] = useState(0);
  useEffect(() => { document.title = `${count}`; }, [count]);
  ```
- Custom hook (encapsulate effect logic):
  ```tsx
  function useDebounced<T>(value: T, ms: number) {
    const [v, setV] = useState(value);
    useEffect(() => {
      const t = setTimeout(() => setV(value), ms);
      return () => clearTimeout(t);
    }, [value, ms]);
    return v;
  }
  ```
- Server Action (v19):
  ```tsx
  async function submit(formData: FormData) {
    "use server";
    await db.users.create({ name: formData.get("name") });
  }
  ```
- `useOptimistic` for optimistic UI updates without manual rollback (v19).

## Gotchas
- Stale closure inside `useEffect`: omitting a dependency captures the value at render-time. Lint with `react-hooks/exhaustive-deps`.
- `useState` initializer runs on every render — wrap in a function for expensive setup: `useState(() => compute())`.
- Server Components don't run in StrictMode double-invoke; bugs that depend on double-call won't reproduce server-side.
- `useEffect` cleanup runs BEFORE the next effect, not after the previous render. Order matters for subscriptions.
- `ref` is now a regular prop in v19; legacy `forwardRef` shape still works but is no longer required.
- Server Actions run in a different process; closing over client-side variables won't work.

## Specifics worth remembering
- useEffect with an empty deps array `[]` runs once after mount, but with NO deps array at all it runs after every render — a common copy-paste foot-gun.
- React batches state updates in event handlers by default in v18+; updates inside `setTimeout` or native event listeners are NOT batched unless wrapped in `flushSync`.

## Version history (newest first)
| Date examined | Version | Key changes since prior |
|---|---|---|
| 2026-05-14 | 19.1.0 | (initial brief) |

## References
- Docs: https://react.dev
- Server Components RFC: https://github.com/reactjs/rfcs/blob/main/text/0188-server-components.md
- v19 upgrade guide: https://react.dev/blog/2024/04/25/react-19-upgrade-guide
- Rules of Hooks: https://react.dev/reference/rules/rules-of-hooks
```

### Example 2: `refresh_existing` delta from React v19.0 → v19.1 (`kind: library`)

The brief existed at v19.0.0 (`updated: 2025-09-02`). A refresh to v19.1.0 produces:

**Frontmatter diff (before → after):**

```diff
-versions_explored: [18.3.0, 19.0.0]
-version_last_seen: 19.0.0
-updated: 2025-09-02
+versions_explored: [18.3.0, 19.0.0, 19.1.0]
+version_last_seen: 19.1.0
+updated: 2026-05-14
```

**Version history table — appended row at TOP (newest first):**

```diff
 ## Version history (newest first)
 | Date examined | Version | Key changes since prior |
 |---|---|---|
+| 2026-05-14 | 19.1.0 | Async ref forwarding GA; ref no longer required as second arg of forwardRef; minor Server Actions hardening. |
 | 2025-09-02 | 19.0.0 | React Compiler beta; useFormStatus / useOptimistic shipped. |
 | 2024-04-25 | 18.3.0 | (initial brief) |
```

**Body edits (only where the delta materially changes content):**

In Gotchas, an existing bullet is superseded by a more accurate one. Append-only history means the original is NOT edited in place — the refresh adds a NEW bullet:

```diff
 ## Gotchas
 - Stale closure inside `useEffect`: omitting a dependency captures the value at render-time. Lint with `react-hooks/exhaustive-deps`.
 - `useState` initializer runs on every render — wrap in a function for expensive setup: `useState(() => compute())`.
 - Server Components don't run in StrictMode double-invoke; bugs that depend on double-call won't reproduce server-side.
 - `useEffect` cleanup runs BEFORE the next effect, not after the previous render. Order matters for subscriptions.
-- `forwardRef` is required to receive a `ref` prop in v19.0.
+- `ref` is now a regular prop in v19.1+; legacy `forwardRef` shape still works but is no longer required.
 - Server Actions run in a different process; closing over client-side variables won't work.
```

The Mental model section gets ONE sentence edit reflecting the ref change:

```diff
 ## Mental model
-Server Components run on the server and emit serialized output to the client; they cannot use hooks or state. Client Components (`"use client"`) opt into interactivity. In v19, `ref` must still go through `forwardRef`.
+Server Components run on the server and emit serialized output to the client; they cannot use hooks or state. Client Components (`"use client"`) opt into interactivity. The mental shift in v19 is "default to server; opt into client". As of v19.1, `ref` is a regular prop.
```

Other sections (TL;DR, When to reach for it, Common patterns, References) are unchanged — the v19.0 → v19.1 delta doesn't materially affect them. The skill does NOT rewrite them.

Audit log row:

```
2026-05-14T15:42:11Z refresh_existing ecosystem=js library=react version=19.1.0 from=19.0.0 caller=user-direct
```

### Example 3: fresh `research_new` for AWS Lambda (`kind: service`)

```markdown
---
name: lambda
display_name: AWS Lambda
kind: service
ecosystem: aws-service
homepage: https://aws.amazon.com/lambda/
repo:
aliases: []
snapshots_explored: [2025-11-30-reinvent-2024, 2026-05-14]
snapshot_last_seen: 2026-05-14
created: 2026-05-14
updated: 2026-05-14
tags: [serverless, compute, aws, event-driven]
stale_threshold_days: 180
see_also: [aws-service/api-gateway, aws-service/step-functions]
schema_version: 2
---

# AWS Lambda — Brief

## TL;DR
AWS Lambda is a serverless compute service that runs code in response to events (HTTP via API Gateway, S3 events, SQS messages, scheduled triggers) without provisioning or managing servers. Billing is per invocation + duration (GB-seconds). The execution model is stateless; each invocation gets a fresh (or reused) container.

## When to reach for it / When NOT to
- Reach for: event-driven processing, short-lived API handlers, fan-out/fan-in pipelines, scheduled jobs, glue code between AWS services.
- NOT for: workloads exceeding 15-minute timeout, long-lived WebSocket connections, workloads needing >10 GB memory or >512 MB /tmp, latency-sensitive paths where cold start is unacceptable.

## Mental model
Lambda packages code + dependencies into a deployment unit (zip or container image). AWS manages the compute fleet; you own only the function logic and IAM permissions. Invocations are isolated — no shared memory between concurrent executions. The execution environment (container) may be reused ("warm") or freshly created ("cold start"). Global state in the handler module persists across warm invocations; side effects in the init path run only on cold starts.

Event sources push structured JSON payloads; the function returns a response or raises an exception. For synchronous invocations (API Gateway, ALB), the return value is the HTTP response. For async invocations (S3, SNS), errors are retried (twice by default) and dead-letter queues capture unprocessable events.

## Common patterns
- HTTP API handler via API Gateway v2 (proxy integration):
  ```python
  def handler(event, context):
      path = event["rawPath"]
      return {"statusCode": 200, "body": f"Hello from {path}"}
  ```
- SQS batch processor with partial failure reporting:
  ```python
  def handler(event, context):
      failures = []
      for record in event["Records"]:
          try:
              process(record["body"])
          except Exception as e:
              failures.append({"itemIdentifier": record["messageId"]})
      return {"batchItemFailures": failures}
  ```

## Pricing model
Billing has two dimensions: (1) **per request** — $0.20 per 1M invocations; (2) **per GB-second of compute** — $0.0000166667 per GB-second (ARM/Graviton2 ~20% cheaper). Cold start compute time is billed. Free tier: 1M requests/month + 400,000 GB-sec/month (permanent, not expiring). Provisioned Concurrency adds a flat hourly charge per concurrency unit to eliminate cold starts.

## Quotas & limits
- Function timeout: **15 minutes hard cap** (no exception).
- Memory: 128 MB – 10,240 MB (10 GB).
- /tmp storage: 512 MB – 10,240 MB (10 GB, configurable).
- Deployment package size: 50 MB zipped, 250 MB unzipped; container images up to 10 GB.
- Concurrent executions: 1,000 per region soft quota (raise via service quota request).
- Payload size: 6 MB synchronous, 256 KB async (SQS/SNS-triggered).
- Environment variables: 4 KB total.

## IAM / permissions cheatsheet
```
# Invoking a function
lambda:InvokeFunction   (resource: function ARN)

# Deploying / managing functions
lambda:CreateFunction, lambda:UpdateFunctionCode, lambda:UpdateFunctionConfiguration
lambda:GetFunction, lambda:ListFunctions

# Execution role (the role the function assumes at runtime) needs:
logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents
# Plus service-specific perms: s3:GetObject, sqs:ReceiveMessage, etc.

# VPC-attached functions also need:
ec2:CreateNetworkInterface, ec2:DescribeNetworkInterfaces, ec2:DeleteNetworkInterface
```

## Gotchas
- Cold starts on container images are dramatically slower than zip deployments for small payloads — use zip unless you need custom runtimes or >250 MB dependencies.
- Global state (DB connections, SDK clients) initialized outside the handler persists across warm invocations — intentional optimization, but beware stale credentials or exhausted connection pools.
- The 15-minute timeout is a hard ceiling with no override; long-running tasks must be split or handed to Step Functions/ECS.
- SQS trigger retries the ENTIRE batch on any error unless you return `batchItemFailures`; without partial failure reporting, one bad message poison-pills the whole batch.
- Provisioned Concurrency and Reserved Concurrency are different: Reserved caps maximum concurrency (throttles above the cap); Provisioned keeps containers warm (costs extra but eliminates cold starts).

## Specifics worth remembering
- The execution environment is reused across warm invocations but NEVER shared between concurrent invocations — concurrency isolation is strict.
- Lambda Layers are versioned and immutable; updating a Layer requires deploying a new layer version AND updating each function that references it.
- ARM/Graviton2 (`architecture: arm64`) is ~20% cheaper and typically faster for CPU-bound workloads; requires native compilation of any C-extension dependencies.

## Version history (newest first)
| Date examined | Snapshot | Key changes since prior |
|---|---|---|
| 2026-05-14 | 2026-05-14 | (initial brief) |
| 2025-11-30 | reinvent-2024 | Lambda added support for 10 GB /tmp; response streaming GA for Node.js runtimes; Python 3.13 runtime added. |

## References
- Lambda developer guide: https://docs.aws.amazon.com/lambda/latest/dg/
- Pricing: https://aws.amazon.com/lambda/pricing/
- Quotas: https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html
- Best practices: https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html
```

### Example 4: fresh `research_new` for AWS DSQL (`kind: service`, milestone-based snapshots)

```markdown
---
name: dsql
display_name: AWS Aurora DSQL
kind: service
ecosystem: aws-service
homepage: https://aws.amazon.com/rds/aurora/dsql/
repo:
aliases: [aurora-dsql]
snapshots_explored: [dsql-preview-2024-12, dsql-ga]
snapshot_last_seen: dsql-ga
created: 2026-05-14
updated: 2026-05-14
tags: [database, serverless, postgres, aws, distributed-sql]
stale_threshold_days: 180
see_also: [aws-service/rds-aurora, aws-service/dynamodb]
schema_version: 2
---

# AWS Aurora DSQL — Brief

## TL;DR
Aurora DSQL is a serverless, distributed PostgreSQL-compatible database with active-active multi-region support and optimistic concurrency control (OCC). No servers to manage; scales to zero; billing per ACU-second and I/O. GA'd at re:Invent 2024. Designed for globally distributed OLTP — not a drop-in replacement for single-region Aurora.

## When to reach for it / When NOT to
- Reach for: global active-active OLTP, serverless apps where the DB should also scale to zero, multi-region writes without manual replication setup.
- NOT for: workloads requiring `SERIALIZABLE` isolation (DSQL uses OCC/snapshot isolation), heavy analytics or reporting queries (use Redshift), existing Aurora setups with no multi-region requirement.

## Mental model
DSQL separates compute from storage. Each endpoint is a PostgreSQL-compatible query processor; the distributed storage layer handles conflict resolution via optimistic concurrency control. Transactions succeed unless a conflict is detected at commit time — conflicts cause a transaction abort (caller retries). There is no single-writer primary; all endpoints accept writes, and DSQL resolves conflicts across regions without coordination overhead.

Connection string looks like standard PostgreSQL; wire protocol is psql/libpq compatible. IAM authentication replaces password auth — the SDK generates short-lived tokens.

## Common patterns
- Connect using IAM token (Python + psycopg2):
  ```python
  import boto3, psycopg2
  client = boto3.client("dsql", region_name="us-east-1")
  token = client.generate_db_connect_admin_auth_token(Hostname=ENDPOINT, Region="us-east-1", Expires=900)
  conn = psycopg2.connect(host=ENDPOINT, user="admin", password=token, dbname="postgres", sslmode="require")
  ```
- Retry on OCC conflict (psycopg2 error code `40001`):
  ```python
  for attempt in range(3):
      try:
          with conn.cursor() as cur:
              cur.execute("UPDATE accounts SET balance = balance - 100 WHERE id = %s", (acct_id,))
          conn.commit(); break
      except psycopg2.errors.SerializationFailure:
          conn.rollback()
  ```

## Pricing model
Billing has three dimensions: (1) **ACU-seconds** — compute capacity consumed while the cluster is active; (2) **I/O requests** — per read/write operation to distributed storage; (3) **storage** — per GB-month of data stored. Scales to zero when idle (no ACU charge). No per-cluster minimum. Exact rates published at https://aws.amazon.com/rds/aurora/dsql/pricing/ and vary by region.

## Quotas & limits
- Max clusters per account per region: 5 (soft, raise via quota request).
- Max connections per cluster: documented in service quotas; grows with ACU allocation.
- Transaction timeout: 60 seconds (OCC conflict check window).
- Max rows returned per query: follows PostgreSQL semantics (no special cap).
- Multi-region active-active: currently supported in paired regions only (see docs for supported pairs).

## IAM / permissions cheatsheet
```
# Connect to cluster
dsql:DbConnectAdmin   (for admin user token generation)
dsql:DbConnect        (for regular IAM database user token generation)

# Manage clusters
dsql:CreateCluster, dsql:DeleteCluster, dsql:GetCluster, dsql:ListClusters
dsql:UpdateCluster

# Peering / multi-region
dsql:CreateMultiRegionClusters, dsql:GetMultiRegionClusters
```

## Gotchas
- OCC means your transaction WILL be aborted on write conflicts — always code retry logic; this is not optional.
- `SERIALIZABLE` isolation level is not supported; DSQL uses snapshot isolation with OCC. Applications that depend on strict serializability need architectural rethinking.
- IAM token-based auth is mandatory — traditional PostgreSQL password auth is not supported. Token lifetime is configurable (15 min default); connection pools must handle token refresh.
- The endpoint hostname is cluster-specific and region-affined; traffic does not auto-route to the closest region — the application picks the endpoint.

## Specifics worth remembering
- DSQL is PostgreSQL-wire-compatible but NOT a full PostgreSQL feature match — check the "Unsupported features" list in the docs before migrating an existing schema.
- Schema DDL (`CREATE TABLE`, `ALTER TABLE`) is replicated to all regions automatically; there is no per-region DDL management.

## Version history (newest first)
| Date examined | Snapshot | Key changes since prior |
|---|---|---|
| 2026-05-14 | dsql-ga | (initial brief at GA) |
| 2025-11-30 | dsql-preview-2024-12 | Preview launched at re:Invent 2024; multi-region active-active, IAM auth, PostgreSQL-compatible wire protocol. |

## References
- DSQL product page: https://aws.amazon.com/rds/aurora/dsql/
- DSQL developer guide: https://docs.aws.amazon.com/aurora-dsql/latest/userguide/
- Pricing: https://aws.amazon.com/rds/aurora/dsql/pricing/
- Unsupported PostgreSQL features: https://docs.aws.amazon.com/aurora-dsql/latest/userguide/working-with-postgresql-compatibility-unsupported-features.html
```

### Example 5: `archive` rename of a deprecated library

The library `request` (Node HTTP client) is deprecated and abandoned. User invokes:

```yaml
intent: archive
library: request
ecosystem: js
caller: user-direct
reason: "deprecated 2020; replaced by node-fetch/undici/axios"
```

Effect:
- `~/.claude/data/tech-briefs/js/request.md` → `~/.claude/data/tech-briefs/js/request.archived-2026-05-14.md` (rename, no content change).
- README index regen drops `request` from the active js section.
- Audit log row:
  ```
  2026-05-14T16:20:00Z archive ecosystem=js library=request archived_as=request.archived-2026-05-14.md reason="deprecated 2020; replaced by node-fetch/undici/axios"
  ```

Future `read_only` calls for `library: request, ecosystem: js` return `status: not_found` (the archived file is NOT probed for reads — it's forensic state only). A new `research_new` for `request` is permitted and would create a fresh `request.md` (the archived file is in the dir for provenance, not the active path).
