# handoff.md template

The handoff dossier exists so a fresh LLM (or a returning human after a week) can pick up the work cold at Phase 2. Optimize for "ramp up in 5 minutes", not for completeness.

## Own what nothing else can regenerate

The handoff's durable value is the record of **what you said and what got decided** — constraints and their sources, discovery Q&A, deferred scope. Nothing downstream can reconstruct that from the code.

Its other half — repo orientation and contract research — exists to feed spec drafting, and is superseded once `spec.v<N>.md` lands. That's fine; it just means the handoff is a Phase 2 input, not an execution-time document.

**Cite upstream contracts; don't reproduce them.** If an external API's full status/error table shapes the design, give the two or three facts that actually constrain the architecture plus the citation (`../other-repo/docs/api.yaml:293-441`). The full table belongs in the spec, where it's the contract being implemented. Reproducing it here means two copies that drift the moment the spec is revised.

**Link to source files; don't paraphrase them.**

```markdown
# <Slug> — Handoff

**Goal (one sentence):** <what we're building, in plain language>

**Ticket / source:** <PROJ-XXXX link, GitHub issue, Slack thread, or "ad-hoc request from user">

**Date opened:** YYYY-MM-DD

## Context

2-4 short paragraphs. What is the user trying to accomplish at the business / product level?
Why now? What changes for users or other systems when this lands?

## Repo orientation

Where in the codebase this work lives. Bulleted, with file paths.

- `path/to/relevant/module.py` — <one-line role>
- `path/to/other/file.ts:120-180` — <one-line role>

Note conventions specific to this area that a fresh reader wouldn't infer from the file alone
— testing approach, error-handling style, dependency-injection pattern, bundler-enforced
naming rules. Conventions only; the repo's verify commands belong in the plan's `Verify:`
steps, where they're actually run.

## Constraints

Things the spec MUST satisfy. Include the source for each — "user said in discovery", "ticket
acceptance criteria", "AWS quota", "existing API contract":

- <constraint> — <source>

## Out of scope

Things that came up in discovery and were deferred. Saves the next reader re-litigating them.

- <thing> — <why deferred>

## Open questions resolved during discovery

Q&A captured from the questionnaire:

> **Q:** <question asked>
> **A:** <user's answer> — <one-line implication>

## Open questions still outstanding

If any. Mark clearly so the spec flags them.

## Pointers

- Related docs: <links>
- Adjacent work / prior art: <PRs, commits, files>
- Upstream contracts: <repo path + file:line — cite, don't copy>
```

If this workspace continues prior work, the relevant deferred decisions from the previous `open-questions.md` go into **Constraints** or **Out of scope** with `— carried over from <prior workspace>` as the source. They don't get their own section; a decision that matters is a constraint, and one that doesn't shouldn't be restated.
