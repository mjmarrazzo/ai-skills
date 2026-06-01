# ADR Format

Adapted from Matt Pocock's `grill-with-docs` skill (https://github.com/mattpocock/skills).

Architecture Decision Records live in `docs/adr/` with sequential numbering: `0001-slug.md`, `0002-slug.md`, etc. Create the `docs/adr/` directory **lazily** — only when the first ADR is actually written.

## When to offer an ADR

All three must hold. If any one is missing, skip:

1. **Hard to reverse.** The cost of changing your mind later is meaningful — a schema migration, a vendor lock-in, a public API contract.
2. **Surprising without context.** A future reader looking at the code will wonder "why did they do it this way?" If the choice is obvious, no ADR needed.
3. **Result of a real trade-off.** Genuine alternatives existed and you picked one for specific reasons. If there was no real alternative, there's nothing to record.

## Template

```md
# {Short title of the decision}

{1-3 sentences: context, what was decided, and why.}
```

That's the default. An ADR can be a single paragraph. The value is in recording *that* a decision was made and *why* — not in filling out boilerplate sections.

## Optional sections

Only include when they add real value. Most ADRs won't need them:

- **Status frontmatter** (`proposed | accepted | deprecated | superseded by ADR-NNNN`) — useful when decisions get revisited.
- **Considered alternatives** — only when the rejected paths are worth remembering.
- **Consequences** — only when non-obvious downstream effects need a callout.

## Numbering

Scan `docs/adr/` for the highest existing number and increment by one. Slug = kebab-case summary of the decision (e.g. `0007-event-sourced-orders.md`).

## What qualifies

- **Architectural shape.** "Monorepo." "Event-sourced write model, projected read model."
- **Integration patterns between contexts.** "Ordering and Billing communicate via domain events, not synchronous HTTP."
- **Technology choices that carry lock-in.** Database, message bus, auth provider, deployment target — the ones that would take a quarter to swap out. Not every library.
- **Boundary and scope decisions.** "Customer data is owned by the Customer context; others reference by ID only." Explicit no-s are as valuable as yes-s.
- **Deliberate deviations from the obvious path.** "Manual SQL, no ORM, because X." Anything where a reasonable reader would assume the opposite — these stop the next engineer from "fixing" something deliberate.
- **Constraints not visible in code.** "No AWS — compliance." "Response times < 200ms — partner contract."
- **Rejected alternatives when the rejection is non-obvious.** If you considered GraphQL and picked REST for subtle reasons, record it — otherwise someone will re-suggest GraphQL in six months.

## What doesn't qualify

- Style choices (formatting, naming) — those go in lint config or a style guide.
- Decisions easily reversed by changing one file.
- Library picks where the alternatives are equivalent ("we used `axios` instead of `node-fetch`") — unless the choice carries lock-in.
- Anything that's just "we did the obvious thing."
