# CONTEXT.md Format

Adapted from Matt Pocock's `grill-with-docs` skill (https://github.com/mattpocock/skills).

`CONTEXT.md` is a project glossary — opinionated, tight, and devoid of implementation detail. It's NOT a spec, NOT a scratch pad, NOT a place to dump decisions (use ADRs for those). Its sole job: pin down what each domain term means in this project so future engineers and LLMs don't drift.

## Structure

```md
# {Context Name}

{One or two sentence description of what this context is and why it exists.}

## Language

**Order**:
A request a customer has placed; tracked from placement through fulfillment.
_Avoid_: Purchase, transaction

**Invoice**:
A request for payment sent to a customer after delivery.
_Avoid_: Bill, payment request

**Customer**:
A person or organization that places orders.
_Avoid_: Client, buyer, account

## Flagged ambiguities

**"Account"** — used in two senses in the code:
- Customer account (the buying entity) → use **Customer**
- Internal billing account (the ledger record) → use **Ledger**
Resolution: avoid the bare term "account" outside narrowly scoped contexts.

## Example dialogue

> Dev: "When an Order is cancelled, do we void the Invoice?"
> Domain expert: "Only if the Order is cancelled before the Invoice is sent. After sending we issue a Credit Note against the Invoice."
```

## Rules

- **Be opinionated.** When multiple words exist for the same concept, pick the best one and list the others under `_Avoid_:` as aliases.
- **Flag conflicts explicitly.** If a term is used ambiguously, surface it in a "Flagged ambiguities" section with a clear resolution.
- **Keep definitions tight.** One or two sentences max. Define what it IS, not what it does.
- **Show relationships.** Use bold term names and express cardinality where obvious ("one Customer has many Orders").
- **Only project-specific terms.** General programming concepts (timeouts, retries, error types) don't belong even if the project uses them heavily. Before adding a term, ask: is this unique to this domain, or is it general?
- **Group under subheadings** when natural clusters emerge. Flat list is fine when the glossary is small.
- **Write an example dialogue.** A short exchange that demonstrates how the terms interact and clarifies boundaries between adjacent concepts.

## Single vs multi-context repos

**Single context (most repos):** one `CONTEXT.md` at the repo root.

**Multiple contexts:** a `CONTEXT-MAP.md` at the repo root names the contexts and their boundaries:

```md
# Context Map

## Contexts

- [Ordering](./src/ordering/CONTEXT.md) — receives and tracks customer orders
- [Billing](./src/billing/CONTEXT.md) — generates invoices and processes payments
- [Fulfillment](./src/fulfillment/CONTEXT.md) — manages warehouse picking and shipping

## Relationships

- **Ordering → Fulfillment**: Ordering emits `OrderPlaced`; Fulfillment consumes it to start picking.
- **Fulfillment → Billing**: Fulfillment emits `ShipmentDispatched`; Billing generates invoices.
- **Ordering ↔ Billing**: Shared types for `CustomerId` and `Money`.
```

Inference rules:
- `CONTEXT-MAP.md` present → multi-context. Route updates to the relevant sub-context.
- Only a root `CONTEXT.md` → single context.
- Neither exists → create a root `CONTEXT.md` lazily the first time a term is resolved (with-docs mode only).

When multi-context and unclear which one a topic belongs to: ask.
