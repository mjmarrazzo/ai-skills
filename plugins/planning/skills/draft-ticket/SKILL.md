---
name: draft-ticket
description: Use this skill whenever the user wants to scope and create a single ticket or issue whose body is detailed enough for another team or another LLM to plan and implement from — triggers include "draft a ticket", "draft an issue", "build a ticket", "scope a ticket", "write up a ticket for X", "ticket for this work", "file an issue for", "make a ticket", "workshop a ticket", "let's nail down requirements", "another team will pull this in", or any prompt where the user is explicitly scoping work they will hand off rather than implement themselves. Drives a light discovery → optional verification → high-level bullets → full draft → workshop loop → tracker-target confirm → create flow. The destination tracker (GitHub issues, JIRA, or other) is resolved at create time, asking the user when it's unclear. Interactive only — no auto mode. One ticket per invocation; for "I'll implement this myself" use blueprint. Skip when the user says "blueprint this" / "plan this" (heavier workflow desired), "just create the ticket with X" with all details supplied AND explicitly opts out of workshop (one-shot create), or is mid-implementation and merely tracking already-decided work.
---

# Draft Ticket

A workshop flow that produces ONE ticket whose body is detailed enough for a downstream LLM (or another team) to run `blueprint` against without re-interrogating the requester. The destination tracker is resolved late — the body is tracker-agnostic, and only Phase 7 decides whether it lands as a GitHub issue, a JIRA ticket, or somewhere else. Interactive only — every gate is a real human gate.

**Announce at start:** "Using draft-ticket to scope, workshop, and create this ticket."

## When to run, when to skip

Run when:
- User wants to scope upcoming work they aren't going to implement themselves.
- User uses any trigger phrase in the description frontmatter.
- The deliverable is one ticket/issue, not a backlog.

Skip when:
- User says "blueprint this" / "plan this" — they want the heavier `blueprint` workflow with `handoff.md` + `spec.v*.md` + `plan.v*.md`.
- User explicitly says "just create the ticket, no workshop" with all required fields supplied — resolve the tracker (Phase 7) and create directly. (If the user supplies rich detail but doesn't opt out of workshop, run the fast-path described in Phase 2.)
- User is mid-implementation and asking to "track this" — one-shot create, no workshop.
- Input is a meeting-notes doc or a full spec to decompose into many tickets — that's multi-ticket work, out of scope here. If an Atlassian sibling skill for that is installed, route to it; otherwise tell the user this skill does one ticket per run.

## Workspace

**None.** This skill writes nothing to disk by default. The created ticket lives in its tracker. On completion, the skill offers (once, low-key) to save the markdown body to `./<KEY>.md` at cwd; default no.

Anti-pattern: do not open `.claude-plans/`, do not write `handoff.md`, do not write `spec.v*.md`. That is `blueprint` territory.

## Phases

```
1. Recon → 2. Discovery wave(s) → 3. Optional verify (opt-in) → 4. High-level bullets
                                                              → 5. Full draft → 6. Workshop loop
                                                              → 7. Tracker target confirm → 8. Create + transition
```

### Phase 1 — Recon (silent unless surfaces a question)

- Read repo `CLAUDE.md` if present, plus global `~/.claude/CLAUDE.md`, for any tracker config the user has set (a default GitHub repo + labels, or a JIRA `cloudId` + project key + conventions). Whatever you find here seeds Phase 7 — but don't assume a tracker yet.
- Read 1–2 files the user mentions by path or that obviously match the subject. Do NOT scan the whole repo.
- If the user references "the way <sibling> does it" and a sibling repo / directory is available (e.g. via `/add-dir`), read the referenced sibling code as ground truth — it settles questions faster than asking.
- If `knowledge-capture` is installed (`~/.claude/skills/knowledge-capture/SKILL.md` or `~/.claude/plugins/cache/**/skills/knowledge-capture/SKILL.md` exists), invoke with `caller=draft-ticket` for the repo's known gotchas. Skip if not installed; mention once.
- If the user explicitly references internal systems the recon files don't explain and a company-knowledge search skill is installed, optional one call.

No artifacts written. No questions asked yet. Tracker tool schemas (Atlassian MCP, `gh`) are NOT preloaded here — defer that to Phase 7 once the destination is known, so a GitHub-only run never touches Atlassian and vice versa.

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
- Pull any required secrets via the project's existing patterns (cloud secret store, parameter store, etc.). Never ask the user to paste credentials. If the repo has no such pattern, suppress the verification offer for this invocation.
- Show every command before running. Use Bash directly for `curl`, cloud CLIs, etc.
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

One fenced markdown block in chat, following `references/ticket-template.md`. The template is tracker-neutral — plain markdown that reads correctly in a GitHub issue or a JIRA description alike. Required sections in order:

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

### Phase 7 — Tracker target confirmation

The body is done; now decide where it lands. **Resolve the tracker before preloading any tracker tooling.**

**Determine the destination, in precedence order:**
1. **Explicit in the request** — "as a GitHub issue", "file it on the repo", "make a JIRA ticket", "in project FOO". Honor it.
2. **Config signal from Phase 1** — a JIRA `cloudId`/project in `CLAUDE.md`, or a GitHub default repo. A signal is a lean, not a lock.
3. **Repo signal** — `git remote get-url origin` points at a GitHub host and `gh auth status` succeeds → GitHub is a natural default.
4. **Still ambiguous → ask.** Single `AskUserQuestion`:
   > Where should this land?
   > - GitHub issue (this repo)
   > - JIRA ticket
   > - Other tracker — I'll hand you the finished body to paste/file yourself

Once the destination is known, preload only that tracker's tools:
- **GitHub:** `gh` is a CLI — no schema preload needed.
- **JIRA:** preload via `ToolSearch` query `select:mcp__claude_ai_Atlassian__createJiraIssue,mcp__claude_ai_Atlassian__getVisibleJiraProjects,mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql,mcp__claude_ai_Atlassian__getTransitionsForJiraIssue,mcp__claude_ai_Atlassian__transitionJiraIssue,mcp__claude_ai_Atlassian__getJiraProjectIssueTypesMetadata,mcp__claude_ai_Atlassian__getAccessibleAtlassianResources`. Skip if already loaded.

**GitHub branch — resolve fields:**

| Field | How |
|---|---|
| **Repo** | `gh repo view --json nameWithOwner` (or explicit `owner/repo` from the request) |
| **Labels** | explicit override → suggest from `gh label list` matching the subject area → ask via `AskUserQuestion` with top candidates + "none". Optional. |
| **Assignee / milestone** | only if the user named one |

Final confirmation (single `AskUserQuestion`): show `{repo, title, labels}`. Options: Create / Edit field / Cancel.

**JIRA branch — resolve fields:**

| Field | How |
|---|---|
| **`cloudId`** | `CLAUDE.md` → `~/.claude/CLAUDE.md` → `mcp__claude_ai_Atlassian__getAccessibleAtlassianResources`. Every Atlassian call needs it; missing `cloudId` is the most common failure. |
| **Project key** | explicit user override → `CLAUDE.md` config → ask via `mcp__claude_ai_Atlassian__getVisibleJiraProjects`. No hardcoded default — if nothing's configured, ask. |
| **Issue type** | explicit override → inferred (bug-language → Bug, "spike"/"investigate" → Task, default → Story) |
| **Component** | explicit override (validated against project metadata) → discovered via JQL on recent tickets in the affected area → `AskUserQuestion` with top 1–3 candidates + "other" |
| **Initial status** | explicit override → project default; transition only if a non-default status was named |

Component discovery query:
```
project = <KEY> AND text ~ "<service-or-feature-name>" ORDER BY updated DESC
```
Extract `components` from the top 5–10 results, dedupe, present top 3 by frequency. Fallback: zero results → free-form prompt validated against `getJiraProjectIssueTypesMetadata`; >3 with no clear winner (top <40%) → present top 5 + "none of these"; typo → retry once with fuzzy suggestion.

Final confirmation (single `AskUserQuestion`): show `{cloudId, project, issueType, component, status, summary}`. Options: Create / Edit field / Cancel.

**Other branch:** print the final body, offer save to `./<slug>.md`, and tell the user it's ready to paste into whatever tracker they use. No create call.

### Phase 8 — Create + transition

**GitHub:**
- `gh issue create --title "<title>" --body "<workshopped markdown>" [--label ...] [--repo owner/repo]`. The markdown body goes in verbatim.
- Return the issue URL.

**JIRA:**
- `mcp__claude_ai_Atlassian__createJiraIssue` with `cloudId` + confirmed fields. Description = workshopped markdown body verbatim.
- If a non-default initial status was requested: `getTransitionsForJiraIssue` → `transitionJiraIssue` (both take `cloudId`).
- Return ticket key + URL.

**Both:** also return a one-line summary of decisions locked during the workshop (≤3 bullets), and offer once: "Want me to save the body to `./<KEY>.md`?" Default no; only write on explicit yes.

## Error handling

**Tracker unreachable / unauthorized** (JIRA MCP down, `gh` not authed): surface the error, print the final ticket body to chat, ask the user to create it manually. Do NOT retry silently.

**User cancels at Phase 7:** print final ticket body, offer save-to-disk, exit.

**JIRA: `getVisibleJiraProjects` returns no projects:** ask the user for the project key directly and validate via `getJiraProjectIssueTypesMetadata`.

**JIRA: `cloudId` missing and `getAccessibleAtlassianResources` fails:** surface the error, print the final body, ask the user to create the ticket manually.

**GitHub: no GitHub remote or `gh` missing:** fall back to the "Other" branch — print the body and offer save-to-disk.

**Component lookup returns nothing or no clear winner:** see "Fallback" under Phase 7 JIRA branch.

## Composition with sibling skills

| Sibling | Used how |
|---|---|
| `knowledge-capture` | Phase 1 read-only digest if installed. |
| company-knowledge search skill | Optional Phase 1 call when scoping pulls in internal systems not in recon files. |
| `blueprint` | Mutually exclusive. "blueprint this" / "plan this" defers there. |
| `tech-brief` | NOT used. |

Sibling install probe: file existence at `~/.claude/skills/<name>/SKILL.md` or `~/.claude/plugins/cache/**/skills/<name>/SKILL.md`. Mention once if missing, continue.

## Anti-patterns

- **Don't pick a tracker before Phase 7.** The body is the same regardless; committing early (and preloading the wrong tooling) is the contamination this skill is built to avoid.
- **Don't assume JIRA.** There is no default tracker. Resolve it from explicit request → config → repo signal → ask.
- **Don't open `.claude-plans/` workspaces, write `handoff.md`, or `spec.v*.md`.** That's `blueprint` territory.
- **Don't write the ticket body to a file unless the user explicitly says yes.** Print to chat; the tracker is the source of truth.
- **Don't auto-create tasks via TaskCreate for the workshop itself.** Tasks are for execution work, not for chat flows.
- **Don't dump the full ticket as the first deliverable.** High-level bullets first, full draft second.
- **Don't add an auto mode.** Interactive is the methodology; auto defeats the point.
- **Don't run verification by default.** Phase 3 is conditional. If neither condition holds, skip it; don't ask "want me to verify anything?" as a default prompt.
- **Don't ask the user to paste credentials.** If the repo has no secret-store pattern, suppress the verification offer entirely.
- **Don't ship a ticket with "TBD" rows.** Either pull it out of the user or move it to "Asks for consideration".
- **Don't split one request into multiple tickets or an epic.** One ticket per invocation.
- **Don't call any Atlassian MCP tool without `cloudId`.** Every call requires it; resolve it in the Phase 7 JIRA branch.

## Inputs accepted

Parsed loosely from the user's invocation message:
- Free-text subject (required).
- Optional tracker hint ("as a GitHub issue", "make a JIRA ticket").
- Optional project key / repo override ("in project FOO", "on owner/repo").
- Optional component / label override ("component=Onboarding", "label=bug").
- Optional initial status ("in To Do", "as Backlog").

## Outputs

- Final ticket markdown body (printed in chat; the workshop already produced this).
- Ticket key / issue number + URL.
- One-line summary of decisions locked during the workshop.
- Optional saved file at `./<KEY>.md` if the user opted in at Phase 8.
