# research.md Template

The parent skill emits `research.md` using this exact structure. Section order is the source-priority order. Empty sections still render — they tell the next reader "we looked here and the well was dry".

Total target: ≤250 lines. Per-section budgets below are upper bounds; sections may be shorter.

---

## Skeleton (copy-paste, then fill)

```markdown
# Research — <topic>

**Run at:** <YYYY-MM-DDTHH:MM:SSZ>
**Sources queried:** <comma-separated source names>
**Mode:** interactive | auto
**Cache:** miss | hit (re-run with `fresh=true` to bypass)

## Local knowledge (from .claude-knowledge/)
<knowledge-capture's read-API digest, verbatim — up to 20 records, ≤20 lines>

## Library briefs (from ~/.claude/data/library-briefs/)
<one bullet per matched library — one-line digest summary + path to full brief — up to 5 briefs, NEVER dropped>

## Confluence
<bullet records, ≤15 records, ≤17 lines>

## JIRA — related tickets
<bullet records, ≤15 records, ≤17 lines — section omitted entirely when non-MSP and no explicit opt-in>

## Recent PRs touching <paths>
<bullet records, ≤15 records, ≤17 lines>
<-- OR, when gh is absent: -->
## Recent commits touching <paths> (gh not available)
<bullet records, ≤15 records, ≤17 lines>

## AWS docs
<bullet records, ≤15 records, ≤17 lines>

## Microsoft Learn
<bullet records, ≤15 records, ≤17 lines>

## Open questions surfaced
<one bullet per topic the research didn't resolve, ≤15 lines>
```

---

## Per-section line budgets

| Section | Max lines | Notes |
|---|---|---|
| Header (title, run-at, sources, mode, cache) | 6 | Fixed. |
| Local knowledge | 20 | Owned by `knowledge-capture` read API. NEVER dropped. |
| Library briefs | ~52 | 5 briefs × ~10 lines each. Sibling-skill call. NEVER dropped. |
| Confluence | 17 | 15 records + section header + optional `_[truncated]_` line. |
| JIRA | 17 | MSP-gated; omitted entirely when off. |
| Recent PRs / commits | 17 | Heading varies by `gh` availability. |
| AWS docs | 17 | |
| Microsoft Learn | 17 | |
| Open questions surfaced | 15 | Free-form bullets; one per topic. |
| Footer (drop markers, if any) | 5 | `_[dropped: <section>]_` lines when overflow drops fired. |

Total upper bound: 6 + 20 + 52 + 17×5 + 15 + 5 = 183 lines for a full populated digest. The 250-line cap exists to absorb subagent line-cap slack and any rendering surprises. Anything over 250 triggers whole-record overflow drops (never-drop sections are exempt).

---

## Empty-section rendering

When a section returns no records, render the heading and a single-line note:

| Subagent return | Section body |
|---|---|
| `none` | `_none found_` |
| `auth-error: <msg>` | `_skipped: <msg>_` |
| `tool-unavailable` | section omitted entirely (no heading) |
| `gh-unavailable` | replace section with `## Recent commits touching <paths> (gh not available)` and re-dispatch commits-fallback subagent |
| time-budget exceeded with partial | render partial + `_[truncated: time budget]_` |

Empty sections are NOT a bug. They tell the next reader the source was checked and produced nothing. Suppressing them invites a future run to repeat the work.

---

## Record format (every bullet section)

```
- **<title>** — <url> — <one-line takeaway under 25 words>
```

`title` and `url` come verbatim from the source. The takeaway is the subagent's one-line summary — never paraphrased from full page contents (subagent prompts forbid full-page fetches for this reason).

JIRA records substitute `<ISSUE-KEY>` for `<title>` and `<summary>: status=<status>, updated=<YYYY-MM-DD>` for the takeaway. Commit records use `<sha>` for `<title>`, omit the URL field, and put `<commit-subject> — <YYYY-MM-DD>` as the takeaway.

---

## Open questions section

The `## Open questions surfaced` section captures topics the research couldn't resolve:

```markdown
## Open questions surfaced

- Confluence search hit 50 results for "auth flow" — too broad. Narrow to a specific service before next run.
- JIRA returned `none` but branch is `MSP-7032/...` — ticket exists; possibly access restricted.
- AWS docs section overflow-dropped; re-run with `total_lines: 350` if AWS context matters here.
```

In auto mode, this section is auto-populated from `none` / `[truncated]` / `dropped` events. In interactive mode, it's seeded the same way; the user may add bullets manually before passing the artifact to blueprint Phase 1.

---

## Footer (overflow drops)

When overflow drops fire (total exceeded 250 lines), append at the very end:

```markdown
---

<!-- overflow log -->
_[dropped: Microsoft Learn — total exceeded 250-line budget]_
_[dropped: AWS docs — total exceeded 250-line budget]_
```

Drops are applied lowest-priority-first. Local knowledge is NEVER dropped. The footer makes the drop visible without polluting the section bodies.

---

## Worked example (abbreviated)

```markdown
# Research — Stripe webhook handler

**Run at:** 2026-05-14T18:42:11Z
**Sources queried:** local-knowledge, library-briefs, confluence, jira, merged-prs, aws-docs, ms-learn
**Mode:** interactive
**Cache:** miss

## Local knowledge (from .claude-knowledge/)

### Gotchas (2 of 8)
- **[2026-04-02] Stripe webhook signature 400 on retry** — verify against raw bytes, not parsed body. (tags: stripe, webhooks)
- **[2026-03-18] Lambda cold start eats Stripe's 10s timeout** — provision concurrency for /webhooks endpoint. (tags: stripe, lambda)

### Patterns (1 of 4)
- **[2026-02-10] Webhook handlers idempotent via event.id table** — see services/billing/webhooks.ts. (tags: idempotency, billing)

## Library briefs (from ~/.claude/data/library-briefs/)

### library-brief: stripe (js, v16.2.0, updated 2026-04-15)

**TL;DR:** Stripe Node.js SDK for payment processing; v16 aligns with Stripe's new synchronous Payment Intents flow.

**Mental model (digest):** Stripe wraps REST calls in typed objects. All money amounts are integers (cents). Webhooks carry a `type` field; signature verification requires the raw request body.

**Top gotchas:**
- Always verify webhook signature against raw bytes — parsed body breaks the HMAC.
- `idempotencyKey` required on retried charge/payment_intent calls to avoid double-charges.
- Test mode and live mode use different API keys; key type is encoded in the prefix (`sk_test_` vs `sk_live_`).

**Full brief:** `~/.claude/data/library-briefs/js/stripe.md`

## Confluence
- **Stripe Integration Runbook** — https://nicusa.atlassian.net/wiki/spaces/ENG/pages/123 — covers retry semantics, IP allowlist, secret rotation
- **Billing Architecture Decision Log** — https://nicusa.atlassian.net/wiki/spaces/ENG/pages/456 — Stripe chosen over Adyen 2024-08

## JIRA — related tickets
- **MSP-7032** — https://nicusa.atlassian.net/browse/MSP-7032 — Add Stripe webhook handler: status=In Progress, updated=2026-05-13
- **MSP-6810** — https://nicusa.atlassian.net/browse/MSP-6810 — Stripe webhook 5xx spike: status=Done, updated=2026-04-02

## Recent PRs touching services/billing/
- **#1842** — https://github.com/org/repo/pull/1842 — Add idempotency table for webhook events (merged 2026-04-10)
- **#1791** — https://github.com/org/repo/pull/1791 — Promote /webhooks to provisioned concurrency (merged 2026-03-20)

## AWS docs
- **API Gateway: Configure Timeouts** — https://docs.aws.amazon.com/apigateway/... — webhook integration timeout default 30s, max 30s
- **Lambda Provisioned Concurrency** — https://docs.aws.amazon.com/lambda/... — eliminates cold-start latency for predictable traffic

## Microsoft Learn
_none found_

## Open questions surfaced

- Should we use SQS between API Gateway and the webhook Lambda for replay durability? (not in any source)
- Confluence has a 2023 doc on Adyen migration — still relevant if we ever rotate?

---
```

The above is ~40 lines for a real research run. The 250-line budget rarely binds in practice; when it does, the overflow rules above apply.
