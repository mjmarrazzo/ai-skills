import copy
import hashlib
import json
import re
from dataclasses import dataclass

from test_cases import graph as graph_mod
from test_cases import profile as profile_mod
from test_cases import rules
from test_cases.ir import CONSTRAINT_KEYS

LOC_ORDER = ("body", "path", "query", "header", "auth", "op", "lifecycle")
CASE_KEYS = (
    "id", "title", "operation", "kind", "loc", "field", "rule", "negative", "technique",
    "priority", "source", "specRef", "needs", "actor", "auth", "input", "steps", "expected",
    "coverage", "drift", "review", "tags",
)
_OPERATION_KEYS = ("method", "path", "operationId")
_INPUT_KEYS = ("body", "remove", "body_mode", "raw", "content_type", "path", "query", "headers")
_EXPECTED_KEYS = ("status", "code", "violations", "body", "not_persisted")
_COVERAGE_KEYS = ("status", "tests")
_REQUIRED = ("id", "title", "operation", "kind", "loc", "rule", "negative", "technique", "priority", "specRef")

_PLACEHOLDER_NEEDS_LLM = ("<<pattern-sample>>", "<<pattern-negative>>")
_REMOVED = "__remove__"
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


@dataclass(frozen=True, slots=True)
class Scope:
    entities: frozenset | None = None
    operation_ids: frozenset | None = None


def _input_defaults():
    return {
        "body": {}, "remove": [], "body_mode": "merge", "raw": None, "content_type": None,
        "path": {}, "query": {}, "headers": {},
    }


def _expected_defaults():
    return {"code": None, "violations": [], "body": None, "not_persisted": []}


def _nested(name, keys, defaults, given):
    extra = set(given) - set(keys)
    if extra:
        raise TypeError(f"unknown {name} keys: {sorted(extra)}")
    merged = {**defaults, **copy.deepcopy(dict(given))}
    missing = [k for k in keys if k not in merged]
    if missing:
        raise TypeError(f"missing {name} keys: {missing}")
    return {k: merged[k] for k in keys}


def make_case(**kw):
    extra = set(kw) - set(CASE_KEYS)
    if extra:
        raise TypeError(f"unknown case keys: {sorted(extra)}")
    missing = [k for k in _REQUIRED if k not in kw]
    if missing:
        raise TypeError(f"missing case keys: {missing}")
    plain = {
        "field": None, "needs": [], "actor": None, "auth": "valid", "source": "spec",
        "steps": None, "drift": None, "review": None, "tags": [],
    }
    given = {k: copy.deepcopy(v) for k, v in kw.items() if k in CASE_KEYS and k not in (
        "operation", "input", "expected", "coverage")}
    merged = {**plain, **given}
    merged["needs"] = list(merged["needs"])
    merged["tags"] = list(merged["tags"])
    merged["operation"] = _nested("operation", _OPERATION_KEYS, {}, kw["operation"])
    merged["input"] = _nested("input", _INPUT_KEYS, _input_defaults(), kw.get("input", {}))
    merged["expected"] = _nested("expected", _EXPECTED_KEYS, _expected_defaults(), kw.get("expected", {}))
    merged["coverage"] = _nested(
        "coverage", _COVERAGE_KEYS, {"status": "gap", "tests": []}, kw.get("coverage", {}))
    return {k: merged[k] for k in CASE_KEYS}


def _clean(text):
    return _UNSAFE.sub("_", text)


def case_id(entity, op_id, loc, field, rule_id, slug=None):
    field_part = "_" if field is None else _clean(field.replace("[]", "_items"))
    parts = [_clean(entity), _clean(op_id), _clean(loc), field_part, _clean(rule_id)]
    if slug is not None:
        raw = slug if isinstance(slug, str) else json.dumps(slug)
        text = str(slug) if not isinstance(slug, str) else slug
        cleaned = _clean(text)
        if cleaned != text or text == "":
            cleaned = (cleaned or "_") + "_" + hashlib.sha1(raw.encode()).hexdigest()[:6]
        parts.append(cleaned)
    return ".".join(parts)


def _entity_of(case):
    return case["id"].split(".")[0]


def in_scope(case, scope):
    if scope is None:
        return True
    if scope.entities is not None and _entity_of(case) not in scope.entities:
        return False
    return scope.operation_ids is None or case["operation"]["operationId"] in scope.operation_ids


def order_cases(cases, spec, graph):
    entity_idx = {e: i for i, e in enumerate(graph.order)}
    op_idx = {o.operation_id: i for i, o in enumerate(spec.operations)}
    loc_idx = {loc: i for i, loc in enumerate(LOC_ORDER)}
    end = len(LOC_ORDER)
    return sorted(cases, key=lambda c: (
        entity_idx.get(_entity_of(c), len(entity_idx)),
        op_idx.get(c["operation"]["operationId"], len(op_idx)),
        loc_idx.get(c["loc"], end),
    ))


def case_context(spec, graph, op):
    entity_id = graph_mod.op_owner(graph)[op.operation_id]
    entity = next(e for e in graph.entities if e.id == entity_id)
    needs = [n for n in entity.needs if not n.startswith("llm:")]
    if entity.item_path and op.path.startswith(entity.item_path):
        needs.append(entity.id)
    needs += [n for n in entity.needs if n.startswith("llm:")]
    return entity_id, list(dict.fromkeys(needs))


def _documented(op):
    return {int(r.status) for r in op.responses if len(r.status) == 3 and r.status.isdigit()}


def expected_status(op, prof, *, valid, kind=None, field=None):
    docs = _documented(op)
    success = min((s for s in docs if 200 <= s < 300), default=200)
    validation = 422 if 422 in docs and 400 not in docs else prof.error["statuses"]["validation"]
    persisted = []
    if kind in ("READONLY_SENT", "MASS_ASSIGNMENT"):
        mode = prof.error["unknown_fields"]
        if mode == "reject":
            status = validation
        else:
            status = success if mode == "ignore" else [success, validation]
            persisted = [field]
    else:
        status = success if valid else validation
    return status, persisted


def _undocumented(op, status):
    docs = _documented(op)
    return any(s not in docs for s in (status if isinstance(status, list) else [status]))


def _priority(row, rule_id, field_name):
    priority = "P3" if rule_id in rules.FORMAT_P3 else row.priority
    last = field_name.split(".")[-1].replace("[]", "").lower()
    if any(hint in last for hint in rules.MONEY_HINTS):
        return "P1"
    return priority


def _constraint_keyword(row, rule_id, field):
    if rule_id.startswith("type."):
        return "type"
    base = row.keyword.split(".")[0]
    if base == "format":
        return "format"
    if base in CONSTRAINT_KEYS and base in field.constraints:
        return base
    return None


def _body_delta(fields_by_path, path, value):
    tokens = re.findall(r"[^.\[]+|\[\]", path)

    def build(i, prefix):
        if i == len(tokens):
            return copy.deepcopy(value)
        token = tokens[i]
        if token == "[]":
            array = fields_by_path.get(prefix)
            floor = array.constraints.get("minItems") if array else None
            pad = max(int(floor) - 1, 0) if isinstance(floor, (int, float)) else 0
            return ["<<items:1>>"] * pad + [build(i + 1, prefix + "[]")]
        return {token: build(i + 1, f"{prefix}.{token}" if prefix else token)}

    return build(0, "")


def _dedupe_key(op, loc, field, value):
    encoded = _REMOVED if value is rules.REMOVE else json.dumps(value, sort_keys=True, default=str)
    return (op.operation_id, loc, field, encoded)


def _needs_pattern_sample(value):
    return isinstance(value, str) and any(p in value for p in _PLACEHOLDER_NEEDS_LLM)


def _field_cases(spec, op, prof, entity_id, base_needs):
    swagger2 = spec.version.startswith("2")
    fields_by_path = {f.path: f for f in op.body.fields} if op.body else {}
    targets = [("body", f.path, f, f.spec_ref, "", rules.RULES) for f in (op.body.fields if op.body else ())]
    required_rows = tuple(r for r in rules.RULES if r.id.startswith("required."))
    other_rows = tuple(r for r in rules.RULES if not r.id.startswith("required."))
    ref_prefix = "" if swagger2 else "/schema"
    for p in op.params:
        if p.location == "query":
            targets.append(("query", p.name, p.field, p.spec_ref, ref_prefix, other_rows))
        elif p.location == "header":
            targets.append(("header", p.name, p.field, p.spec_ref, ref_prefix, required_rows))

    seen = set()
    out = []
    for loc, name, field, ref, ref_prefix, rows in targets:
        for row in rows:
            for variant in rules.expand(row, field):
                value = variant.value
                if loc != "body" and value is None:
                    continue
                key = _dedupe_key(op, loc, name, value)
                if key in seen:
                    continue
                seen.add(key)
                kw = _constraint_keyword(row, variant.rule_id, field)
                if loc == "body":
                    spec_ref = f"{ref}/{kw}" if kw else ref
                    delta = {"body": {}, "remove": [name]} if value is rules.REMOVE else {
                        "body": _body_delta(fields_by_path, name, value)}
                else:
                    spec_ref = f"{ref}{ref_prefix}/{kw}" if kw else ref
                    delta = {("query" if loc == "query" else "headers"): {
                        name: None if value is rules.REMOVE else copy.deepcopy(value)}}
                valid = row.valid
                kind = "INVALID_QUERY_PARAM" if loc == "query" and not valid else row.kind
                status, persisted = expected_status(op, prof, valid=valid, kind=kind, field=name)
                tags = list(row.tags) + (["undocumented-status"] if _undocumented(op, status) else [])
                needs = list(base_needs)
                if _needs_pattern_sample(value) and "llm:pattern-sample" not in needs:
                    needs.append("llm:pattern-sample")
                title = (f"{op.method} {op.path} {'accepts' if valid else 'rejects'} {name or loc}: "
                         f"{variant.rule_id}" + (f" {variant.slug}" if variant.slug else ""))
                out.append(make_case(
                    id=case_id(entity_id, op.operation_id, loc, name, variant.rule_id, variant.slug),
                    title=title,
                    operation={"method": op.method, "path": op.path, "operationId": op.operation_id},
                    kind=kind, loc=loc, field=name, rule=variant.rule_id, negative=not valid,
                    technique=row.technique, priority=_priority(row, variant.rule_id, name),
                    specRef=spec_ref, needs=needs, input=delta,
                    expected={
                        "status": status,
                        "violations": [{"field": name}] if not valid else [],
                        "not_persisted": persisted,
                    },
                    tags=tags,
                ))
    return out


def derive(spec, graph, profile, scope=None):
    cases = []
    owner = graph_mod.op_owner(graph)
    for op in spec.operations:
        if profile_mod.is_excluded(profile, op):
            continue
        if scope is not None:
            if scope.entities is not None and owner.get(op.operation_id) not in scope.entities:
                continue
            if scope.operation_ids is not None and op.operation_id not in scope.operation_ids:
                continue
        entity_id, base_needs = case_context(spec, graph, op)
        cases.extend(_field_cases(spec, op, profile, entity_id, base_needs))
    return order_cases(cases, spec, graph)
