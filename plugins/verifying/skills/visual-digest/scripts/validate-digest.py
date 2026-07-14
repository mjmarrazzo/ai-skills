#!/usr/bin/env python3
"""Validate a visual-digest YAML file against the pinned schema invariants.

Usage: python3 validate-digest.py <digest.yml> [...more digests]

Enforces the invariants in references/digest-schema.md (v2): required meta
fields and enums, status/field gating, parent_region and contents cross-refs,
bbox rules, and delta-block gating. Exits 0 when every file is clean,
nonzero with one message per violation otherwise.
"""

import sys

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "validate-digest.py requires PyYAML (import yaml failed).\n"
        "Install it with: pip3 install pyyaml\n"
    )
    sys.exit(2)

META_STATUS = {"ok", "halted_blank", "halted_error", "low_confidence"}
META_KIND = {"mockup", "live-screenshot", "regression-shot"}
LEVELS = {"high", "medium", "low"}
REGION_ROLES = {"navigation", "content", "actions", "metadata", "other"}
ELEMENT_KINDS = {"button", "input", "link", "image", "tile", "card",
                 "badge", "text", "icon", "divider", "other"}
ELEMENT_STATES = {"enabled", "disabled", "loading", "hidden", "unknown"}
COMPARISON_MODES = {"structural", "exact"}
HALTED = {"halted_blank", "halted_error"}


def is_bbox(v):
    return (isinstance(v, list) and len(v) == 4
            and all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in v))


def validate(doc, errors):
    err = errors.append

    if not isinstance(doc, dict):
        err("digest must be a YAML mapping at the top level")
        return

    # --- meta ---
    meta = doc.get("meta")
    if not isinstance(meta, dict):
        err("meta: required block is missing or not a mapping")
        return
    status = meta.get("status")

    for field in ("kind", "source_path", "viewport", "status", "confidence",
                  "blank_or_error_detected"):
        if field not in meta:
            err(f"meta.{field}: required field is missing")

    if "kind" in meta and meta["kind"] not in META_KIND:
        err(f"meta.kind: '{meta['kind']}' not in {sorted(META_KIND)}")
    if "status" in meta and status not in META_STATUS:
        err(f"meta.status: '{status}' not in {sorted(META_STATUS)}")
    if "confidence" in meta and meta["confidence"] not in LEVELS:
        err(f"meta.confidence: '{meta['confidence']}' not in {sorted(LEVELS)}")

    viewport = meta.get("viewport")
    if "viewport" in meta and not (
            isinstance(viewport, dict)
            and isinstance(viewport.get("w"), int)
            and isinstance(viewport.get("h"), int)):
        err("meta.viewport: must be a mapping { w: int, h: int }")

    if status is not None and status != "ok" and not meta.get("status_reason"):
        err(f"meta.status_reason: required when status is '{status}'")

    if status == "ok":
        if "legibility" not in meta:
            err("meta.legibility: required when status == ok")
        elif meta["legibility"] not in LEVELS:
            err(f"meta.legibility: '{meta['legibility']}' not in {sorted(LEVELS)}")

    boe = meta.get("blank_or_error_detected")
    if boe is True and status not in HALTED:
        err("meta.blank_or_error_detected is true but status is not halted_blank/halted_error")
    if status in HALTED and boe is not True:
        err(f"meta.status is '{status}' but blank_or_error_detected is not true")

    if "comparison_mode" in meta and meta["comparison_mode"] not in COMPARISON_MODES:
        err(f"meta.comparison_mode: '{meta['comparison_mode']}' not in {sorted(COMPARISON_MODES)}")
    if meta.get("viewports_match") is False and meta.get("comparison_mode") == "exact":
        err("meta: viewports_match false requires comparison_mode structural (exact is incoherent)")

    # --- status gating ---
    content_blocks = ("regions", "elements", "flows", "hierarchy")
    if status in HALTED:
        for block in content_blocks + ("mockup_vs_impl_deltas", "cross_frame_deltas"):
            if doc.get(block):
                err(f"{block}: must be omitted/empty when status is '{status}' (meta-only digest)")
        return  # nothing else applies to a halted digest

    if status in ("ok", "low_confidence"):
        for block in ("regions", "elements", "hierarchy"):
            if block not in doc:
                err(f"{block}: required when status == '{status}'")

    # --- regions ---
    regions = doc.get("regions") or []
    region_ids = set()
    if not isinstance(regions, list):
        err("regions: must be a list")
        regions = []
    if len(regions) > 6:
        err(f"regions: {len(regions)} entries — cap is 6 (collapse extras into 'other')")
    for i, region in enumerate(regions):
        where = f"regions[{i}]"
        if not isinstance(region, dict):
            err(f"{where}: must be a mapping")
            continue
        rid = region.get("id")
        if not rid:
            err(f"{where}.id: required")
        elif rid in region_ids:
            err(f"{where}.id: duplicate region id '{rid}'")
        else:
            region_ids.add(rid)
        if not is_bbox(region.get("bbox_pct")):
            err(f"{where}.bbox_pct: required [x, y, w, h] numeric list for regions")
        if region.get("role") not in REGION_ROLES:
            err(f"{where}.role: '{region.get('role')}' not in {sorted(REGION_ROLES)}")
        if not isinstance(region.get("contents"), list):
            err(f"{where}.contents: required list of element ids")

    # --- elements ---
    elements = doc.get("elements") or []
    element_ids = set()
    if not isinstance(elements, list):
        err("elements: must be a list")
        elements = []
    for i, el in enumerate(elements):
        where = f"elements[{i}]"
        if not isinstance(el, dict):
            err(f"{where}: must be a mapping")
            continue
        eid = el.get("id")
        if not eid:
            err(f"{where}.id: required")
        elif eid in element_ids:
            err(f"{where}.id: duplicate element id '{eid}'")
        else:
            element_ids.add(eid)
        if el.get("kind") not in ELEMENT_KINDS:
            err(f"{where}.kind: '{el.get('kind')}' not in {sorted(ELEMENT_KINDS)}")
        if "label" not in el or not isinstance(el.get("label"), str):
            err(f"{where}.label: required string (empty string for label-less elements)")
        if el.get("state") not in ELEMENT_STATES:
            err(f"{where}.state: '{el.get('state')}' not in {sorted(ELEMENT_STATES)}")
        parent = el.get("parent_region")
        if not parent:
            err(f"{where}.parent_region: required — every element must have a parent")
        elif parent not in region_ids:
            err(f"{where}.parent_region: '{parent}' does not reference any region.id")
        if "bbox_pct" in el and not is_bbox(el["bbox_pct"]):
            err(f"{where}.bbox_pct: when present, must be [x, y, w, h] numeric list")

    # --- contents cross-refs ---
    for i, region in enumerate(regions):
        if isinstance(region, dict) and isinstance(region.get("contents"), list):
            for cid in region["contents"]:
                if cid not in element_ids:
                    err(f"regions[{i}].contents: '{cid}' does not reference any element.id")

    # --- flows ---
    flows = doc.get("flows") or []
    if not isinstance(flows, list):
        err("flows: must be a list")
        flows = []
    for i, flow in enumerate(flows):
        if not isinstance(flow, dict) or not flow.get("description"):
            err(f"flows[{i}].description: required")
            continue
        if flow.get("confidence") not in LEVELS:
            err(f"flows[{i}].confidence: '{flow.get('confidence')}' not in {sorted(LEVELS)}")

    # --- delta blocks ---
    mvid = doc.get("mockup_vs_impl_deltas")
    if mvid is not None:
        if "comparison_mode" not in meta:
            err("mockup_vs_impl_deltas: present but meta.comparison_mode is missing "
                "(deltas appear only in compare mode)")
        if not isinstance(mvid, dict):
            err("mockup_vs_impl_deltas: must be a mapping")
        else:
            for key in ("missing", "extra", "mismatched"):
                if key not in mvid or not isinstance(mvid[key], list):
                    err(f"mockup_vs_impl_deltas.{key}: required list")

    cfd = doc.get("cross_frame_deltas")
    if cfd is not None:
        if not isinstance(cfd, dict):
            err("cross_frame_deltas: must be a mapping")
        else:
            if not cfd.get("baseline_frame"):
                err("cross_frame_deltas.baseline_frame: required")
            if not isinstance(cfd.get("per_frame"), list):
                err("cross_frame_deltas.per_frame: required list")
    if mvid is not None and cfd is not None:
        err("mockup_vs_impl_deltas and cross_frame_deltas are mutually exclusive "
            "(compare mode vs describe variant-set)")


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(__doc__.strip() + "\n")
        return 2
    exit_code = 0
    for path in argv[1:]:
        errors = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except FileNotFoundError:
            errors.append("file not found")
            doc = None
        except yaml.YAMLError as exc:
            errors.append(f"YAML parse error: {exc}")
            doc = None
        if doc is not None:
            validate(doc, errors)
        if errors:
            exit_code = 1
            for message in errors:
                print(f"{path}: {message}")
        else:
            print(f"{path}: ok")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
