---
name: visual-digest
description: Use this skill whenever a screenshot or mockup needs structured analysis — user attaches an image and asks "what's on this", "does this match the design", "review this mockup", or refers to "this screen", "the mock", "the design". Auto-invoked by `ui-validation` after every Playwright screenshot when a baseline or mockup is present, by `blueprint` Phase 1 when the user attaches a mockup before the discovery questionnaire, and promoted to opus by the caller for `auth`, `payment`, `card`, `checkout` images. Forces a typed YAML digest instead of "looks good" prose; halts on blank/error canvases; independent passes for compare mode. Skip only on explicit opt-out ("just describe it", "no schema", "skip visual-digest").
---

# Visual Digest

Force a typed digest on a screenshot or mockup so downstream LLMs (and this one) can reason about it without falling into "looks good" vibes. The schema is the attention-steering mechanism: vision step doesn't return prose, it fills a YAML digest the caller can grep, diff, and gatekeep on.

**Announce at start:** "Using visual-digest to produce a structured digest of `<image>`."

## When to trigger

Auto-trigger when:

- User attaches an image and asks for analysis, review, or comparison.
- `ui-validation` finishes a Playwright screenshot and has a baseline or mockup on file (describe or compare mode).
- `blueprint` Phase 1 sees an attached mockup BEFORE the discovery questionnaire fires — digest first so the questions can reference identified elements.
- Two images are attached and the user wants them compared (mockup vs impl, baseline vs regression).

High-stakes paths (`auth`, `payment`, `card`, `checkout`, `pin`, `passcode` in the filename/path) get **opus promotion by the caller**. The skill itself trusts whatever model is on the other end.

Skip when: user explicitly opts out ("just describe it", "no schema", "skip visual-digest"), no image is attached, or the image is purely decorative (a logo, an icon set with no surrounding UI).

## Default mode: interactive

Before running, ask the user (one batched `AskUserQuestion`):

1. **`expected_complexity`** — `simple` / `form` / `data-grid` / `checkout` / `dashboard` / skip. Drives the coverage check.
2. **`flow_step`** — e.g. `"1-of-3"` if this is a mid-flow screenshot. Optional; scales the coverage floor.
3. **`viewports_match`** (compare mode only) — yes/no. Drives normalization.
4. **`comparison_mode`** (compare mode only) — `structural` (default, recommended) or `exact`.

Auto mode opt-in:

- Explicit phrase: "go full auto", "no questions", "auto mode".
- Caller parameter: `mode=auto`.
- Sibling invocation: `ui-validation` and `blueprint` pass `mode=auto` by default (they've already gated the user; double-prompting is friction).

In auto mode, the skill infers from filename keywords + image dims and **logs every inference** to `.claude-plans/<active>/open-questions.md` (workspace) or `./.claude-results/<ts>/open-questions.md` (ad-hoc). Format pinned in this workspace's `decisions.md` HITL entry.

## Inputs

| Param | Type | Required | Notes |
|---|---|---|---|
| `image_paths` | `[string]` | yes | 1 path = describe mode, 2 paths = compare mode |
| `mode` | `"describe" \| "compare"` | inferred | from `image_paths` cardinality |
| `expected_complexity` | enum | optional | coverage-check hint; omitted = skip check |
| `flow_step` | string | optional | e.g. `"1-of-3"`, scales coverage floor |
| `viewports_match` | bool | compare only | normalization gate |
| `comparison_mode` | `"structural" \| "exact"` | compare only | default `structural` |
| `caller` | string | required | cycle-guard param. `caller=visual-digest` is misuse, skill logs and no-ops. |

## Workflow (load-bearing — track via TodoWrite)

Four steps, always in this order. Full mechanics in `references/workflow.md`.

1. **Blank-guard FIRST.** Fill `meta.status` and `meta.blank_or_error_detected` BEFORE anything else. If blank/error: write a stub with `meta` only, halt, surface to caller. No "looks fine" on a blank canvas, ever.
2. **Regions before elements.** Enumerate ≤6 top-level layout regions with `role` enum and `bbox_pct`.
3. **Elements per region.** Each element gets stable id, kind, label, state, parent_region. `bbox_pct` optional (omit when uncertain).
4. **Coverage check.** Cross-check element count against `expected_complexity` floor (if provided). Miss attaches an `open_question`; **does NOT downgrade `confidence`**. `flow_step` scales the floor.

Compare mode runs steps 1-4 INDEPENDENTLY for each image, then diffs the typed outputs. **Never re-look at the images side-by-side.** Mechanics in `references/comparison.md`.

## Output

YAML digest written to:

| Context | Path |
|---|---|
| Workspace, single-image | `.claude-plans/<active>/visual-digests/<basename>-<mode>-<viewport>.yml` |
| Workspace, per-task (mid-execute-plan) | `.claude-plans/<active>/visual-digests/task-<N>/<basename>-<mode>-<viewport>.yml` |
| Ad-hoc (no workspace) | `./.claude-results/<YYYY-MM-DD-HHMMSS>/visual-digest/<basename>-<mode>-<viewport>.yml` |
| Blueprint pre-workspace | ad-hoc path; blueprint moves into `.claude-plans/<slug>/visual-digests/` after workspace creation |

Slug example: `dashboard-describe-1440x900.yml`, `checkout-compare-375x812.yml`. First write to `./.claude-results/` triggers idempotent `.gitignore` append.

Full schema pinned in `references/digest-schema.md`. Quick shape:

```yaml
meta: { kind, source_path, viewport, status, confidence, blank_or_error_detected, ... }
regions: [{ id, bbox_pct, role, contents }]
elements: [{ id, kind, label, state, parent_region, bbox_pct?, notes? }]
flows: [{ description, confidence }]
hierarchy: [...]
open_questions: [...]
mockup_vs_impl_deltas:   # compare mode only
  missing: [...]
  extra: [...]
  mismatched: [...]
```

## Vision-capable invocation requirement

The skill **requires** a vision-capable Claude model with at least one image attached to the current message. If no image is attached: `meta.status: halted_error`, `status_reason: "no image attached to invocation"`, stop. The skill **does NOT** dispatch a subagent to "get vision" — subagents can't receive images they weren't given. Halt loudly instead.

## Active workspace resolution

Use the canonical algorithm pinned in `.claude-plans/2026-05-14-composition-skills/decisions.md`. In brief: `WORKSPACE_PATH` env first; enumerate `.claude-plans/*/` dirs with `plan.md` or `spec.md`; prefer the one matching the current branch's ticket key; fall back to most-recent by mtime; otherwise ad-hoc mode.

## Composition

| | |
|---|---|
| **Callees** | none — visual-digest is a leaf. The "callee" is the vision-capable model itself. |
| **Callers** | `ui-validation` (post-Playwright, describe or compare), `blueprint` (Phase 1 if mockup attached) |
| **Cycle posture** | `caller=visual-digest` is misuse — skill logs and no-ops |
| **Reads** | the image(s); workspace's `decisions.md` for the active-workspace algorithm |
| **Writes** | YAML digest at the path above; idempotent `.gitignore` append for `.claude-results/`; `open-questions.md` entries in auto mode |

If a referenced sibling skill is not installed, mention it once and degrade gracefully — don't fail the workflow.

## Reporting

After writing the digest, report to the caller:

```
visual-digest — dashboard.png
─────────────────────────────────────
status: ok
mode: describe
viewport: 1440x900
elements: 23 (6 buttons, 4 inputs, 8 text, 3 image, 2 badge)
regions: 4 (header, main, sidebar, footer)
confidence: high
open questions: 1
digest: .claude-plans/<active>/visual-digests/dashboard-describe-1440x900.yml
```

For `halted_*`:

```
visual-digest — checkout.png
─────────────────────────────────────
status: halted_error
reason: "401 Unauthorized rendered in main viewport"
digest: .claude-plans/<active>/visual-digests/checkout-describe-1440x900.yml
→ handing back to caller for next-step decision
```

## Anti-patterns

- **Returning prose instead of filling the schema.** The schema IS the skill. A free-text description is a misuse; the caller can't grep or diff it. Fill every required field, omit optionals honestly.
- **Trusting a blank canvas.** Always set `meta.blank_or_error_detected` and `meta.status` FIRST. "I'll just describe what's there" on an empty viewport ships broken UIs.
- **Side-by-side compare instead of independent-then-diff.** Looking at two images together is where vibes win every time. Independent passes, then diff the typed output.
- **Padding `bbox_pct` to seem thorough.** Low-confidence bboxes are noise pretending to be signal. Omit when uncertain; add a one-line `notes_on_image_quality` for tiny dims (<200px).
- **Omitting `meta.status`.** Callers check `status` first. Without it, an empty `elements` list reads as "looks fine" — exactly the failure mode this skill exists to fix.
- **Ratcheting `confidence` down on every mid-flow screenshot.** Coverage misses attach an `open_question`; they do not move `confidence`.
- **Dispatching a subagent for vision when invoked without an image.** Footgun — subagents can't receive images they weren't given. Halt with `halted_error` instead.
- **`caller=visual-digest`.** Cycle guard. Skill logs an error and no-ops.
- **Promising pixel-perfect comparison.** Non-goal. The schema doesn't support it; setting caller expectations the skill can't meet erodes trust.

## Open questions

- Programmatic YAML parsing in any future skill that compares two digests across sessions. Deferred — v1 hands the YAML to the caller LLM to diff.
- Whether to support a third mode (`baseline` — write the first digest, freeze it, diff every subsequent run against it). Deferred to dogfooding.
