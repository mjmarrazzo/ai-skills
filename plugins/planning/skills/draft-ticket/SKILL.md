---
name: draft-ticket
description: Use this skill whenever the user wants to scope and create a single JIRA ticket whose body is detailed enough for another team or another LLM to plan and implement from — triggers include "draft a ticket", "draft a JIRA ticket", "build a ticket", "scope a ticket", "write up a ticket for X", "ticket for this work", "make a ticket", "workshop a ticket", "let's nail down requirements", "another team will pull this in", or any prompt where the user is explicitly scoping work they will hand off rather than implement themselves. Drives a light discovery → optional verification → high-level bullets → full ticket draft → workshop loop → JIRA target confirm → create flow. Interactive only — no auto mode. One ticket per invocation; for multi-ticket spec decomposition use atlassian:spec-to-backlog, for meeting-notes ingestion use atlassian:capture-tasks-from-meeting-notes, for "I'll implement this myself" use blueprint. Skip when the user says "blueprint this" / "plan this" (heavier workflow desired), "just create the ticket with X" with all details supplied AND explicitly opts out of workshop (no workshop needed, one-shot create), or is mid-implementation and merely tracking already-decided work in JIRA.
---

# Draft Ticket

A workshop flow that produces ONE JIRA ticket whose body is detailed enough for a downstream LLM (or another team) to run `blueprint` against without re-interrogating the requester. Interactive only — every gate is a real human gate.

**Announce at start:** "Using draft-ticket to scope, workshop, and create this ticket."

## When to run, when to skip

Run when:
- User wants to scope upcoming work they aren't going to implement themselves.
- User uses any trigger phrase in the description frontmatter.
- The deliverable is one ticket, not a backlog.

Skip when:
- User says "blueprint this" / "plan this" — they want the heavier `blueprint` workflow with `handoff.md` + `spec.v*.md` + `plan.v*.md`.
- User explicitly says "just create the ticket, no workshop" with all required fields supplied — call `mcp__claude_ai_Atlassian__createJiraIssue` directly. (If the user supplies rich detail but doesn't opt out of workshop, run the fast-path described in Phase 2.)
- User is mid-implementation and asking to "track this in JIRA" — one-shot create, no workshop.
- Input is a meeting-notes doc → `atlassian:capture-tasks-from-meeting-notes`.
- Input is a full spec doc to decompose → `atlassian:spec-to-backlog`.

## Workspace

**None.** This skill writes nothing to disk by default. The final ticket lives in JIRA. On completion, the skill offers (once, low-key) to save the markdown body to `./<KEY>.md` at cwd; default no.

Anti-pattern: do not open `.claude-plans/`, do not write `handoff.md`, do not write `spec.v*.md`. That is `blueprint` territory.

## Phases

```
1. Recon → 2. Discovery wave(s) → 3. Optional verify (opt-in) → 4. High-level bullets
                                                              → 5. Full ticket draft → 6. Workshop loop
                                                              → 7. JIRA target confirm → 8. Create + transition
```

### Phase 1 — Recon (silent unless surfaces a question)

- Read repo `CLAUDE.md` if present, plus global `~/.claude/CLAUDE.md` for JIRA defaults (`cloudId`, project key, conventions). The `cloudId` discovered here is propagated to **every** Atlassian MCP call later in the skill — none of those calls work without it.
- If `cloudId` is absent from both files, fetch it via `mcp__claude_ai_Atlassian__getAccessibleAtlassianResources` at Phase 7 before any other JIRA call.
- All Atlassian MCP tools below are deferred — preload schemas via `ToolSearch` with query `select:mcp__claude_ai_Atlassian__createJiraIssue,mcp__claude_ai_Atlassian__getVisibleJiraProjects,mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql,mcp__claude_ai_Atlassian__getTransitionsForJiraIssue,mcp__claude_ai_Atlassian__transitionJiraIssue,mcp__claude_ai_Atlassian__getJiraProjectIssueTypesMetadata,mcp__claude_ai_Atlassian__getAccessibleAtlassianResources` before Phase 7. Skip if they're already loaded in the session.
- Read 1–2 files the user mentions by path or that obviously match the subject. Do NOT scan the whole repo.
- If the user references "the way <sibling> does it" and a sibling repo / directory is available (e.g. via `/add-dir`), read the referenced sibling code as ground truth — it settles questions faster than asking.
- If `knowledge-capture` is installed (`~/.claude/skills/knowledge-capture/SKILL.md` or `~/.claude/plugins/cache/**/skills/knowledge-capture/SKILL.md` exists), invoke with `caller=draft-ticket` for the repo's known gotchas. Skip if not installed; mention once.
- If the user explicitly references internal systems the recon files don't explain and `atlassian:search-company-knowledge` is installed, optional one call.

No artifacts written. No questions asked yet.

### Phase 2 — Discovery wave(s)

Max **2 waves total**. Cap exists because the user is going to workshop the draft anyway — don't drain patience up front.

**Fast-path:** if the user's invocation already covers subsystem/scope/acceptance signals, skip both waves and proceed directly to Phase 4 (high-level bullets). The workshop loop still catches gaps.

**Wave 1 (default):** structured `AskUserQuestion` for clean-option-set choices. Examples:
- Which subsystem owns this work?
- Sync or async?
- Extend an existing module or create a new one?
- What's the integration boundary?

1–4 questions in one call.

**Wave 2 (only if needed):** free-form follow-ups for invariants only the user knows. Single message, 1–3 questions. Examples: edge cases they've hit before, performance constraints, compliance asks, who else is touching this area.

If 2 waves aren't enough, proceed to high-level bullets anyway. The workshop loop will pull out the rest.

### Phase 3 — Optional verification (skipped by default)

Offer only when BOTH:
- The user's request asserts external behavior (API contract shape, auth header format, endpoint URL, schema field, idempotency).
- The answer is not already in the files read during Phase 1.

Offer pattern (single `AskUserQuestion`):
> I'd like to verify <specific assumption> by <one-liner of what I'd run>. OK to proceed?
> Options: yes / skip / I'll verify myself.

If yes:
- Pull any required secrets via the project's existing patterns (DynamoDB `GetItem`, SSM `GetParameter`, etc.). Never ask the user to paste credentials. If the repo has no such pattern, suppress the verification offer for this invocation.
- Show every command before running. Use Bash directly for `curl`, `aws`, etc.
- **Read-only by default.** Any mutation against a shared env requires a SECOND, per-mutation approval — never batch mutation approvals.
- Whole phase capped at ~3 minutes of trials. If it's growing, abort and surface the assumption as an "Asks for consideration" in the ticket instead.

Findings fold into the "Background" section of the eventual ticket body, with the exact command run + redacted result.

Secrets/credential redaction: if a verification result contains a value matching `(?i)(key|token|secret|password|bearer)`, replace with `<redacted>` in the ticket body.

### Phase 4 — High-level bullet draft

Print a **numbered bullet list** in chat covering:
- The proposed ticket title (one line).
- The headline of each section the full draft will contain.
- Decisions locked from discovery (one bullet each).

NOT in the high-level draft: code blocks, acceptance criteria text, file:line refs. Those land in the full draft.

Ask: "Anything missing or wrong at this level before I expand?"

On structural feedback → loop back into Phase 2 or revise the bullets. On approval → Phase 5.

If the subject is too vague to bullet honestly, surface the gaps as questions instead of dumping placeholder bullets. Never write "TBD" rows.

### Phase 5 — Full ticket draft

One fenced markdown block in chat, following `references/ticket-template.md`. Required sections in order:

1. **Summary** — 1–3 sentences.
2. **Background** — includes verified findings if Phase 3 ran.
3. **Scope** — affected services / files with absolute or repo-relative paths.
4. **Out of scope** — skip if empty.
5. **Acceptance criteria** — numbered, behavior-level, independently verifiable.
6. **Asks for consideration** *(non-blocking)*.
7. **References** — skip if empty.

Rules:
- No "TBD" or "N/A". Skip the section instead.
- Absolute paths and `file:line` refs when describing existing code.
- Skip bullets that just restate things that aren't changing — they muddy the read.
- Plain markdown; no HTML.

### Phase 6 — Workshop loop

After every full draft:
> Anything wrong, missing, or worth tightening?

On feedback → regenerate the FULL ticket block with edits applied. Do NOT show diffs or changelog between rounds; the user owns the comparison.

User signals approval with: "looks good", "approve", "ship it", "send it", or equivalent.

Stall protection: after 5 rounds, prompt "Want to ship this version, or take a break?" — on break, print final body, exit.

### Phase 7 — JIRA target confirmation

Determine fields, in this precedence order for each:

| Field | Precedence |
|---|---|
| **`cloudId`** | repo `CLAUDE.md` → global `~/.claude/CLAUDE.md` → `mcp__claude_ai_Atlassian__getAccessibleAtlassianResources` |
| **Project key** | explicit user override → repo `CLAUDE.md` → global `~/.claude/CLAUDE.md` (default MSP) → ask via `mcp__claude_ai_Atlassian__getVisibleJiraProjects` |
| **Issue type** | explicit override → inferred (bug-language → Bug, "spike"/"investigate" → Task, default → Story) |
| **Component** | explicit override (validated against project metadata) → discovered via JQL search on recent tickets matching the affected service area → `AskUserQuestion` with top 1–3 candidates + "other (specify)" |
| **Initial status** | explicit override → project default; transition only if non-default named |

Every `mcp__claude_ai_Atlassian__*` call below takes `cloudId` as a parameter. The skill MUST pass the resolved `cloudId` to: `getVisibleJiraProjects`, `getJiraProjectIssueTypesMetadata`, `searchJiraIssuesUsingJql`, `createJiraIssue`, `getTransitionsForJiraIssue`, `transitionJiraIssue`. Missing `cloudId` is the most common failure mode.

Component discovery query pattern:
```
project = <KEY> AND text ~ "<service-or-feature-name>" ORDER BY updated DESC
```
Extract the `components` field from the top 5–10 results, dedupe, present top 3 by frequency. Fallback ladder:
- Zero results or no component field populated → prompt free-form for component name; validate against `mcp__claude_ai_Atlassian__getJiraProjectIssueTypesMetadata`.
- More than 3 candidates with no clear winner (top candidate <40% of results) → present top 5 instead of 3 and add "none of these" as an option.
- Typo on free-form entry → retry once with fuzzy-match suggestion.

Final confirmation (single `AskUserQuestion`): show `{cloudId, project, issueType, component, status, summary}` block. Options: Create / Edit field / Cancel.

### Phase 8 — Create + transition

- Call `mcp__claude_ai_Atlassian__createJiraIssue` with `cloudId` + confirmed fields. Description = workshopped markdown body verbatim.
- If a non-default initial status was requested: `mcp__claude_ai_Atlassian__getTransitionsForJiraIssue` → `mcp__claude_ai_Atlassian__transitionJiraIssue` (both take `cloudId`).
- Return to user:
  - Ticket key + URL.
  - One-line summary of decisions locked during workshop (≤3 bullets).
- Offer once: "Want me to save the body to `./<KEY>.md`?" Default no; only write on explicit yes.

## Error handling

**JIRA MCP unreachable / unauthorized:** at Phase 7 confirm, surface the error, print the final ticket body to chat, ask user to create manually. Do NOT retry silently.

**User cancels at Phase 7:** print final ticket body, offer save-to-disk, exit.

**`mcp__claude_ai_Atlassian__getVisibleJiraProjects` returns no projects:** ask the user for the project key directly and validate via `mcp__claude_ai_Atlassian__getJiraProjectIssueTypesMetadata`.

**Component lookup returns nothing or no clear winner:** see "Fallback ladder" under Phase 7.

**`cloudId` missing and `getAccessibleAtlassianResources` fails:** surface the error, print the final ticket body to chat, ask the user to create the ticket manually with the body provided.

## Composition with sibling skills

| Sibling | Used how |
|---|---|
| `knowledge-capture` | Phase 1 read-only digest if installed. |
| `atlassian:search-company-knowledge` | Optional Phase 1 call when scoping pulls in internal systems not in recon files. |
| `blueprint` | Mutually exclusive. "blueprint this" / "plan this" defers there. |
| `atlassian:spec-to-backlog` | Mutually exclusive — multi-ticket-from-spec. |
| `atlassian:capture-tasks-from-meeting-notes` | Mutually exclusive — ticket-from-doc. |
| `tech-brief` | NOT used. |

Sibling install probe: file existence at `~/.claude/skills/<name>/SKILL.md` or `~/.claude/plugins/cache/**/skills/<name>/SKILL.md`. Mention once if missing, continue.

## Anti-patterns

- **Don't open `.claude-plans/` workspaces, write `handoff.md`, or `spec.v*.md`.** That's `blueprint` territory.
- **Don't write the ticket body to a file unless the user explicitly says yes.** Print to chat; JIRA is the source of truth.
- **Don't auto-create tasks via TaskCreate for the workshop itself.** Tasks are for execution work, not for chat flows.
- **Don't dump the full ticket as the first deliverable.** High-level bullets first, full draft second.
- **Don't add an auto mode.** Interactive is the methodology; auto defeats the point.
- **Don't run verification by default.** Phase 3 is conditional — only offered when the user's request asserts external behavior AND recon didn't already answer it. If neither condition holds, skip the phase entirely; don't ask "want me to verify anything?" as a default prompt.
- **Don't ask the user to paste credentials.** If the repo has no DDB/SSM pattern for secrets, suppress the verification offer entirely.
- **Don't ship a ticket with "TBD" rows.** Either pull it out of the user or move it to "Asks for consideration".
- **Don't split one request into multiple tickets or an epic.** One ticket per invocation. Backlog decomposition belongs to `atlassian:spec-to-backlog`.
- **Don't parse meeting notes, Confluence pages, or spec docs as input.** Route the user to `atlassian:capture-tasks-from-meeting-notes` or `atlassian:spec-to-backlog`.
- **Don't call any Atlassian MCP tool without `cloudId`.** Every call requires it; resolve in Phase 1 / Phase 7.

## Inputs accepted

Parsed loosely from the user's invocation message:
- Free-text subject (required).
- Optional project key override ("in project FOO", "project=FOO").
- Optional component override ("component=Onboarding").
- Optional initial status ("in To Do", "as Backlog").

## Outputs

- Final ticket markdown body (printed in chat; the workshop already produced this).
- JIRA ticket key + URL.
- One-line summary of decisions locked during the workshop.
- Optional saved file at `./<KEY>.md` if the user opted in at Phase 8.
