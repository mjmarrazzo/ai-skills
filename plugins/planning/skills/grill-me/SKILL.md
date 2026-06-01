---
name: grill-me
description: Use this skill when the user wants to stress-test a plan, design, or proposal through a relentless one-question-at-a-time interview. Triggers on "grill me", "grill me on this", "stress-test the plan", "challenge my design", "interview me", "poke holes", "/grill", "/grill-me". With-docs variants ("grill me with docs", "grill me and update context", "grill me, ADRs ok") additionally sharpen domain language inline into `CONTEXT.md` and offer ADRs sparingly when decisions are hard-to-reverse AND surprising-without-context AND result-of-a-real-trade-off. Default mode does NOT write outside the skill dir. Skip on explicit opt-out ("just do it", "no grilling") or when there's no plan to interrogate.
---

# Grill Me

Relentless one-question-at-a-time interview that stress-tests a plan, design, or proposal. Inspired by Matt Pocock's `grill-with-docs` ([github.com/mattpocock/skills](https://github.com/mattpocock/skills)). Walks the decision tree branch-by-branch, resolves dependencies between choices, and forces precision on overloaded terms. Every question ships with the agent's recommended answer + one-line reasoning so the user can `accept`, `reject`, or redirect.

**Announce at start:** `Grilling on. One question at a time. I'll recommend an answer for each — accept, reject, or send me to read something.`

## When to run, when to skip

Run when:
- User says "grill me", "challenge this", "stress-test", "poke holes", "/grill", "/grill-me".
- User invokes the skill mid-design or mid-planning and wants pushback before committing.

Skip when:
- User explicitly opts out ("no grilling", "just do it", "skip the interview").
- No plan or design has been supplied AND user can't articulate one when asked.
- Running in auto mode (see Auto-mode section — interview requires a human).

## Modes

### Default (interview only)
1. **Read input.** If no plan was supplied with the trigger, ask: "What plan or design should I grill you on?" Wait.
2. **Recon, read-only, in parallel where independent.** CLAUDE.md, README, the directory the plan touches, any `CONTEXT.md` / `CONTEXT-MAP.md`. Don't write anything in default mode.
3. **Build decision tree mentally.** Identify branches, dependencies between decisions, ambiguous terms, untested assumptions, contradictions between user's claims and the code.
4. **Loop.** Pick the next-most-load-bearing unanswered question, prefer codebase exploration over asking when the answer is in the code, then ask ONE question using the template below. Accept reply. Update state. Surface contradictions immediately ("Your code at `path:line` does X, but you just said Y — which is right?").
5. **Exit** when the user says "done"/"enough"/"good" OR no load-bearing questions remain. Print summary.

### With-docs (opt-in)
Trigger via "grill me with docs", "update context as we go", "grill me, ADRs ok", or arg `--docs`. Adds to the default loop:
- **Glossary updates inline.** When a term is resolved, append/update `CONTEXT.md` immediately — don't batch. Single-context repos: root `CONTEXT.md`. Multi-context: route via `CONTEXT-MAP.md`. Format in `references/CONTEXT-FORMAT.md`.
- **Conflict-with-glossary callouts.** If user uses a term that conflicts with an existing entry, stop and resolve before moving on.
- **ADR offers, sparingly.** Only offer an ADR when ALL three hold:
  1. Hard to reverse
  2. Surprising without context (a future reader would wonder "why?")
  3. Result of a real trade-off (genuine alternatives were considered)
  On user `yes`, write `docs/adr/NNNN-slug.md` (NNNN = max existing + 1; create dir lazily). Format in `references/ADR-FORMAT.md`.

### Auto-mode
Grill IS the interview — no human means no grill. If invoked in auto mode without a pre-canned answer file (out of scope v1), print:

> `grill-me requires an interactive human; exiting cleanly. Re-invoke without auto mode.`

…and exit. No further work.

## Question template

What the user sees each round:

```
Q<n>: <question, anchored with file:line when applicable>

Recommended answer: <agent's call>
Why: <one line>

(accept / reject / explain / read <path> / skip)
```

Reply handling:
- `accept` — lock the recommendation, move to next branch.
- `reject` or free text — record user's answer, move on.
- `explain` — agent expands reasoning, then re-asks.
- `read <path>` — agent reads the file, re-asks (possibly with revised recommendation).
- `skip` — log to deferred list, surface in exit summary.

## Exit summary template

```
Grill complete. Sharpened:
- <item 1>
- <item 2>
...
Deferred (skipped): <list or "none">
Glossary updated: <terms or "none">       # with-docs mode only
ADRs created: <paths or "none">           # with-docs mode only
```

## Composition with siblings

Loose coupling — grill-me works standalone. When siblings are installed:
- **`knowledge-capture`:** at session start (with-docs mode), read its digest if installed — known repo gotchas inform which questions to lead with.
- **`tech-brief`:** if libraries are named in the plan and briefs exist at `~/.claude/data/tech-briefs/<ecosystem>/<lib>.md`, fold relevant excerpts into recon.
- **`blueprint`:** blueprint Phase 1 MAY offer to invoke grill-me before drafting `spec.v1.md`. If grill-me detects an active `.claude-plans/<workspace>/` directory, it appends its exit summary to that workspace's `decisions.md`.
- **`vscode-preview`:** after writing/updating `CONTEXT.md` or an ADR (with-docs mode), offer to open it in preview.

If a sibling isn't installed, mention once and proceed without it.

## Anti-patterns

- **Don't batch questions.** One at a time. Multi-question dumps overwhelm and tank precision. If you have five questions, ask the most load-bearing one and let the answer collapse the others.
- **Don't write `CONTEXT.md` or ADRs in default mode.** Docs mode is opt-in. Surprise writes to the user's repo destroy trust.
- **Don't keep grilling past "done".** When the user signals exit, stop and summarize. Past N rounds you're chasing diminishing returns and burning goodwill.
- **Don't offer an ADR for every decision.** The three-criteria gate exists because ADR sprawl is real. If any of the three is missing, skip.
- **Don't ask what the codebase can answer.** If a question is answerable by reading code, read it and either skip the question or anchor a sharper one with `file:line`.
- **Don't argue past the user's stated constraint.** If they said "must use REST, no GraphQL", don't keep probing whether GraphQL might be better. Probe inside the constraint.
