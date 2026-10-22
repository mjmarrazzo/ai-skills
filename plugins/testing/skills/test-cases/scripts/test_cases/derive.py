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


def _money_bump(priority, field_name):
    last = field_name.split(".")[-1].replace("[]", "").lower()
    return "P1" if any(hint in last for hint in rules.MONEY_HINTS) else priority


def _priority(row, rule_id, field_name):
    return _money_bump("P3" if rule_id in rules.FORMAT_P3 else row.priority, field_name)


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


def _row_case(op, prof, entity_id, needs, *, loc, field, rule, kind, valid, technique, priority,
              spec_ref, label, delta=None, slug=None, status=None, violations=None,
              persisted=(), tags=()):
    if status is None:
        status, persisted = expected_status(op, prof, valid=valid, kind=kind, field=field)
    all_tags = list(tags) + (["undocumented-status"] if _undocumented(op, status) else [])
    return make_case(
        id=case_id(entity_id, op.operation_id, loc, field, rule, slug),
        title=f"{op.method} {op.path} {'accepts' if valid else 'rejects'} {label}",
        operation={"method": op.method, "path": op.path, "operationId": op.operation_id},
        kind=kind, loc=loc, field=field, rule=rule, negative=not valid, technique=technique,
        priority=priority, specRef=spec_ref, needs=needs, input=delta or {},
        expected={
            "status": status,
            "violations": violations if violations is not None else (
                [{"field": field}] if not valid and field else []),
            "not_persisted": list(persisted),
        },
        tags=all_tags,
    )


def _target_cases(op, prof, entity_id, base_needs, target, seen):
    loc, name, field, ref, ref_prefix, rows, fields_by_path = target
    out = []
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
            needs = list(base_needs)
            if _needs_pattern_sample(value) and "llm:pattern-sample" not in needs:
                needs.append("llm:pattern-sample")
            out.append(_row_case(
                op, prof, entity_id, needs, loc=loc, field=name, rule=variant.rule_id, kind=kind,
                valid=valid, technique=row.technique, priority=_priority(row, variant.rule_id, name),
                spec_ref=spec_ref, label=f"{name or loc}: {variant.rule_id}"
                + (f" {variant.slug}" if variant.slug else ""),
                delta=delta, slug=variant.slug, tags=row.tags))
    return out


def _is_top_level(field):
    return "." not in field.path and "[]" not in field.path


def _body_cases(op, prof, entity_id, needs, seen):
    fields = op.body.fields
    by_path = {f.path: f for f in fields}
    out = []
    for f in fields:
        out += _target_cases(op, prof, entity_id, needs, ("body", f.path, f, f.spec_ref, "", rules.RULES, by_path), seen)
        if f.type == "string" and "maxLength" not in f.constraints and not f.truncated:
            key = _dedupe_key(op, "body", f.path, "<<str:10000>>")
            if key not in seen:
                seen.add(key)
                status = [expected_status(op, prof, valid=False)[0], 413]
                out.append(_row_case(
                    op, prof, entity_id, needs, loc="body", field=f.path, rule="unbounded.oversize",
                    kind="RESOURCE_LIMIT", valid=False, technique="owasp-api4",
                    priority=_money_bump("P3", f.path), spec_ref=f.spec_ref,
                    label=f"{f.path}: unbounded.oversize",
                    delta={"body": _body_delta(by_path, f.path, "<<str:10000>>")}, status=status))
        if _is_top_level(f) and not f.required:
            out.append(_row_case(
                op, prof, entity_id, needs, loc="body", field=f.path, rule="optional.absent",
                kind="OPTIONAL_ABSENT", valid=True, technique="ep",
                priority=_money_bump("P3", f.path), spec_ref=f.spec_ref,
                label=f"{f.path}: optional.absent", delta={"remove": [f.path]}))
    if op.body.additional_properties is False:
        out.append(_row_case(
            op, prof, entity_id, needs, loc="body", field=None, rule="additionalProperties.unknown",
            kind="UNKNOWN_FIELD", valid=False, technique="error-guess", priority="P2",
            spec_ref=op.body.spec_ref, label="body: additionalProperties.unknown",
            delta={"body": {"__unexpected_field__": "x"}}))
    if op.body.root_type == "object" and op.body.additional_properties is not False:
        top = {f.path for f in fields if _is_top_level(f)}
        for name, value in rules.MASS_ASSIGNMENT_PROBES:
            if name in top:
                continue
            out.append(_row_case(
                op, prof, entity_id, needs, loc="body", field=name, rule=f"mass_assignment.{name}",
                kind="MASS_ASSIGNMENT", valid=False, technique="owasp-api3", priority="P1",
                spec_ref=op.body.spec_ref, label=f"{name}: mass_assignment", delta={"body": {name: value}}))
    return out


def _path_value(param):
    field = param.field
    if field.format == "uuid":
        return "not-a-uuid", False
    if field.type in ("integer", "number"):
        return "abc", False
    pattern = field.constraints.get("pattern")
    if not isinstance(pattern, str):
        return None, False
    if rules.compile_pattern(pattern) is None:
        return "<<pattern-negative>>", True
    probe = next(r for r in rules.RULES if r.id == "pattern.out_of_class")
    variants = rules.expand(probe, field)
    return (variants[0].value, False) if variants else (None, False)


def _path_cases(op, prof, entity_id, base_needs):
    needs = [n for n in base_needs if n != entity_id]
    tenant = prof.tenant["param"]
    out = []
    for p in op.params:
        if p.location != "path":
            continue
        value, llm = _path_value(p)
        if value is not None:
            out.append(_row_case(
                op, prof, entity_id, needs + (["llm:pattern-sample"] if llm else []), loc="path",
                field=p.name, rule="path.malformed", kind="INVALID_ID_FORMAT", valid=False,
                technique="error-guess", priority="P2", spec_ref=p.spec_ref,
                label=f"{p.name}: path.malformed", delta={"path": {p.name: value}}))
        if p.name != tenant:
            out.append(_row_case(
                op, prof, entity_id, needs, loc="path", field=p.name, rule="path.not_found",
                kind="NOT_FOUND", valid=False, technique="error-guess", priority="P2",
                spec_ref=p.spec_ref, label=f"{p.name}: path.not_found",
                delta={"path": {p.name: f"<<nonexistent:{p.name}>>"}},
                status=prof.error["statuses"]["not_found"], violations=[]))
    return out


def _query_extras(op, prof, entity_id, needs, p, seen):
    out = []

    def add(rule, kind, valid, technique, value, status=None, priority="P2"):
        delta = {"query": {p.name: value}} if value is not rules.REMOVE else {"query": {}}
        if value is not rules.REMOVE and rule != "pagination.walk":
            key = _dedupe_key(op, "query", p.name, value)
            if key in seen:
                return
            seen.add(key)
        out.append(_row_case(
            op, prof, entity_id, needs, loc="query", field=p.name, rule=rule, kind=kind,
            valid=valid, technique=technique, priority=priority, spec_ref=p.spec_ref,
            label=f"{p.name}: {rule}", delta=delta, status=status))

    if p.required:
        key = _dedupe_key(op, "query", p.name, None)
        seen.add(key)
        out.append(_row_case(
            op, prof, entity_id, needs, loc="query", field=p.name, rule="query.missing",
            kind="INVALID_QUERY_PARAM", valid=False, technique="ep", priority="P2",
            spec_ref=p.spec_ref, label=f"{p.name}: query.missing", delta={"query": {p.name: None}}))
    if p.name in rules.PAGINATION_NAMES:
        add("pagination.walk", "PAGINATION", True, "ep", rules.REMOVE)
        bad = -1 if p.field.type == "integer" else "not-a-valid-cursor"
        add("pagination.bad_cursor", "INVALID_QUERY_PARAM", False, "error-guess", bad)
    if p.name in rules.LIMIT_NAMES:
        maximum = p.field.constraints.get("maximum")
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
            add("limit.over_max", "RESOURCE_LIMIT", False, "owasp-api4", maximum + 1)
        for rule, value in (("limit.zero", 0), ("limit.negative", -1), ("limit.huge", 10**9)):
            add(rule, "RESOURCE_LIMIT", False, "owasp-api4", value)
    return out


def _auth_cases(op, prof, entity_id, needs):
    def make(rule, kind, valid, auth, status=None, tags=()):
        return _row_case(
            op, prof, entity_id, needs, loc="auth", field=None, rule=rule, kind=kind, valid=valid,
            technique="auth-matrix", priority="P1", spec_ref=op.spec_ref, label=f"op: {rule}",
            delta={}, status=status, tags=tags) | {"auth": auth}

    if not op.security.secured:
        return [make("auth.public", "PUBLIC_REACHABLE", True, "none", tags=("security",))]
    return [
        make("auth.missing", "AUTH_MISSING", False, "none", prof.auth["missing"]["status"]),
        make("auth.malformed", "AUTH_INVALID", False, "malformed", prof.auth["malformed"]["status"]),
    ]


def _op_level_cases(op, prof, entity_id, needs):
    def make(rule, kind, valid, priority, delta, status=None):
        return _row_case(
            op, prof, entity_id, needs, loc="op", field=None, rule=rule, kind=kind, valid=valid,
            technique="ep" if valid or rule.startswith("required") else "error-guess",
            priority=priority, spec_ref=op.spec_ref, label=f"op: {rule}", delta=delta, status=status)

    out = [make("happy.full", "HAPPY_FULL", True, "P1", {})]
    if not op.body:
        return out
    top = [f for f in op.body.fields if _is_top_level(f)]
    optional = [f.path for f in top if not f.required]
    if optional:
        out.append(make("happy.min", "HAPPY_MIN", True, "P2", {"remove": optional}))
    if any(f.required for f in top):
        out.append(make("required.all_missing", "REQUIRED_MISSING", False, "P2",
                        {"body": {}, "body_mode": "replace"}))
    out += [
        make("body.malformed", "MALFORMED_BODY", False, "P2", {"body_mode": "raw", "raw": '{"'}),
        make("body.array", "MALFORMED_BODY", False, "P2", {"body_mode": "raw", "raw": "[]"}),
        make("body.empty", "EMPTY_BODY", False, "P2", {"body_mode": "none"}),
        make("body.content_type", "WRONG_CONTENT_TYPE", False, "P2", {"content_type": "text/plain"},
             prof.error["statuses"]["unsupported_media"]),
    ]
    return out


def _op_cases(op, prof, entity_id, base_needs, swagger2):
    seen = set()
    out = _body_cases(op, prof, entity_id, base_needs, seen) if op.body else []
    out += _path_cases(op, prof, entity_id, base_needs)
    ref_prefix = "" if swagger2 else "/schema"
    for p in op.params:
        if p.location == "query":
            target = ("query", p.name, p.field, p.spec_ref, ref_prefix, tuple(
                r for r in rules.RULES if not r.id.startswith("required.")), {})
            out += _target_cases(op, prof, entity_id, base_needs, target, seen)
            out += _query_extras(op, prof, entity_id, base_needs, p, seen)
        elif p.location == "header":
            target = ("header", p.name, p.field, p.spec_ref, ref_prefix, tuple(
                r for r in rules.RULES if r.id.startswith("required.")), {})
            out += _target_cases(op, prof, entity_id, base_needs, target, seen)
    out += _auth_cases(op, prof, entity_id, base_needs)
    out += _op_level_cases(op, prof, entity_id, base_needs)
    return out


def _lowest_2xx(op):
    return min((s for s in _documented(op) if 200 <= s < 300), default=200)


def _step(op, expect, capture=None):
    return {"operationId": op.operation_id, "expect": expect, "capture": capture}


def _lifecycle_case(create, entity, needs, rule, kind, negative, priority, steps, title):
    return make_case(
        id=case_id(entity.id, create.operation_id, "lifecycle", None, rule),
        title=title,
        operation={"method": create.method, "path": create.path, "operationId": create.operation_id},
        kind=kind, loc="lifecycle", field=None, rule=rule, negative=negative,
        technique="lifecycle", priority=priority, specRef=create.spec_ref, needs=needs,
        steps=steps, expected={"status": steps[-1]["expect"]},
    )


def _lifecycle_cases(spec, graph, prof):
    ops = {o.operation_id: o for o in spec.operations}
    out = []
    for entity in graph.entities:
        by_flag = {f: ops[op_id] for f, op_id in entity.ops.items()
                   if not profile_mod.is_excluded(prof, ops[op_id])}
        create, read = by_flag.get("C"), by_flag.get("R")
        if create is None or read is None:
            continue
        needs = list(entity.needs)
        if entity.id_candidate is None or entity.id_param is None:
            needs.append("llm:id-threading")
        needs = list(dict.fromkeys(needs))
        capture = ({entity.id_param: entity.id_candidate["field"]}
                   if entity.id_candidate and entity.id_param else None)
        not_found = prof.error["statuses"]["not_found"]
        first = _step(create, _lowest_2xx(create), capture)
        steps = [first, _step(read, _lowest_2xx(read))]
        mutate = by_flag.get("U") or by_flag.get("P")
        if mutate is not None:
            steps += [_step(mutate, _lowest_2xx(mutate)), _step(read, _lowest_2xx(read))]
        delete = by_flag.get("D")
        if delete is not None:
            steps += [_step(delete, _lowest_2xx(delete)), _step(read, not_found)]
        out.append(_lifecycle_case(
            create, entity, needs, "lifecycle.crud", "LIFECYCLE", False, "P1", steps,
            f"{entity.id}: create, read and mutate through the lifecycle"))
        if delete is not None:
            twice = [copy.deepcopy(first), _step(delete, _lowest_2xx(delete)), _step(delete, not_found)]
            out.append(_lifecycle_case(
                create, entity, needs, "lifecycle.delete_twice", "DELETE_TWICE", True, "P2", twice,
                f"{entity.id}: second delete returns not found"))
    return out


def derive(spec, graph, profile, scope=None):
    cases = []
    owner = graph_mod.op_owner(graph)
    swagger2 = spec.version.startswith("2")
    for op in spec.operations:
        if profile_mod.is_excluded(profile, op):
            continue
        if scope is not None:
            if scope.entities is not None and owner.get(op.operation_id) not in scope.entities:
                continue
            if scope.operation_ids is not None and op.operation_id not in scope.operation_ids:
                continue
        entity_id, base_needs = case_context(spec, graph, op)
        cases.extend(_op_cases(op, profile, entity_id, base_needs, swagger2))
    cases.extend(c for c in _lifecycle_cases(spec, graph, profile) if in_scope(c, scope))
    return order_cases(cases, spec, graph)
