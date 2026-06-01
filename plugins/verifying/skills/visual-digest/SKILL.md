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

In auto mode, the skill infers from filename keywords + image dims and **logs every inference** to `.claude-plans/<active>/open-questions.md` (workspace) or `./.claude-results/<ts>/open-questions.md` (ad-hoc). Format pinned in this workspace's `decisions.md` HITL entry.

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
| `caller` | string | required | cycle-guard param. `caller=visual-digest` is misuse, skill logs and no-ops. |

## Workflow (load-bearing — track via TodoWrite)

Four steps, always in this order. Full mechanics in `references/workflow.md`.

1. **Blank-guard FIRST.** Fill `meta.status` and `meta.blank_or_error_detected` BEFORE anything else, then set `meta.legibility` (how readable the image is — separate from enumeration `confidence`). If blank/error: write a stub with `meta` only, halt, surface to caller. No "looks fine" on a blank canvas, ever.
2. **Regions before elements.** Enumerate ≤6 top-level layout regions with `role` enum and `bbox_pct`.
3. **Elements per region.** Each element gets stable id, kind, label, state, parent_region. `bbox_pct` is optional and **default-omitted in describe mode / on mockups / on non-full-res images** — eyeballed coordinates are theater.
4. **Coverage check.** Cross-check element count against `expected_complexity` floor (if provided). Miss attaches an `open_question`; **does NOT downgrade `confidence`**. `flow_step` scales the floor.

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

- **Returning prose instead of filling the schema.** The schema IS the skill. A free-text description is a misuse; the caller can't grep or diff it. Fill every required field, omit optionals honestly.
- **Trusting a blank canvas.** Always set `meta.blank_or_error_detected` and `meta.status` FIRST. "I'll just describe what's there" on an empty viewport ships broken UIs.
- **Side-by-side compare instead of independent-then-diff.** Looking at two images together is where vibes win every time. Independent passes, then diff the typed output.
- **Padding `bbox_pct` to seem thorough — especially in describe mode.** Low-confidence bboxes are noise pretending to be signal, and coordinates eyeballed off a downscaled mockup are pure theater. Default-omit in describe mode; reserve bbox for full-res live screenshots and `exact` compare. Add a one-line `notes_on_image_quality` for tiny dims (<200px).
- **Omitting `meta.status`.** Callers check `status` first. Without it, an empty `elements` list reads as "looks fine" — exactly the failure mode this skill exists to fix.
- **Ratcheting `confidence` down on every mid-flow screenshot.** Coverage misses attach an `open_question`; they do not move `confidence`.
- **Dispatching a subagent for vision when invoked without an image.** Footgun — subagents can't receive images they weren't given. Halt with `halted_error` instead.
- **`caller=visual-digest`.** Cycle guard. Skill logs an error and no-ops.
- **Promising pixel-perfect comparison.** Non-goal. The schema doesn't support it; setting caller expectations the skill can't meet erodes trust.
- **Treating a complete digest as a correctness pass.** A full, high-`confidence` digest proves the model *looked* at every region — not that it read them right. Don't let "the digest is clean" substitute for independent correctness review (human, spec reviewers, tests).
- **`confidence: high` on a barely-legible image.** Confidence is enumeration completeness; legibility is read reliability. If the text is fuzzy, set `legibility: low` and keep `confidence` honest about what you could enumerate — don't collapse the two.
- **Delta-only digesting variant-set siblings.** In a `variant_set`, every frame gets a full independent digest; `cross_frame_deltas` is computed from those. Skimming siblings against the baseline to save tokens reintroduces the rubber-stamp.

## Open questions

- Programmatic YAML parsing in any future skill that compares two digests across sessions. Deferred — v1 hands the YAML to the caller LLM to diff.
- Whether to support a third mode (`baseline` — write the first digest, freeze it, diff every subsequent run against it). Deferred to dogfooding.
