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

**Then set `legibility` (v2) — a separate axis from `confidence`.** Before enumerating anything, judge how *readable* the image actually is: full-resolution and crisp → `high`; downscaled, compressed, or small but the structure is still clear → `medium`; blurry, tiny, or heavily occluded such that labels/states are guesses → `low`. This is observation reliability, and it is independent of how completely you later enumerate (`confidence`). A downscaled mockup whose every region you can name but whose label text you're half-guessing is `confidence: high, legibility: low` — that is the honest digest, not a contradiction. If you write a `notes_on_image_quality` about readability, `legibility` must not be `high`.

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
- `bbox_pct`: **OPTIONAL, and default-omit in describe mode.** Always omit for mockups and any downscaled / non-full-resolution image: coordinates eyeballed off a shrunken mock are directionally-ok theater — useless for pixel work and a tax on attention. Populate bbox only for full-resolution live screenshots, or `exact` compare mode where a human will act on the pixels. Also omit when uncertain, when image dim <200px (then add `notes_on_image_quality`), or when neighbors overlap so much that boundaries aren't crisp.
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

## Step 5 — Cross-frame delta (describe-mode variant sets only)

Runs only when `mode == describe` and the caller passed `variant_set: true` (≥2 images that are variants of the *same* screen). Skip entirely otherwise.

The field-tested payoff of this skill showed up here: forcing a full `elements` enumeration on two near-identical grid frames surfaced that one had a body paragraph the other didn't — which drove a correct architectural inference. The delta only appeared because both frames were enumerated in full, not skimmed.

**Mechanics — same independent-then-diff discipline as compare mode:**

1. Pick the **baseline frame**: the most complete / canonical variant. Record it as `cross_frame_deltas.baseline_frame`.
2. Run Steps 1–4 **fully and independently on every frame**, including the siblings. Do NOT shortcut siblings to a "delta-only" glance against the baseline — that re-opens the exact rubber-stamp failure ("looks like the baseline, moving on") this skill exists to close. Each frame gets its own full digest on disk.
3. **String-diff** each sibling's typed digest against the baseline's (match by `id` then `(kind, label)`, diff the per-kind whitelist). Never re-look at the images side-by-side to compare.
4. Write the consolidated result to `cross_frame_deltas`. This block — not the N full digests — is what the caller/human reads to see what differs.

**On the scope tradeoff:** yes, this means N full digests for N frames rather than "one full plus delta-only siblings." That cost is deliberate. Full enumeration of each frame is the forcing function; the consolidation a reviewer wants lives in `cross_frame_deltas`, not in enumerating less. Cheaper enumeration would have missed the body-paragraph delta.

---

## Anti-patterns specific to the workflow

- **Returning prose instead of filling the schema.** The most damaging misuse. A free-text description ("This screenshot shows a checkout page with a payment form and an order summary on the right") is exactly what the skill exists to prevent. Fill every required schema field; the schema IS the digest.
- **Side-by-side compare instead of independent-then-diff.** Compare mode runs steps 1-4 INDEPENDENTLY for each image. Looking at both images at once is where vibes win. See `comparison.md` for the mechanics.
- **Trusting a blank canvas.** Step 1 is non-negotiable. A halt is a useful signal, not a failure of the skill.
- **Ratcheting `confidence` down on every mid-flow screenshot.** Coverage misses attach an `open_question`; they don't move `confidence`. False positives in a "this might be wrong" channel are corrosive — users learn to ignore the field.
- **Skipping the regions pass and going straight to elements.** Without regions-first, the elements list reflects salience, not structure. Diffs against future digests become noise.
- **Filling `bbox_pct` with low-confidence guesses.** Omit when uncertain. Padding to seem thorough is exactly the failure mode the schema is designed to prevent.
- **Filling `bbox_pct` at all in describe mode / on a mockup.** Coordinates eyeballed off a downscaled mock are theater — directionally ok, useless for pixel work, and a tax on attention. Default-omit; bbox is for full-res live screenshots and `exact` compare only.
- **Listing every element with `bbox_pct` of the same value** (e.g. `[0.0, 0.0, 100.0, 100.0]`). Sign that the model gave up and copied a placeholder; reviewers will catch it.
- **Inventing `flow_step` when the caller didn't provide it.** Step counting requires context the model doesn't have. If the caller didn't pass it, the coverage check uses the full floor.
- **Delta-only digesting the siblings in a variant set.** Tempting for token savings; fatal to the mechanism. Each frame gets a full independent digest — the cross-frame delta is computed from those, not from a skim.
- **Treating a complete digest as a correctness check.** The digest proves you *looked* at every region; it does not prove you read them right. Correctness is a separate, downstream verification.
