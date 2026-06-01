# visual-digest — DESIGN

Status: pinned. Authoritative design for the schema-forced screenshot/mockup analyzer. SKILL.md is the deployable surface; this file is the rigor behind it.

## Goal

Replace "looks good to me" with a typed digest. A vision-capable model is forced through a fixed schema — `meta` first, regions before elements, coverage check at the end — and writes YAML the caller can grep, diff, and gatekeep on. The schema IS the skill: the vision step does not return prose, it fills the digest.

## The failure mode this skill exists to fix

Three corrosive defaults in LLM-on-image work:

1. **Blank-canvas trust.** Model says "looks great" on a screenshot that's an empty viewport, a 401, or a JS error boundary. Vibes win because the model never asked "is there anything here?".
2. **Mockup match by hand-wave.** "This matches the mockup" when half the controls aren't rendered. Side-by-side vision passes attend to the first thing they noticed and let the rest slide.
3. **Attention drift.** Freeform descriptions grab whatever's salient (a hero image, a brand color) and skip layout, state, hierarchy. Reviewers downstream can't catch what they can't see.

The fix is structural. A fixed schema with a halt-first `meta.status` field, an explicit regions pass before any elements pass, an explicit coverage check at the end, and — in compare mode — independent digests diffed by string match. No vibes-permissive surface anywhere in the flow.

## Workflow (load-bearing)

Always four steps, always in this order. Skipping a step is misuse. Track each via TodoWrite.

### Step 1 — Blank-guard FIRST

Fill `meta.status` and `meta.blank_or_error_detected` BEFORE anything else. Inspect the image for: blank/white/black canvas, 4xx/5xx error pages, React/Vue error boundaries, "could not connect" dialogs, loading spinners with no content, single-toast error overlays on an empty body.

If any are present:

- `meta.status: halted_blank` (truly empty/all-whitespace) OR `halted_error` (error UI detected).
- `meta.status_reason: "<one sentence>"`.
- Stop. Write the digest with `meta` only — no `regions`, no `elements`, no `flows`.
- Surface to caller. `ui-validation` treats this as a verification failure and hands to `debug-loop`. `blueprint` Phase 1 treats it as "the mockup isn't loadable, ask the user for a different image".

The trap is filling in the rest of the schema "just to be thorough". Don't. The empty digest is the signal.

### Step 2 — Regions BEFORE elements

Identify ≤6 top-level layout regions. Allowed `role` enums: `navigation | content | actions | metadata | other`. Each region gets a stable slug id (`header`, `main`, `sidebar`, `footer`, `aside`, etc.) and a `bbox_pct` (see precision rules below).

The regions pass exists to force attention to layout structure before the model can grab "the first thing I noticed". A six-region cap keeps it cheap; anything beyond six is collapsed into `other`.

### Step 3 — Elements per region

For each element: stable id, kind enum, label, state enum, parent_region pointing at a region from step 2. Optional `bbox_pct` and `notes`.

Element `kind` enum: `button | input | link | image | tile | card | badge | text | icon | divider | other`.
Element `state` enum: `enabled | disabled | loading | hidden | unknown`.

Two constraints:

- Every element MUST have a `parent_region`. An element with no region is a parser error; if you can't place it, fold it into `other` or note in `open_questions`.
- `bbox_pct` is OPTIONAL. Omit it when you can't pin it confidently. Omitting is honesty; padding to "seem thorough" is the corrosive default — see anti-patterns.

### Step 4 — Coverage check

After enumeration, count elements per kind and cross-check against `expected_complexity` if provided:

| Hint | Floor |
|---|---|
| `simple` | ≥1 element |
| `form` | ≥3 inputs + ≥1 button |
| `data-grid` | ≥1 grid/table + ≥1 row + ≥1 action |
| `checkout` | ≥4 inputs (card/exp/cvv/name minimum) + ≥1 primary CTA |
| `dashboard` | ≥3 distinct widgets/cards |

Behavior on a miss:

- **Attach** an entry to `open_questions`: `"expected ≥4 inputs based on complexity 'checkout'; saw 2 — is this mid-flow?"`.
- **DO NOT** downgrade `meta.confidence`. Ratcheting confidence on every mid-flow screenshot trains callers to ignore the field entirely; that's a corrosive false-positive channel.
- When the caller supplied `flow_step` (e.g. `"1-of-3"`), scale the floor proportionally: `ceil(expected / steps)`. A first-of-three checkout step honestly shows fewer fields; the floor should follow.

If `expected_complexity` is omitted, **skip the coverage check entirely**. No floor = no false alarms.

## Compare mode

Compare mode is invoked when `image_paths` has length 2 (mockup + impl, baseline + regression, or any two-image diff).

### Independent-then-diff (load-bearing)

Run step 1-4 INDEPENDENTLY for each image. Two separate digests, no shared context, no peeking. Only after both digests exist does the skill compute `mockup_vs_impl_deltas` by diffing the typed fields.

**Never re-look at the images side-by-side.** Side-by-side vision passes are where vibes win — the model attends to whichever image is "righter" and rationalizes the other. Independent passes force the typed output to be the source of truth.

### Viewport normalization

Caller MUST declare `viewports_match: bool` when invoking compare mode. If false, OR if the two digests' viewports differ by more than 20% in either axis:

- Auto-set `comparison_mode: structural`.
- Suppress `parent_region` deltas in `mismatched.field` — responsive layouts legitimately reassign regions, that's not a mismatch.
- Suppress region-level deltas (don't flag "header in mockup, no header in impl" when one is mobile and the other desktop).
- Drop `meta.confidence` to `medium` (this is one of the few places confidence DOES move — caller asked us to compare across viewports, that's intrinsically lossy).

### `comparison_mode: structural | exact`

Caller-facing knob. Default `structural`.

- `structural`: diff existence + label. Suppress positional/regional/styling deltas. What you want for "does the impl have the same controls as the mockup".
- `exact`: diff everything in the field whitelist. Use only when viewports match AND the caller specifically wants tight comparison (e.g. design-pixel review).

### Field whitelist per element kind

Diffs are bounded per element kind to avoid noise:

| Kind | Diffed fields |
|---|---|
| `button`, `link` | `label`, `state`. Skip `parent_region` in structural mode. |
| `input` | `label`, `state`, presence. Skip `parent_region` in structural mode. |
| `image`, `icon` | presence + `kind` only. Skip `label`, `state` (icon-only buttons have unknown labels). |
| `text`, `badge` | presence + `label`. |
| `tile`, `card` | presence + child count. |
| `divider`, `other` | presence only. |

### `mockup_vs_impl_deltas` population rule

`missing`, `extra`, `mismatched` are populated by **diffing the typed outputs**, never by re-looking at images. If the diff is ambiguous (one digest has `kind: button label: "Save"`, the other has `kind: button label: "Submit"` — same conceptual element?), pick the closer match by label-edit-distance and put both ids into `mismatched`. Tie-break by region affinity.

## `meta.status` contract

`status` values:

- `ok` — digest is complete and trustworthy.
- `halted_blank` — blank/empty canvas; only `meta` populated.
- `halted_error` — error UI detected (4xx, 5xx, error boundary); only `meta` populated.
- `low_confidence` — digest filled but the model is genuinely uncertain (low-res image, ambiguous controls). `confidence` is `low`. Caller may still consume `regions`/`elements` but treat as advisory.

Callers MUST check `meta.status` before consuming any other field. An empty `elements` list does not mean "no UI elements" — it means halted, and the caller must respect that. `ui-validation` treats `halted_*` as a verification failure.

## Vision-capable invocation requirement

The skill **requires** a vision-capable Claude model with at least one image attached to the invoking message. If invoked without an attached image:

- `meta.status: halted_error`.
- `meta.status_reason: "no image attached to invocation"`.
- Stop. Surface to caller.

The skill does **NOT** dispatch a subagent to "get vision". Subagents in Claude Code can't receive images they weren't given; pretending otherwise produces silent failure where the subagent hallucinates a digest of nothing. Halt loudly instead.

High-stakes promotion to opus is a **caller-side** hint, not a skill-internal mechanism. When the image filename or path contains `auth`, `payment`, `card`, `checkout`, `pin`, `passcode`, the caller (`ui-validation`, `blueprint`) dispatches to opus before invoking visual-digest. The skill itself trusts whatever model is on the other end.

## Output paths

Mirrors the per-task screenshot subpath convention from composition-skills `decisions.md`.

| Context | Path |
|---|---|
| Workspace, single-image | `.claude-plans/<active>/visual-digests/<basename>-<mode>-<viewport>.yml` |
| Workspace, per-task (called mid-execute-plan) | `.claude-plans/<active>/visual-digests/task-<N>/<basename>-<mode>-<viewport>.yml` |
| Ad-hoc (no workspace) | `./.claude-results/<YYYY-MM-DD-HHMMSS>/visual-digest/<basename>-<mode>-<viewport>.yml` |

Slug convention: `<image-basename>-<mode>-<viewport>.yml`. Example: `dashboard-describe-1440x900.yml`, `checkout-compare-375x812.yml`.

**Pre-workspace invocation (blueprint Phase 1):** when the user attaches a mockup to a fresh `blueprint` invocation that hasn't created its workspace yet, visual-digest writes to the ad-hoc path. `blueprint`, after creating `.claude-plans/<slug>/`, MOVES the digest into `.claude-plans/<slug>/visual-digests/`. The move is blueprint's responsibility, not visual-digest's.

**Idempotent `.gitignore` append:** writing to `./.claude-results/` for the first time triggers an append of `.claude-results/` to `.gitignore` (same pattern `ui-validation` enforces).

## `bbox_pct` precision

Floats with one decimal. `[33.5, 12.0, 18.2, 4.7]` — origin top-left, percent of image dimensions.

**Omit `bbox_pct` entirely when:**

- Image dimension <200px in either axis. Add `meta.notes_on_image_quality: "small image, bbox omitted"`.
- The model can't confidently pin the boundaries (overlapping elements, transparency, ambiguous edges). Better to leave it blank than to pad.

Omission is signal. A digest with no `bbox_pct` on a 100x100 favicon is honest; a digest with `[5, 10, 90, 80]` on the same image is noise pretending to be signal.

## Field reference (compact)

Full schema in `references/digest-schema.md`. Quick reference:

```yaml
meta:
  kind: mockup | live-screenshot | regression-shot
  source_path: <absolute-path>
  viewport: { w: <int>, h: <int> }
  status: ok | halted_blank | halted_error | low_confidence
  status_reason: <string>           # required when status != ok
  confidence: high | medium | low
  blank_or_error_detected: <bool>
  notes_on_image_quality: <string>  # optional
  expected_complexity: <hint>?       # echoed from caller
  flow_step: <string>?               # echoed from caller, e.g. "1-of-3"
  comparison_mode: structural | exact   # compare mode only
  viewports_match: <bool>            # compare mode only

regions: [...]
elements: [...]
flows: [...]
hierarchy: [...]
open_questions: [...]

mockup_vs_impl_deltas:               # compare mode only
  missing: [...]
  extra: [...]
  mismatched: [...]
```

## Composition

- **Callees:** none. visual-digest is a leaf in the cycle graph (its "callee" is the vision-capable model itself).
- **Callers:** `ui-validation` (post-screenshot, describe or compare), `blueprint` (Phase 1 if a mockup is attached). Future callers welcome.
- **Cycle posture:** `caller=visual-digest` is treated as misuse — skill logs an error and no-ops. Cycle guard via the standard `caller=<skill-name>` parameter.

## Interactive vs auto mode

Default = interactive. Before running, the skill asks the user (via AskUserQuestion):

1. `expected_complexity` — hint for the coverage check (or skip).
2. `flow_step` — if this is a mid-flow screenshot.
3. `viewports_match` (compare mode only) — yes/no for normalization.
4. `comparison_mode` (compare mode only) — `structural` (default) or `exact`.

Auto mode is opt-in via: explicit user phrase ("go full auto", "no questions"), caller parameter `mode=auto`, or sibling-invocation context (`ui-validation` and `blueprint` pass through auto by default since they're already gating the user). In auto mode the skill INFERS:

- `expected_complexity` from filename keywords (`checkout`, `dashboard`, `form`, `grid`) and dims.
- `flow_step` is skipped (no inference — too easy to get wrong).
- `viewports_match` from comparing the two source images' dims (within 20% → true).
- `comparison_mode` defaults to `structural`.

Every inferred decision is logged to `.claude-plans/<active>/open-questions.md` (or `./.claude-results/<ts>/open-questions.md` ad-hoc) in the format specified by the workspace's `decisions.md` HITL entry.

## Anti-patterns

Ordered by frequency of damage.

- **Returning prose instead of filling the schema.** The schema IS the skill. A free-text description is a misuse; the caller can't grep or diff it, and the next LLM in the chain can't reason about it. Fill every required field, omit optionals honestly, but do not "describe" anything in plain English outside `notes` and `open_questions`.
- **Side-by-side compare instead of independent-then-diff.** Looking at two images together is where vibes win every time. Independent passes, then diff the typed output, period.
- **Trusting a blank canvas.** Always set `meta.blank_or_error_detected` before anything else. "I'll just describe what's there" on an empty viewport gets users to ship broken UIs.
- **Padding `bbox_pct` to seem thorough.** Low-confidence bboxes are noise pretending to be signal. Omit when uncertain; add a one-line note in `notes_on_image_quality` for tiny dims.
- **Omitting `meta.status`.** Callers read `status` first. Without it, an empty `elements` list reads as "no UI elements found, looks fine" — exactly the failure mode this skill exists to fix.
- **Ratcheting `confidence` down on every mid-flow screenshot.** Coverage misses attach an `open_question`; they do not move `confidence`. Move `confidence` only when the model is genuinely uncertain about what it's looking at.
- **Dispatching a subagent for vision when invoked without an image.** This is a footgun — subagents can't receive images they weren't given. Halt with `halted_error` instead.
- **`caller=visual-digest`.** Cycle guard. Skill logs and no-ops.
- **Re-looking at images mid-compare.** Once the typed digests exist, the comparison is a string diff. Going back to the pixels to "sanity check" reintroduces the vibes you eliminated by running them independently.
- **Hand-waving "pixel-perfect" comparisons.** Non-goal. The schema doesn't support it; promising it sets caller expectations the skill can't meet.
