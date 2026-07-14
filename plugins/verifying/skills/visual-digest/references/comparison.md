# comparison — compare mode mechanics

When `image_paths` has length 2, `visual-digest` runs in compare mode. The output adds a `mockup_vs_impl_deltas` block computed by diffing the two digests' typed fields. Compare mode exists for: mockup vs implementation, baseline vs regression, and any two-image structural diff.

The load-bearing rule: **independent passes, diff the typed output. Never re-look at the images side-by-side.**

---

## Why independent-then-diff

The corrosive default in two-image vision work is to look at both images at the same time and "compare". This is where vibes win every time:

- The model attends to whichever image is "righter" and rationalizes the other.
- Salient differences (hero image, color shift) crowd out structural ones (a missing input).
- The output is unauditable — you can't grep for what was compared.

Independent passes break this — with an honest caveat about what "independent" means here:

1. Run the full 4-step workflow on image A. Output: digest A (`<basename-a>-describe-<viewport>.yml`).
2. Run the full 4-step workflow on image B **without re-opening image A** and without consulting digest A while enumerating. Output: digest B.
3. Diff the two YAML documents by id, kind, and the field whitelist. Output: `mockup_vs_impl_deltas`.

These are *sequential* independent passes within one context, not true isolation: the model that digests B has already seen A earlier in the conversation, so some residual context contamination is unavoidable. The discipline that remains enforceable — and load-bearing — is that image A is never re-opened while digesting B, and the typed digests are the **only** inputs to the comparison.

Step 3 is a **string comparison**, not a vision pass. The model does not look at the pixels again. If the diff is ambiguous, the resolution rule is below.

---

## Viewport normalization

The caller MUST declare `viewports_match: bool` when invoking compare mode. If false — OR if the two digests' viewports differ by more than 20% in either axis — the skill normalizes:

- **Auto-set `comparison_mode: structural`.** Even if the caller asked for `exact`. Exact comparison across different viewports is incoherent.
- **Suppress region-level deltas.** Don't flag "header in mockup, no header in impl" when one is mobile and the other desktop; that's expected responsive behavior, not a regression.
- **Suppress `parent_region` in `mismatched.field`.** Responsive layouts legitimately reassign regions (a sidebar nav becomes a hamburger menu's contents on mobile). Flagging it as a mismatch is noise.
- **Drop `meta.legibility` to `medium`** (v2; this was `meta.confidence` before the split). Reading element correspondences across mismatched viewports is intrinsically lossy — that's an observation-reliability statement, so it lands on `legibility`. `confidence` (enumeration completeness) is unaffected and stays as enumerated.

The 20% auto-detection is a fallback. Callers should still pass `viewports_match` honestly; the auto-detect catches misuse.

---

## `comparison_mode: structural | exact`

Caller-facing knob. Default: `structural`.

### `structural` (default)

Diff existence + label. Suppress positional/regional/styling deltas. What callers want for "does the impl have the same controls as the mockup".

- Region-level deltas: presence + role only. Position differences suppressed.
- Element-level deltas: presence + per-kind field whitelist (see below).
- `parent_region` differences suppressed.
- Bbox differences suppressed entirely (bbox is for human review, not diff).

### `exact`

Diff everything in the field whitelist. Use only when `viewports_match: true` AND the caller specifically wants tight comparison (e.g. design-pixel review).

- Region-level deltas: presence + role + position (≥5% bbox shift flagged).
- Element-level deltas: full whitelist diff including `parent_region` and label.
- Bbox differences flagged when >5% shift on any dimension.

If `viewports_match: false`, `exact` is silently downgraded to `structural`. The skill notes the downgrade in `meta.notes_on_image_quality`.

---

## Field whitelist per element kind

Different element kinds have different signal-to-noise ratios in compare mode. The whitelist bounds what gets diffed.

| Kind | Diffed fields | Rationale |
|---|---|---|
| `button`, `link` | `label`, `state` | Position/region varies by viewport; label and state are the contract. |
| `input` | `label`, `state`, presence | Same — what fields exist and whether they're disabled matters; layout doesn't. |
| `image`, `icon` | presence + `kind` only | Icon-only buttons have unknown labels; comparing labels is noise. Theme differences are not a regression. |
| `text`, `badge` | presence + `label` | Copy changes matter; position doesn't. |
| `tile`, `card` | presence + child count | Tile labels often include live data ("Revenue $128k"); compare structure, not values. |
| `divider`, `other` | presence only | Layout primitives; presence is the signal. |

`parent_region` is added to the whitelist only in `exact` mode AND when `viewports_match: true`. Always suppressed otherwise.

---

## `mockup_vs_impl_deltas` population rule

After both digests exist, walk them:

### `missing` — in A (mockup), not in B (impl)

For each element in digest A: search digest B for a match by `id` first, then by `(kind, label)` exact match. If neither hits, append to `missing` with the element's `kind`, `label`, `parent_region`.

### `extra` — in B (impl), not in A (mockup)

Symmetric. For each element in digest B not found in A, append to `extra`.

### `mismatched` — same conceptual element, different details

For each element in A matched in B (by id or by `(kind, label)`):

- For each field in the whitelist for that kind: compare values. If different, append a `mismatched` entry with `mockup_id`, `impl_id`, `field`, `mockup_value`, `impl_value`.
- Skip fields that are uniformly suppressed by the current `comparison_mode`.

### Ambiguous matches

If digest A has `kind: button label: "Save"` and digest B has `kind: button label: "Submit"` — same element conceptually, or extra/missing pair?

**Resolution rule:** pick the closer match by label edit distance. If two candidates in B tie, tie-break by region affinity (same `parent_region` wins). If still tied, treat as `extra` + `missing` (a "rename" gets flagged as both, which is informative — reviewers can read it as "renamed: Save → Submit").

**Never re-look at the images to resolve.** The whole point of independent-then-diff is that the typed output is the source of truth.

---

## Compare-mode output structure

Compare mode produces three files:

```
.claude-plans/<active>/visual-digests/
├── checkout-mockup-describe-1440x900.yml      # digest A, fully populated
├── checkout-impl-describe-1440x900.yml        # digest B, fully populated
└── checkout-compare-1440x900.yml              # the comparison digest with deltas
```

The comparison digest's `regions`, `elements`, `flows`, `hierarchy` are duplicated from the IMPL side (the "current" reality). `mockup_vs_impl_deltas` is the only field unique to it. Callers consuming the comparison digest can grep its deltas without re-reading the two source digests.

---

## Anti-patterns specific to compare mode

Canonical list lives in SKILL.md. Compare-mode additions:

- **Re-looking at the images to resolve ambiguity** — the typed output is the source of truth; ambiguity resolves by edit distance and region affinity, not by re-pixeling.
- **Skipping the `viewports_match` declaration** — comparing across mismatched viewports without normalization drowns the signal; if the caller can't declare, ask the user.
- **`exact` mode across non-matching viewports** — the skill downgrades to `structural`; note the downgrade so the caller isn't surprised.
- **Diffing fields outside the whitelist** — adding position/bbox/`parent_region` deltas back "for completeness" reintroduces filtered noise.
- **Treating renames as a single mismatch** — a rename is `extra` + `missing`, both flagged; the double-flag is the right mental model.
- **Letting bbox positional differences dominate the diff** — bbox diffs are advisory even in `exact` mode; they don't gate "is this a regression".
