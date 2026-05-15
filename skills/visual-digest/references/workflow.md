# workflow — the 4-step process

The mechanics behind `visual-digest`'s load-bearing rule: the schema steers attention through these four steps, always in this order. Each step has a `TodoWrite` entry; the digest is invalid if a step is skipped or reordered.

---

## Step 1 — Blank-guard FIRST

Fill `meta.status` and `meta.blank_or_error_detected` BEFORE looking at anything else. This is the single most violated rule in vision work — the model "describes what's there" on an empty canvas because describing feels productive. Don't.

**Detect:**

- Solid-color viewport (white, black, brand color) covering >95% of the image.
- 4xx/5xx error pages — common signals: `404`, `Not Found`, `Internal Server Error`, `502 Bad Gateway`, browser error chrome.
- Error boundaries — React's "Something went wrong", Vue's error overlay, Next.js dev error stack.
- "Cannot connect", "Network error", "Please refresh" dialogs covering main content.
- Loading spinner with no content rendered behind it.
- Authentication redirects — "Sign in to continue", login form when expecting a dashboard.

**Decide `status`:**

| Condition | `status` | `blank_or_error_detected` |
|---|---|---|
| Empty viewport, no content | `halted_blank` | `true` |
| Error UI present | `halted_error` | `true` |
| Content present, model uncertain | `low_confidence` | `false` |
| Content present, model confident | `ok` | `false` |

**On `halted_*`:**

- Set `meta.status` and `meta.status_reason` (one sentence).
- Write digest with `meta` ONLY. Omit `regions`, `elements`, `flows`, `hierarchy`, `mockup_vs_impl_deltas`.
- Stop. Surface to caller.

The empty digest IS the signal. Don't fill in regions to "be thorough"; that re-introduces the failure mode this skill exists to fix.

---

## Step 2 — Regions BEFORE elements

Enumerate ≤6 top-level layout regions FIRST, before naming any individual control.

**Why this order:** without a regions pass, the model grabs whatever's salient (the hero image, the brand color, the call-to-action) and lists controls in whatever order they catch the eye. The regions pass forces structural attention.

**Each region:**

- Stable `id`: lowercase-kebab slug (`header`, `main`, `sidebar`, `aside`, `footer`, `modal`, `toast-region`, etc.).
- `bbox_pct`: `[x, y, w, h]` floats with one decimal, percent of image dimensions, origin top-left.
- `role`: `navigation` | `content` | `actions` | `metadata` | `other`.
- `contents`: list of element ids that live in this region (filled in step 3).

**The ≤6 cap is a feature.** Anything beyond six top-level regions usually means the model didn't group, it just listed everything. Collapse small adjacent regions into `other` rather than ratchet up the count.

---

## Step 3 — Elements per region

For each region from step 2, enumerate the elements inside it. Each element gets:

- Stable `id`: lowercase-kebab slug, unique within the digest (`save-button`, `nav-primary`, `tile-revenue`).
- `kind`: enum from `button | input | link | image | tile | card | badge | text | icon | divider | other`.
- `label`: user-visible text. Empty string for label-less elements (icons, dividers). Don't invent labels.
- `state`: `enabled | disabled | loading | hidden | unknown`. Use `unknown` honestly when state isn't legible.
- `parent_region`: id of the region from step 2 that contains this element. **Required.** Every element MUST have a parent.
- `bbox_pct`: **OPTIONAL.** Omit when uncertain, when image dim <200px (then add `notes_on_image_quality`), or when the element overlaps so much with neighbors that boundaries aren't crisp.
- `notes`: optional one-liner. Used for intentionality hints ("primary CTA, looks intentional") or layout cues ("appears off-grid, possibly intentional").

**Element ordering rule:** within a region, walk top-to-bottom, then left-to-right. Predictable order makes diffs cheaper for compare mode.

---

## Step 4 — Coverage check

After enumeration, count elements and cross-check against `expected_complexity` if provided.

**Floors (when `expected_complexity` is set):**

| Hint | Floor |
|---|---|
| `simple` | ≥1 element total |
| `form` | ≥3 `kind: input` + ≥1 `kind: button` |
| `data-grid` | ≥1 grid/table + ≥1 row + ≥1 action button |
| `checkout` | ≥4 `kind: input` (card/exp/cvv/name minimum) + ≥1 primary CTA |
| `dashboard` | ≥3 distinct widgets (`tile`, `card`, or chart `image`) |

**When `flow_step` is provided** (e.g. `"1-of-3"`), scale the floor proportionally: `ceil(floor / steps)`. A first-of-three checkout step honestly shows fewer fields; the coverage check should respect that.

**On a miss:**

- Attach a string to `open_questions`: `"expected ≥4 inputs based on complexity 'checkout'; saw 2 — is this mid-flow?"`.
- **DO NOT** downgrade `meta.confidence`. The whole point of the floor is to surface a question; ratcheting confidence trains callers to ignore the field.

**When `expected_complexity` is omitted:** skip the check entirely. No floor = no false alarms. Don't invent a floor from filename hints — the caller is responsible for passing the hint if they want the check.

---

## Anti-patterns specific to the workflow

- **Returning prose instead of filling the schema.** The most damaging misuse. A free-text description ("This screenshot shows a checkout page with a payment form and an order summary on the right") is exactly what the skill exists to prevent. Fill every required schema field; the schema IS the digest.
- **Side-by-side compare instead of independent-then-diff.** Compare mode runs steps 1-4 INDEPENDENTLY for each image. Looking at both images at once is where vibes win. See `comparison.md` for the mechanics.
- **Trusting a blank canvas.** Step 1 is non-negotiable. A halt is a useful signal, not a failure of the skill.
- **Ratcheting `confidence` down on every mid-flow screenshot.** Coverage misses attach an `open_question`; they don't move `confidence`. False positives in a "this might be wrong" channel are corrosive — users learn to ignore the field.
- **Skipping the regions pass and going straight to elements.** Without regions-first, the elements list reflects salience, not structure. Diffs against future digests become noise.
- **Filling `bbox_pct` with low-confidence guesses.** Omit when uncertain. Padding to seem thorough is exactly the failure mode the schema is designed to prevent.
- **Listing every element with `bbox_pct` of the same value** (e.g. `[0.0, 0.0, 100.0, 100.0]`). Sign that the model gave up and copied a placeholder; reviewers will catch it.
- **Inventing `flow_step` when the caller didn't provide it.** Step counting requires context the model doesn't have. If the caller didn't pass it, the coverage check uses the full floor.
