# handoff.md template

The handoff dossier exists so a fresh LLM (or a returning human after a week) can pick up the work cold. Optimize for "ramp-up in 5 minutes", not for completeness. Link to source files; don't paraphrase them.

```markdown
# <Slug> — Handoff

**Goal (one sentence):** <what we're building, in plain language>

**Ticket / source:** <MSP-XXXX link, GitHub issue, Slack thread, or "ad-hoc request from user">

**Date opened:** YYYY-MM-DD

## Context

2-4 short paragraphs. What is the user trying to accomplish at the business / product level? Why now? What changes for users / other systems when this lands?

## Repo orientation

Where in the codebase this work lives. Bulleted, with file paths.

- `path/to/relevant/module.py` — <one-line role>
- `path/to/other/file.ts:120-180` — <one-line role>

Note any patterns / conventions specific to this area (testing approach, error handling, dependency injection style) that a fresh reader wouldn't infer from the file alone.

## Constraints

Things the spec MUST satisfy. Include the source for each — "user said in discovery", "ticket acceptance criteria", "AWS quota", "existing API contract":

- <constraint> — <source>
- <constraint> — <source>

## Out of scope

Explicitly call out things that came up in discovery but were deferred. Saves the next reader from re-litigating them.

- <thing> — <why deferred>

## Open questions resolved during discovery

Q&A captured from the questionnaire. Format:

> **Q:** <question asked>
> **A:** <user's answer> — <one-line implication>

## Open questions still outstanding

If any. Mark them clearly so the spec can flag them.

## Pointers

- Related docs: <links>
- Adjacent work / prior art: <PRs, commits, files>
- People to ask: <names, roles> (only if the user surfaced them)

## Continuation log (from prior `open-questions.md`)

If this workspace continues work from a prior session, summarize what the prior `open-questions.md` flagged. Otherwise omit the section.
```
