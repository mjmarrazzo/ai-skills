---
name: visual-digest
description: Use this skill whenever a screenshot or mockup needs structured analysis — user attaches an image and asks "what's on this", "does this match the design", "review this mockup", or refers to "this screen", "the mock", "the design". Auto-invoked by `ui-validation` after every Playwright screenshot when a baseline or mockup is present, by `blueprint` Phase 1 when the user attaches a mockup before the discovery questionnaire, and promoted to opus by the caller for `auth`, `payment`, `card`, `checkout` images. Forces a typed YAML digest instead of "looks good" prose; halts on blank/error canvases; independent passes for compare mode. Skip only on explicit opt-out ("just describe it", "no schema", "skip visual-digest").
---

# Visual Digest

Force a typed digest on a screenshot or mockup so downstream LLMs (and this one) can reason about it without falling into "looks good" vibes. The schema is the attention-steering mechanism: vision step doesn't return prose, it fills a YAML digest the caller can grep, diff, and gatekeep on.

**This is an attention tool, not a correctness tool.** Its whole job is to force the model to look at and name every region and element instead of waving through a "looks fine" — that rubber-stamp is what ships broken UIs. It does **not** certify the read was *correct*: a fully-populated, high-confidence digest can still misread a label or miss an intent. Independent correctness checking is a separate, downstream job (a human, spec reviewers, tests) — never let a clean digest stand in for it. `confidence` reports enumeration completeness and `legibility` reports how trustworthy the read itself was; neither is a correctness guarantee.

**Announce at start:** "Using visual-digest to produce a structured digest of `<image>`."

## When to trigger

Auto-trigger when:

- User attaches an image and asks for analysis, review, or comparison.
- `ui-validation` finishes a Playwright screenshot and has a baseline or mockup on file (describe or compare mode).
- `blueprint` Phase 1 sees an attached mockup BEFORE the discovery questionnaire fires — digest first so the questions can reference identified elements.
- Two images are attached and the user wants them compared (mockup vs impl, baseline vs regression) — compare mode.
- Multiple images are attached that are variants of the SAME screen (design alternatives, A/B frames, before/after of one view) and the user wants them digested — describe mode with `variant_set: true`, which adds a cross-frame delta. Distinct from compare mode: variants have no "right answer" side, the differences between them are the point.

High-stakes paths (`auth`, `payment`, `card`, `checkout`, `pin`, `passcode` in the filename/path) get **opus promotion by the caller**. The skill itself trusts whatever model is on the other end.

Skip when: user explicitly opts out ("just describe it", "no schema", "skip visual-digest"), no image is attached, or the image is purely decorative (a logo, an icon set with no surrounding UI).

## Default mode: interactive

Before running, ask the user (one batched `AskUserQuestion`):

1. **`expected_complexity`** — `simple` / `form` / `data-grid` / `checkout` / `dashboard` / skip. Drives the coverage check.
2. **`flow_step`** — e.g. `"1-of-3"` if this is a mid-flow screenshot. Optional; scales the coverage floor.
3. **`viewports_match`** (compare mode only) — yes/no. Drives normalization.
4. **`comparison_mode`** (compare mode only) — `structural` (default, recommended) or `exact`.
5. **`variant_set`** (≥2 images, describe mode) — are these variants of the same screen (→ cross-frame delta) or unrelated images digested separately?

Auto mode opt-in:

- Explicit phrase: "go full auto", "no questions", "auto mode".
- Caller parameter: `mode=auto`.
- Sibling invocation: `ui-validation` and `blueprint` pass `mode=auto` by default (they've already gated the user; double-prompting is friction).

In auto mode, the skill infers from filename keywords + image dims and **logs every inference** to `.claude-plans/<active>/open-questions.md` (workspace) or `./.claude-results/<ts>/open-questions.md` (ad-hoc), one dated bullet per inferred decision.

## Inputs

| Param | Type | Required | Notes |
|---|---|---|---|
| `image_paths` | `[string]` | yes | 1 = describe. 2 = compare (mockup vs impl). ≥2 with `variant_set: true` = describe variant-set (per-image digests + cross-frame delta). |
| `mode` | `"describe" \| "compare"` | inferred | from `image_paths` cardinality; `variant_set` keeps multi-image input in describe mode instead of compare |
| `variant_set` | bool | optional | describe-mode only. The N images are variants of one screen → run a cross-frame delta. Default `false` (each image digested independently, no delta). |
| `expected_complexity` | enum | optional | coverage-check hint; omitted = skip check |
| `flow_step` | string | optional | e.g. `"1-of-3"`, scales coverage floor |
| `viewports_match` | bool | compare only | normalization gate |
| `comparison_mode` | `"structural" \| "exact"` | compare only | default `structural` |
| `caller` | string | optional | cycle-guard param; sibling skills pass their name. Defaults to `chat` when user-invoked. `caller=visual-digest` is misuse, skill logs and no-ops. |

## Workflow (load-bearing — track via TodoWrite)

Four digest steps, always in this order, then validate. Full mechanics in `references/workflow.md`.

1. **Blank-guard FIRST.** Fill `meta.status` and `meta.blank_or_error_detected` BEFORE anything else, then set `meta.legibility` (how readable the image is — separate from enumeration `confidence`). If blank/error: write a stub with `meta` only, halt, surface to caller. No "looks fine" on a blank canvas, ever.
2. **Regions before elements.** Enumerate ≤6 top-level layout regions with `role` enum and `bbox_pct`.
3. **Elements per region.** Each element gets stable id, kind, label, state, parent_region. `bbox_pct` is optional and **default-omitted in describe mode / on mockups / on non-full-res images** — eyeballed coordinates are theater.
4. **Coverage check.** Cross-check element count against `expected_complexity` floor (if provided). Miss attaches an `open_question`; **does NOT downgrade `confidence`**. `flow_step` scales the floor.
5. **Validate.** Run `python3 scripts/validate-digest.py <digest.yml>` on every digest written (each per-image digest and any compare digest). Fix violations and re-run until it exits 0; only then report to the caller.

Compare mode (2 images, mockup vs impl) runs steps 1-4 INDEPENDENTLY for each image, then diffs the typed outputs into `mockup_vs_impl_deltas`. Describe variant-set mode (`variant_set: true`) runs steps 1-4 INDEPENDENTLY for every frame, then diffs each sibling against a baseline frame into `cross_frame_deltas` (Step 5 in `references/workflow.md`). **Never re-look at the images side-by-side** in either case. Mechanics in `references/comparison.md` and `references/workflow.md`.

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
meta: { kind, source_path, viewport, status, confidence, legibility, blank_or_error_detected, ... }
regions: [{ id, bbox_pct, role, contents }]
elements: [{ id, kind, label, state, parent_region, bbox_pct?, notes? }]
flows: [{ description, confidence }]
hierarchy: [...]
open_questions: [...]
mockup_vs_impl_deltas:   # compare mode only
  missing: [...]
  extra: [...]
  mismatched: [...]
cross_frame_deltas:      # describe variant-set only (variant_set: true)
  baseline_frame: <basename>
  per_frame: [...]
```

## Vision-capable invocation requirement

The skill **requires** a vision-capable Claude model with at least one image attached to the current message. If no image is attached: `meta.status: halted_error`, `status_reason: "no image attached to invocation"`, stop. The skill **does NOT** dispatch a subagent to "get vision" — subagents can't receive images they weren't given. Halt loudly instead.

## Active workspace resolution

**Active-workspace resolution** (canonical, shared across all sibling skills):
1. If the caller passes `WORKSPACE_PATH` (explicit absolute path), use it — no discovery.
2. Otherwise enumerate `.claude-plans/*/` in the repo root (or cwd if not in a git repo).
3. Filter to directories containing `plan.v*.md` or `spec.v*.md` (blueprint writes only versioned artifacts, never bare `plan.md`/`spec.md`). When a skill needs "the plan" or "the spec", use the highest-N version.
4. Exactly one match → use it.
5. Multiple → prefer the one whose slug contains the current branch's ticket key (branch `MSP-7032/foo` → workspace with `MSP-7032` in slug).
6. Still multiple → most recent by mtime of the newest `plan.v*.md` (fall back to dir mtime).
7. Zero → ad-hoc mode, no workspace. Ad-hoc artifacts go under `./.claude-results/<YYYY-MM-DD-HHMMSS>/<skill-name>/` (gitignored).

## Composition

| | |
|---|---|
| **Callees** | none — visual-digest is a leaf. The "callee" is the vision-capable model itself. |
| **Callers** | `ui-validation` (post-Playwright, describe or compare), `blueprint` (Phase 1 if mockup attached) |
| **Cycle posture** | `caller` defaults to `chat` when user-invoked; `caller=visual-digest` is misuse — skill logs and no-ops |
| **Reads** | the image(s) |
| **Writes** | YAML digest at the path above; idempotent `.gitignore` append for `.claude-results/`; `open-questions.md` entries in auto mode |
| **Validates** | every written digest via `scripts/validate-digest.py` before reporting |

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
confidence: high      # enumeration completeness
legibility: high      # observation reliability
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

Canonical list — `references/workflow.md` and `references/comparison.md` add only mode-specific ones.

- **Returning prose instead of filling the schema** — the schema IS the skill; fill every required field, omit optionals honestly.
- **Trusting a blank canvas** — set `meta.blank_or_error_detected` and `meta.status` FIRST, before describing anything.
- **Side-by-side compare instead of independent-then-diff** — independent passes, then diff the typed output.
- **Padding `bbox_pct` to seem thorough** — default-omit in describe mode / on mockups / non-full-res images; reserve bbox for full-res live screenshots and `exact` compare.
- **Omitting `meta.status`** — without it an empty `elements` list reads as "looks fine", the exact failure mode this skill exists to fix.
- **Ratcheting `confidence` down on every mid-flow screenshot** — coverage misses attach an `open_question`, they do not move `confidence`.
- **Dispatching a subagent for vision when invoked without an image** — subagents can't receive images they weren't given; halt with `halted_error`.
- **`caller=visual-digest`** — cycle guard; log an error and no-op.
- **Promising pixel-perfect comparison** — non-goal; the schema doesn't support it.
- **Treating a complete digest as a correctness pass** — a clean digest proves the model looked, not that it read right; correctness review is separate and downstream.
- **`confidence: high` on a barely-legible image** — fuzzy text means `legibility: low`; don't collapse the two axes.
- **Delta-only digesting variant-set siblings** — every frame gets a full independent digest; `cross_frame_deltas` is computed from those, never a skim.
- **Skipping the validator** — an unvalidated digest can carry dangling `parent_region`/`contents` refs downstream; run `scripts/validate-digest.py` before reporting.

## Open questions

- Programmatic cross-digest comparison in any future skill (two digests across sessions). Deferred — v1 hands the YAML to the caller LLM to diff; `scripts/validate-digest.py` covers schema invariants only, not diffing.
- Whether to support a third mode (`baseline` — write the first digest, freeze it, diff every subsequent run against it). Deferred to dogfooding.
