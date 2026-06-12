# digest-schema — pinned

The single authoritative version of the `visual-digest` YAML schema. Referenced by `ui-validation`, `blueprint`, and any future caller. Bumps to this schema require an explicit version note here and a corresponding caller update.

**Format:** YAML. Chosen because (a) human-readable for review, (b) structurally greppable by callers, (c) parseable by any future helper. JSON was rejected on readability — the user opens these files.

**Version:** v2. Changelog at the bottom (["Version history"](#version-history)).

> **v2 (2026-05-28):** Split the single `confidence` field into two axes — `confidence` (enumeration completeness) and `legibility` (observation reliability) — and added the optional `cross_frame_deltas` block for describe-mode variant sets. **Caller action required:** any caller reading `meta.confidence` must now also read `meta.legibility`; a high `confidence` no longer implies the read was reliable.

---

## Top-level shape

```yaml
meta: { ... }            # required, populated FIRST
regions: [ ... ]         # required when meta.status == ok; omit/empty when halted
elements: [ ... ]        # required when meta.status == ok; omit/empty when halted
flows: [ ... ]           # optional, populated when user actions are inferable
hierarchy: [ ... ]       # required when meta.status == ok; indented outline
open_questions: [ ... ]  # optional, entries are free-form strings
mockup_vs_impl_deltas:   # compare mode only; required when mode == compare
  missing: [ ... ]
  extra: [ ... ]
  mismatched: [ ... ]
cross_frame_deltas:      # describe-mode variant sets only (variant_set: true); optional
  baseline_frame: <basename>
  per_frame: [ ... ]
```

---

## `meta` block

| Field | Type | Required | Enum / notes |
|---|---|---|---|
| `kind` | enum | yes | `mockup` \| `live-screenshot` \| `regression-shot` |
| `source_path` | string (absolute path) | yes | The image's location on disk. |
| `viewport` | `{ w: int, h: int }` | yes | Read from image dimensions. |
| `status` | enum | yes | `ok` \| `halted_blank` \| `halted_error` \| `low_confidence`. **Populated FIRST.** |
| `status_reason` | string | conditional | Required when `status != ok`. One sentence. |
| `confidence` | enum | yes | `high` \| `medium` \| `low`. **Enumeration confidence** — how completely the visible regions/elements were enumerated. Says nothing about whether the read was *correct*. Self-honest. |
| `legibility` | enum | cond. | Required when `status == ok`. `high` \| `medium` \| `low`. **Observation confidence** — how reliably the image could actually be read (resolution, blur, downscaling, occlusion, overlap). A crisp-structure / fuzzy-text mockup is honestly `confidence: high, legibility: low`. |
| `blank_or_error_detected` | bool | yes | Set FIRST in the workflow. Implies `status` ∈ {`halted_blank`, `halted_error`}. |
| `notes_on_image_quality` | string | optional | e.g. "low-res, text hard to read", "small image, bbox omitted". |
| `expected_complexity` | enum | optional | Echoed from caller: `simple` \| `form` \| `data-grid` \| `checkout` \| `dashboard`. |
| `flow_step` | string | optional | Echoed from caller, e.g. `"1-of-3"`. Scales coverage floor. |
| `comparison_mode` | enum | compare-only | `structural` (default) \| `exact`. |
| `viewports_match` | bool | compare-only | Caller-declared; drives normalization. |

**Status semantics:**

- `ok`: digest complete and trustworthy. Caller may consume all fields.
- `halted_blank`: blank/empty canvas. Only `meta` populated. Caller treats as failure.
- `halted_error`: error UI detected (4xx, 5xx, error boundary, missing image). Only `meta` populated. Caller treats as failure.
- `low_confidence`: digest filled but the model is genuinely uncertain. `confidence` is `low`. Caller consumes as advisory.

Callers MUST check `meta.status` BEFORE consuming any other field.

**Two confidence axes (v2).** `confidence` and `legibility` measure different things and move independently:

- `confidence` = **enumeration completeness.** "Did I find and name every region/element I could see?" Coverage-check misses surface as `open_questions`; they do NOT move `confidence` (see the workflow file).
- `legibility` = **observation reliability.** "Can I trust what I read off these pixels?" Driven by image quality, not by how thorough the enumeration was.

The two are deliberately orthogonal. A downscaled mockup can have `confidence: high` (every region enumerated) and `legibility: low` (label text too fuzzy to trust) at the same time — and that combination is the honest answer, not a contradiction. Neither field is a correctness guarantee; both can be `high` on a digest that still misread a label. **Hard rule:** when `notes_on_image_quality` flags a readability problem, `legibility` must not be `high`.

---

## `regions` block

≤6 entries. The cap is a feature: more than six regions usually means the model didn't actually group, it just listed everything.

```yaml
regions:
  - id: header              # stable slug, lowercase-kebab
    bbox_pct: [0.0, 0.0, 100.0, 8.5]
    role: navigation        # enum: navigation | content | actions | metadata | other
    contents: [logo, nav-primary, user-menu]   # element ids in this region
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | slug | yes | Stable within the digest. Lowercase, kebab-case. |
| `bbox_pct` | `[x, y, w, h]` floats (1 decimal) | yes for regions | Origin top-left, percent of image. |
| `role` | enum | yes | `navigation` \| `content` \| `actions` \| `metadata` \| `other`. |
| `contents` | `[element-id, ...]` | yes | Element ids; cross-reference into `elements`. |

---

## `elements` block

```yaml
elements:
  - id: save-button         # stable slug within the digest
    kind: button            # enum (see below)
    label: "Save changes"
    state: enabled          # enum: enabled | disabled | loading | hidden | unknown
    parent_region: header   # MUST point to a region.id
    bbox_pct: [88.5, 2.1, 9.8, 3.5]   # OPTIONAL — omit when uncertain
    notes: "primary CTA, looks intentional"   # optional
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | slug | yes | Stable within the digest. |
| `kind` | enum | yes | See element kinds below. |
| `label` | string | yes | The user-visible label. Empty string for label-less elements (e.g. icons). |
| `state` | enum | yes | `enabled` \| `disabled` \| `loading` \| `hidden` \| `unknown`. |
| `parent_region` | region-id | yes | Must reference a region in `regions[]`. |
| `bbox_pct` | floats (1 decimal) | optional | **Default-omit in describe mode**; always omit for mockups and any downscaled / non-full-resolution image — eyeballed coordinates off a shrunken image are noise dressed as signal, and they cost attention. Populate only for full-resolution live screenshots, or `exact` compare mode where a human will act on the pixels. Also omit when uncertain or image dim <200px. |
| `notes` | string | optional | Short free-form note. |

**`kind` enum:** `button` \| `input` \| `link` \| `image` \| `tile` \| `card` \| `badge` \| `text` \| `icon` \| `divider` \| `other`.

**Every element MUST have a `parent_region`.** Unplaceable elements either go into the `other` region or get noted in `open_questions` instead.

---

## `flows` block (optional)

Inferable user actions and outcomes.

```yaml
flows:
  - description: "Click 'Add card' → modal with inputs [card-number, exp, cvv, name]"
    confidence: medium       # high | medium | low
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `description` | string | yes | One sentence; pattern: "Action → Outcome". |
| `confidence` | enum | yes | How sure are we this flow exists. Independent of `meta.confidence`. |

---

## `hierarchy` block

Indented outline of the page. Two-space indent; format `<id>: <kind>: <label>`.

```yaml
hierarchy:
  - "header (navigation)"
  - "  logo (image)"
  - "  nav-primary (link x3)"
  - "  user-menu (button)"
  - "main (content)"
  - "  page-title (text): 'Dashboard'"
  - "  metric-tile (tile x4)"
```

Forces the model to express grouping, which makes coverage misses obvious.

---

## `open_questions` block

Free-form strings. Things the model genuinely couldn't tell, OR coverage-check misses.

```yaml
open_questions:
  - "Is the 'Beta' badge clickable? Hover state isn't visible in a static image."
  - "Expected ≥4 inputs based on complexity 'checkout'; saw 2 — is this mid-flow?"
```

Coverage misses go here. **They do not downgrade `meta.confidence`** — see the workflow file.

---

## `mockup_vs_impl_deltas` block (compare mode only)

Populated by diffing the TWO digests' typed fields. Never by re-looking at images.

```yaml
mockup_vs_impl_deltas:
  missing:                   # in mockup, not in impl
    - mockup_id: save-button
      kind: button
      label: "Save changes"
      parent_region: header
  extra:                     # in impl, not in mockup
    - impl_id: beta-badge
      kind: badge
      label: "Beta"
      parent_region: header
  mismatched:                # same conceptual element, different details
    - mockup_id: cta-primary
      impl_id: primary-action
      field: label             # field: label | state | parent_region | kind
      mockup_value: "Continue"
      impl_value: "Proceed"
```

**Field whitelist per kind** (in `structural` mode):

| Kind | Diffed fields |
|---|---|
| `button`, `link` | `label`, `state` |
| `input` | `label`, `state`, presence |
| `image`, `icon` | presence + `kind` only |
| `text`, `badge` | presence + `label` |
| `tile`, `card` | presence + child count |
| `divider`, `other` | presence only |

`parent_region` is diffed only in `exact` mode with `viewports_match: true`. Otherwise suppressed (responsive layouts legitimately reassign regions).

---

## `cross_frame_deltas` block (describe-mode variant sets only)

Present only when `mode == describe` AND the caller passed `variant_set: true` (≥2 images that are variants of the *same* screen — design alternatives, A/B frames, before/after of one view). This is NOT compare mode: there is no mockup-vs-impl "right answer," just N frames of one screen whose differences are the point.

Every frame still gets its OWN full, independent describe digest on disk — the forced full enumeration of each frame is exactly what surfaces the deltas (a body paragraph present in one frame and absent in another only shows up because both were fully enumerated, not skimmed). `cross_frame_deltas` is then a **string diff of those typed digests** — never a fresh side-by-side vision pass — and it is the consolidated artifact a human or caller actually reads instead of eyeballing N sprawling digests.

```yaml
cross_frame_deltas:
  baseline_frame: grid-default          # the canonical frame other frames diff against
  per_frame:
    - frame: grid-empty-state           # basename of the sibling frame's digest
      missing:                          # in baseline, absent in this frame
        - id: body-copy
          kind: text
          label: "Choose a template to get started"
          parent_region: main
      extra: []                         # in this frame, absent in baseline
      mismatched:                       # same element, differing whitelisted field
        - id: cta-primary
          field: state
          baseline_value: enabled
          frame_value: disabled
```

Same matching and field-whitelist rules as `mockup_vs_impl_deltas` (match by `id` then `(kind, label)`; diff the per-kind whitelist). The baseline frame is the most complete / canonical variant; pick it explicitly and note the choice in `open_questions` if it isn't obvious.

---

## Worked example: describe mode, mockup

```yaml
# .claude-plans/<active>/visual-digests/checkout-describe-1440x900.yml
meta:
  kind: mockup
  source_path: /Users/me/coding/proj/designs/checkout.png
  viewport: { w: 1440, h: 900 }
  status: ok
  confidence: high
  legibility: high
  blank_or_error_detected: false
  expected_complexity: checkout

regions:
  - id: header
    bbox_pct: [0.0, 0.0, 100.0, 8.0]
    role: navigation
    contents: [logo, step-indicator]
  - id: main
    bbox_pct: [20.0, 8.0, 60.0, 80.0]
    role: content
    contents: [page-title, card-number, card-exp, card-cvv, name-on-card, billing-address, cta-pay]
  - id: aside
    bbox_pct: [80.0, 8.0, 20.0, 80.0]
    role: metadata
    contents: [order-summary]
  - id: footer
    bbox_pct: [0.0, 88.0, 100.0, 12.0]
    role: navigation
    contents: [trust-badges]

elements:
  - { id: logo, kind: image, label: "", state: enabled, parent_region: header }
  - { id: step-indicator, kind: text, label: "Step 3 of 3 — Payment", state: enabled, parent_region: header }
  - { id: page-title, kind: text, label: "Payment details", state: enabled, parent_region: main }
  - { id: card-number, kind: input, label: "Card number", state: enabled, parent_region: main }
  - { id: card-exp, kind: input, label: "Expiry", state: enabled, parent_region: main }
  - { id: card-cvv, kind: input, label: "CVV", state: enabled, parent_region: main }
  - { id: name-on-card, kind: input, label: "Name on card", state: enabled, parent_region: main }
  - { id: billing-address, kind: input, label: "Billing address", state: enabled, parent_region: main }
  - { id: cta-pay, kind: button, label: "Pay $42.99", state: enabled, parent_region: main, notes: "primary CTA" }
  - { id: order-summary, kind: card, label: "Order summary", state: enabled, parent_region: aside }
  - { id: trust-badges, kind: image, label: "", state: enabled, parent_region: footer }

flows:
  - description: "Fill card fields → click 'Pay' → server validates and redirects to confirmation"
    confidence: medium

hierarchy:
  - "header (navigation)"
  - "  logo (image)"
  - "  step-indicator (text): 'Step 3 of 3 — Payment'"
  - "main (content)"
  - "  page-title (text): 'Payment details'"
  - "  card-number, card-exp, card-cvv, name-on-card, billing-address (input x5)"
  - "  cta-pay (button): 'Pay $42.99'"
  - "aside (metadata)"
  - "  order-summary (card)"
  - "footer (navigation)"
  - "  trust-badges (image)"

open_questions: []
```

---

## Worked example: describe mode, live screenshot

```yaml
# .claude-plans/<active>/visual-digests/dashboard-describe-1280x800.yml
meta:
  kind: live-screenshot
  source_path: /Users/me/coding/proj/.claude-plans/PROJ-1234-feature/screenshots/task-3/desktop/dashboard.png
  viewport: { w: 1280, h: 800 }
  status: ok
  confidence: high
  legibility: high
  blank_or_error_detected: false
  expected_complexity: dashboard

regions:
  - id: header
    bbox_pct: [0.0, 0.0, 100.0, 7.5]
    role: navigation
    contents: [logo, search, user-menu]
  - id: sidebar
    bbox_pct: [0.0, 7.5, 18.0, 92.5]
    role: navigation
    contents: [nav-overview, nav-tickets, nav-reports, nav-settings]
  - id: main
    bbox_pct: [18.0, 7.5, 82.0, 92.5]
    role: content
    contents: [page-title, tile-revenue, tile-users, tile-uptime, tile-errors, chart-traffic]

elements:
  - { id: logo, kind: image, label: "", state: enabled, parent_region: header }
  - { id: search, kind: input, label: "Search", state: enabled, parent_region: header }
  - { id: user-menu, kind: button, label: "MM", state: enabled, parent_region: header, notes: "avatar w/ initials" }
  - { id: nav-overview, kind: link, label: "Overview", state: enabled, parent_region: sidebar }
  - { id: nav-tickets, kind: link, label: "Tickets", state: enabled, parent_region: sidebar }
  - { id: nav-reports, kind: link, label: "Reports", state: enabled, parent_region: sidebar }
  - { id: nav-settings, kind: link, label: "Settings", state: enabled, parent_region: sidebar }
  - { id: page-title, kind: text, label: "Overview", state: enabled, parent_region: main }
  - { id: tile-revenue, kind: tile, label: "Revenue — $128.4k", state: enabled, parent_region: main }
  - { id: tile-users, kind: tile, label: "Users — 2,341", state: enabled, parent_region: main }
  - { id: tile-uptime, kind: tile, label: "Uptime — 99.97%", state: enabled, parent_region: main }
  - { id: tile-errors, kind: tile, label: "Errors — 12", state: enabled, parent_region: main }
  - { id: chart-traffic, kind: image, label: "Traffic chart", state: enabled, parent_region: main, notes: "line chart, 7-day window" }

flows:
  - description: "Click sidebar nav link → route changes, main content updates"
    confidence: high

hierarchy:
  - "header (navigation)"
  - "  logo (image), search (input), user-menu (button)"
  - "sidebar (navigation)"
  - "  nav-overview, nav-tickets, nav-reports, nav-settings (link x4)"
  - "main (content)"
  - "  page-title (text): 'Overview'"
  - "  tile-revenue, tile-users, tile-uptime, tile-errors (tile x4)"
  - "  chart-traffic (image)"

open_questions:
  - "Is the user-menu avatar clickable to open a dropdown? Static image can't tell."
```

---

## Worked example: compare mode (mockup + live, deltas populated)

```yaml
# .claude-plans/<active>/visual-digests/checkout-compare-1440x900.yml
# This is the COMPARE-LEVEL digest; each source image also has its own independent digest:
#   checkout-mockup-describe-1440x900.yml
#   checkout-impl-describe-1440x900.yml
meta:
  kind: regression-shot
  source_path: /Users/me/coding/proj/.claude-plans/PROJ-1234/screenshots/task-5/desktop/checkout.png
  viewport: { w: 1440, h: 900 }
  status: ok
  confidence: high
  legibility: high
  blank_or_error_detected: false
  expected_complexity: checkout
  comparison_mode: structural
  viewports_match: true

# Regions and elements are duplicated from the IMPL digest (the "current" side).
# Full per-image digests live in the two sibling files above.
regions: [ ... see checkout-impl-describe-1440x900.yml ... ]
elements: [ ... see checkout-impl-describe-1440x900.yml ... ]
flows: []
hierarchy: [ ... ]
open_questions: []

mockup_vs_impl_deltas:
  missing:
    - mockup_id: billing-address
      kind: input
      label: "Billing address"
      parent_region: main
  extra:
    - impl_id: save-card-toggle
      kind: input
      label: "Save card for next time"
      parent_region: main
  mismatched:
    - mockup_id: cta-pay
      impl_id: cta-pay
      field: label
      mockup_value: "Pay $42.99"
      impl_value: "Pay now"
    - mockup_id: card-cvv
      impl_id: card-cvv
      field: state
      mockup_value: enabled
      impl_value: disabled
```

---

## Worked example: blank canvas halt

```yaml
# .claude-plans/<active>/visual-digests/checkout-describe-1440x900.yml
meta:
  kind: live-screenshot
  source_path: /Users/me/coding/proj/.claude-plans/PROJ-1234/screenshots/task-5/desktop/checkout.png
  viewport: { w: 1440, h: 900 }
  status: halted_blank
  status_reason: "Image is entirely white viewport with no rendered content"
  confidence: high
  blank_or_error_detected: true
  notes_on_image_quality: "blank canvas detected; nothing to digest"

# regions, elements, flows, hierarchy, open_questions, mockup_vs_impl_deltas all OMITTED.
```

Caller (`ui-validation`) reads `meta.status: halted_blank`, treats as verification failure, and hands to `debug-loop` with the digest path as context.

---

## Schema invariants (parsers can rely on these)

- `meta` is always present. `meta.status` is always populated.
- When `meta.status != ok`: `regions`, `elements`, `flows`, `hierarchy`, `mockup_vs_impl_deltas` MAY be omitted entirely. `open_questions` MAY be present (e.g. "image was blank — was that intentional?").
- Every `element.parent_region` references a `region.id` in the same file.
- Every id in `region.contents[]` references an `element.id` in the same file.
- `mockup_vs_impl_deltas` appears only when `mode == compare`.
- `cross_frame_deltas` appears only when `mode == describe` AND `variant_set: true`. Each frame referenced in it has its own full describe digest on disk.
- `meta.legibility` is present whenever `meta.status == ok` (and whenever any content was read). It is independent of `meta.confidence`.
- `bbox_pct` values are floats with one decimal of precision. Default-omitted in describe mode and always omitted for mockups / non-full-res / downscaled images; omitted entirely when image dim <200px or model uncertainty is high.
- `viewports_match: false` implies `comparison_mode: structural` automatically (skill enforces this).

---

## Version history

- **v2 (2026-05-28):** Split `confidence` into `confidence` (enumeration completeness) + `legibility` (observation reliability) — the old single field conflated "I found everything" with "I can trust what I read," letting a possibly-misread image report `confidence: high`. Added `cross_frame_deltas` for describe-mode variant sets so the value of forced cross-frame enumeration has a structured home. Strengthened `bbox_pct` to default-omit in describe mode / on non-full-res images. **Caller migration:** read `meta.legibility` alongside `meta.confidence`; a clean digest is an attention artifact, not a correctness certificate.
- **v1:** Initial schema — `meta`, `regions`, `elements`, `flows`, `hierarchy`, `open_questions`, `mockup_vs_impl_deltas`.
