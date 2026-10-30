import copy
import re
from dataclasses import dataclass

DEFAULTS = {
    "version": 1,
    "name": "generic",
    "service_path": None,
    "stack": None,
    "auth": {
        "default_actor": "default",
        "missing": {"status": 401, "body": None},
        "malformed": {"status": 401, "value": "Bearer invalid.token.value", "body": None},
    },
    "actors": ["default"],
    "error": {
        "keys": {"code": "code", "violations": "violations", "field": "field", "message": "message"},
        "statuses": {"validation": 400, "not_found": 404, "conflict": 409, "unsupported_media": 415},
        "codes": {
            "validation": None,
            "not_found": None,
            "conflict": None,
            "malformed_body": None,
            "forbidden": None,
        },
        "assert_messages": False,
        "messages": {},
        "unknown_fields": "unknown",
    },
    "tenant": {"model": "none", "param": None, "cross_tenant_status": 404, "actor_other": None},
    "auth_matrix": [],
    "conflicts": {},
    "state_machines": {},
    "exclude": [],
    "tests": {
        "indexer": None,
        "globs": ["**/src/test/**/*.kt", "**/src/test/**/*.java"],
        "exclude_classes": ["*TestBase", "*Support"],
    },
}


@dataclass(frozen=True, slots=True)
class Profile:
    version: int
    name: str
    service_path: str | None
    stack: str | None
    auth: dict
    actors: tuple
    error: dict
    tenant: dict
    auth_matrix: tuple
    conflicts: dict
    state_machines: dict
    exclude: tuple
    tests: dict


_TUPLE_KEYS = ("actors", "auth_matrix", "exclude")


def _merge(base, over):
    for key, val in over.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _merge(base[key], val)
        else:
            base[key] = copy.deepcopy(val)
    return base


def resolve(raw):
    merged = _merge(copy.deepcopy(DEFAULTS), raw or {})
    for key in _TUPLE_KEYS:
        merged[key] = tuple(merged[key])
    return Profile(**{k: merged[k] for k in Profile.__dataclass_fields__})


_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"})


def match_op(pattern, method, path):
    pattern = pattern.strip()
    if pattern == "*":
        return True
    head, _, rest = pattern.partition(" ")
    if head in _METHODS:
        if method.upper() != head:
            return False
        pattern = rest.strip()
    regex = ".*".join(re.escape(chunk) for chunk in pattern.split("*"))
    return re.fullmatch(regex, path) is not None


def is_excluded(profile, op):
    return any(match_op(p, op.method, op.path) for p in profile.exclude)


_VALIDATION_KINDS = frozenset({
    "REQUIRED_MISSING", "LENGTH_INVALID", "PATTERN_INVALID", "RANGE_INVALID", "ENUM_INVALID",
    "ARRAY_BOUNDS", "FORMAT_INVALID", "TYPE_INVALID", "UNKNOWN_FIELD", "INVALID_QUERY_PARAM",
    "INVALID_ID_FORMAT", "EMPTY_BODY", "RESOURCE_LIMIT", "READONLY_SENT", "MASS_ASSIGNMENT",
})
_CODE_KEY = {
    "NOT_FOUND": "not_found", "DUPLICATE": "conflict", "STATE_CONFLICT": "conflict",
    "FORBIDDEN_PERMISSION": "forbidden",
}


def _code_key(case):
    kind = case["kind"]
    if kind in _VALIDATION_KINDS:
        return "validation"
    if kind == "MALFORMED_BODY":
        return "malformed_body"
    if kind == "CROSS_TENANT":
        return "not_found" if case["expected"]["status"] == 404 else "forbidden"
    return _CODE_KEY.get(kind)


def _is_4xx(status):
    return isinstance(status, int) and not isinstance(status, bool) and 400 <= status < 500


def _constraints(op, name):
    if op is None:
        return {}
    for f in (op.body.fields if op.body else ()):
        if f.path == name:
            return f.constraints
    for p in op.params:
        if p.name == name:
            return p.field.constraints
    return {}


def _fill_messages(case, op, messages):
    keyword = case["rule"].split(".")[0]
    template = messages.get(keyword)
    if template is None:
        return
    for violation in case["expected"]["violations"]:
        value = _constraints(op, violation.get("field")).get(keyword)
        violation["message"] = template.replace("{n}", str(value))


def _fill_expected(case, op, profile):
    expected = case["expected"]
    if case["negative"] and _is_4xx(expected["status"]):
        key = _code_key(case)
        codes = profile.error["codes"]
        code = codes.get(key)
        if code is None and key == "malformed_body":
            code = codes.get("validation")
        expected["code"] = code
    if case["rule"] in ("auth.missing", "auth.malformed"):
        body = profile.auth[case["rule"].split(".")[1]]["body"]
        expected["body"] = copy.deepcopy(body)
    if profile.error["assert_messages"]:
        _fill_messages(case, op, profile.error["messages"])


def _unknown_field_cases(spec, graph, profile, present):
    from . import derive

    owner = derive.graph_mod.op_owner(graph)
    out = []
    for op in spec.operations:
        body = op.body
        if is_excluded(profile, op) or body is None or body.root_type != "object":
            continue
        if body.additional_properties is False:
            continue
        entity_id, needs = derive.case_context(spec, graph, op, owner)
        cid = derive.case_id(entity_id, op.operation_id, "body", None, "additionalProperties.unknown")
        if cid in present:
            continue
        status, _ = derive.expected_status(op, profile, valid=False)
        out.append(derive.make_case(
            id=cid, title=f"{op.method} {op.path} rejects body: additionalProperties.unknown",
            operation={"method": op.method, "path": op.path, "operationId": op.operation_id},
            kind="UNKNOWN_FIELD", loc="body", rule="additionalProperties.unknown", negative=True,
            technique="error-guess", priority="P2", source="profile", specRef=body.spec_ref,
            needs=needs, input={"body": {"__unexpected_field__": "x"}},
            expected={"status": status, "violations": []}, tags=["profile"]))
    return out


def apply(cases, spec, graph, profile, scope=None):
    from . import derive

    out = copy.deepcopy(list(cases))
    if profile.error["unknown_fields"] == "reject":
        out += _unknown_field_cases(spec, graph, profile, {c["id"] for c in out})
    ops = {o.operation_id: o for o in spec.operations}
    out = [c for c in out if derive.in_scope(c, scope)]
    for case in out:
        _fill_expected(case, ops.get(case["operation"]["operationId"]), profile)
    return out


def _profile_case(derive, op, entity_id, needs, *, kind, rule, technique, priority, status, label,
                  field=None, actor=None, body=None):
    return derive.make_case(
        id=derive.case_id(entity_id, op.operation_id, "op", field, rule),
        title=f"{op.method} {op.path} {label}",
        operation={"method": op.method, "path": op.path, "operationId": op.operation_id},
        kind=kind, loc="op", field=field, rule=rule, negative=True, technique=technique,
        priority=priority, source="profile", specRef=op.spec_ref, needs=needs, actor=actor,
        input={"body": body} if body else {}, expected={"status": status}, tags=["profile"])


def _state_pairs(states):
    targets = []
    for src, dests in states.items():
        for name in (src, *dests):
            if name not in targets:
                targets.append(name)
    return [(src, dst) for src in states for dst in targets
            if dst != src and dst not in states[src]]


def profile_cases(spec, graph, profile):
    from . import derive

    owner = derive.graph_mod.op_owner(graph)
    entities = {e.id: e for e in graph.entities}
    conflict = profile.error["statuses"]["conflict"]
    tenant = profile.tenant
    cross = tenant["model"] != "none" and tenant["actor_other"]
    out = []
    seen = set()

    def add(case):
        if case["id"] not in seen:
            seen.add(case["id"])
            out.append(case)

    ops = [o for o in spec.operations if not is_excluded(profile, o)]
    for op in ops:
        entity_id, needs = derive.case_context(spec, graph, op, owner)
        make = lambda **kw: _profile_case(derive, op, entity_id, needs, **kw)  # noqa: E731
        for row in profile.auth_matrix:
            if match_op(row["ops"], op.method, op.path):
                add(make(
                    kind="FORBIDDEN_PERMISSION", rule=f"matrix.{row['actor']}", technique="auth-matrix",
                    priority="P1", status=row.get("expect", 403), actor=row["actor"],
                    label=f"forbids {row['actor']}"))
        item_path = entities[entity_id].item_path
        if cross and item_path and op.path.startswith(item_path):
            add(make(
                kind="CROSS_TENANT", rule="tenant.cross", technique="owasp-api1", priority="P1",
                status=tenant["cross_tenant_status"], actor=tenant["actor_other"],
                label="denies another tenant's resource"))
        for pattern, fields in profile.conflicts.items():
            if match_op(pattern, op.method, op.path):
                for name in fields:
                    add(make(
                        kind="DUPLICATE", rule=f"conflict.{name}", technique="error-guess",
                        priority="P2", status=conflict, field=name, label=f"rejects duplicate {name}"))

    by_id = {o.operation_id: o for o in ops}
    for entity_id, sm in profile.state_machines.items():
        op = by_id.get(sm["transition_op"])
        if entity_id not in entities or op is None:
            continue
        owner_id, needs = derive.case_context(spec, graph, op, owner)
        for src, dst in _state_pairs(sm["states"]):
            add(_profile_case(
                derive, op, owner_id, needs, kind="STATE_CONFLICT", rule=f"state.{src}_to_{dst}",
                technique="state-transition", priority="P1", status=conflict, field=sm["field"],
                body={sm["field"]: dst}, label=f"rejects {src} to {dst}"))
    return out
