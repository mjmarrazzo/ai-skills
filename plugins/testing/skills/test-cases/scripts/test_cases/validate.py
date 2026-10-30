import re

FAULT_EXEMPT_KINDS = frozenset({
    "FORBIDDEN_PERMISSION", "CROSS_TENANT", "DUPLICATE",
    "STATE_CONFLICT", "LIFECYCLE", "DELETE_TWICE",
})
FIELD_INJECTING_KINDS = frozenset({"UNKNOWN_FIELD", "MASS_ASSIGNMENT"})
SOURCES = ("spec", "profile", "llm")
_LOCATION_KEYS = (("path", "path"), ("query", "query"), ("headers", "header"))


def _is_placeholder(value):
    return isinstance(value, str) and value.startswith("<<") and value.endswith(">>")


def _leaves(body):
    if isinstance(body, dict) and body:
        return sum(_leaves(v) for v in body.values())
    return 1


def fault_count(case):
    inp = case.get("input") or {}
    mode = inp.get("body_mode", "merge")
    body = inp.get("body")
    faults = _leaves(body) if body else 0
    faults += len(inp.get("remove") or [])
    faults += sum(len(inp.get(k) or {}) for k in ("path", "query", "headers"))
    faults += case.get("auth", "valid") != "valid"
    faults += mode != "merge"
    faults += bool(inp.get("content_type"))
    return faults


def body_paths(body):
    out = []

    def walk(node, prefix):
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            path = f"{prefix}{key}"
            if isinstance(value, dict) and value:
                walk(value, path + ".")
            elif isinstance(value, list):
                out.append(path + "[]")
                for item in value:
                    if isinstance(item, dict) and item:
                        walk(item, path + "[].")
            else:
                out.append(path)

    walk(body, "")
    seen = set()
    return [p for p in out if not (p in seen or seen.add(p))]


def _valid_status(status):
    def is_int(v):
        return isinstance(v, int) and not isinstance(v, bool)

    if isinstance(status, list):
        return bool(status) and all(is_int(v) for v in status)
    return is_int(status)


def _case_errors(case, ops):
    errs = []
    op = case.get("operation") or {}
    op_id = op.get("operationId")
    if not case.get("specRef"):
        errs.append("missing specRef")
    if case.get("source") not in SOURCES:
        errs.append(f"invalid source {case.get('source')!r}")
    if not op_id:
        errs.append("missing operation.operationId")
    if not _valid_status((case.get("expected") or {}).get("status")):
        errs.append("expected.status must be an int or a non-empty list of ints")

    if (case.get("negative") and case.get("source") == "spec"
            and case.get("kind") not in FAULT_EXEMPT_KINDS):
        n = fault_count(case)
        if n != 1:
            errs.append(f"faults={n} (want 1)")

    if op_id:
        spec_op = ops.get(op_id)
        if spec_op is None:
            errs.append(f"unknown operation {op_id}")
        else:
            errs.extend(_field_errors(case, spec_op))
    return errs


def _field_errors(case, op):
    errs = []
    inp = case.get("input") or {}
    known = {f.path for f in op.body.fields} if op.body else set()
    injecting = case.get("kind") in FIELD_INJECTING_KINDS
    paths = body_paths(inp.get("body"))
    for path in paths:
        if injecting and any(other.startswith(path + ".") for other in paths):
            continue
        if injecting and path in known:
            errs.append(f"injected body path {path} exists in spec")
        elif not injecting and path not in known:
            errs.append(f"body path {path} not in spec")
    for path in inp.get("remove") or []:
        if path not in known:
            errs.append(f"remove path {path} not in spec")
    for key, loc in _LOCATION_KEYS:
        names = {p.name for p in op.params if p.location == loc}
        for name in inp.get(key) or {}:
            if name not in names:
                errs.append(f"{key} key {name} not a {loc} param")
    return errs


def invariants(cases, spec):
    ops = {o.operation_id: o for o in spec.operations}
    errors = []
    counts = {}
    for case in cases:
        cid = case.get("id", "<no id>")
        counts[cid] = counts.get(cid, 0) + 1
        errors.extend(f"{cid}: {msg}" for msg in _case_errors(case, ops))
    errors.extend(f"{cid}: duplicate id" for cid, n in counts.items() if n > 1)
    return sorted(errors)


_KEYWORDS = frozenset({
    "type", "enum", "const", "required", "properties", "additionalProperties", "items",
    "minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum", "pattern", "$ref",
})
_ANNOTATIONS = frozenset({
    "$schema", "$id", "$defs", "$comment", "title", "description", "default", "examples",
})
_SCHEMA_MAPS = ("properties", "$defs")
_SCHEMA_VALUES = ("items", "additionalProperties")


def _esc(token):
    return str(token).replace("~", "~0").replace("/", "~1")


def assert_supported(schema, ptr=""):
    if not isinstance(schema, dict):
        return
    for kw, value in schema.items():
        if kw not in _KEYWORDS and kw not in _ANNOTATIONS:
            raise ValueError(f"unsupported keyword {kw} at {ptr or '/'}")
        if kw in _SCHEMA_MAPS and isinstance(value, dict):
            for name, sub in value.items():
                assert_supported(sub, f"{ptr}/{kw}/{_esc(name)}")
        elif kw in _SCHEMA_VALUES:
            assert_supported(value, f"{ptr}/{kw}")


def _is_type(value, name):
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    return {
        "string": isinstance(value, str), "array": isinstance(value, list),
        "object": isinstance(value, dict), "null": value is None,
    }[name]


def _same(a, b):
    return a == b and isinstance(a, bool) == isinstance(b, bool)


def _resolve(root, ref):
    prefix = "#/$defs/"
    if not ref.startswith(prefix) or ref[len(prefix):] not in root.get("$defs", {}):
        raise ValueError(f"unsupported $ref {ref}")
    return root["$defs"][ref[len(prefix):]]


def _validate(value, schema, root, ptr, errs):
    if "$ref" in schema:
        _validate(value, _resolve(root, schema["$ref"]), root, ptr, errs)
        return
    here = ptr or "/"
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, n) for n in names):
            errs.append(f"{here}: expected {' or '.join(names)}")
            return
    if "enum" in schema and not any(_same(value, v) for v in schema["enum"]):
        errs.append(f"{here}: {value!r} not in enum")
    if "const" in schema and not _same(value, schema["const"]):
        errs.append(f"{here}: expected const {schema['const']!r}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append(f"{here}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(f"{here}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{here}: does not match {schema['pattern']}")
    if _is_type(value, "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{here}: below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{here}: above maximum {schema['maximum']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append(f"{here}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"{here}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                _validate(item, schema["items"], root, f"{ptr}/{i}", errs)
    if isinstance(value, dict):
        for key in schema.get("required", ()):
            if key not in value:
                errs.append(f"{ptr}/{_esc(key)}: required property missing")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            sub = f"{ptr}/{_esc(key)}"
            if key in props:
                _validate(item, props[key], root, sub, errs)
            elif extra is False:
                errs.append(f"{sub}: additional property not allowed")
            elif isinstance(extra, dict):
                _validate(item, extra, root, sub, errs)


def check(instance, schema):
    assert_supported(schema)
    errs = []
    _validate(instance, schema, schema, "", errs)
    return sorted(errs)


def _op_index(spec):
    refs = {}
    ops = {}
    for op in spec.operations:
        ops[op.operation_id] = op
        refs[op.spec_ref] = op.description
        fields = [*(op.body.fields if op.body else ()), *(p.field for p in op.params)]
        for f in fields:
            refs[f.spec_ref] = f.description
    return ops, refs


def _body_errors(where, body, op):
    probe = {"kind": "LLM", "input": {"body": body}}
    return [f"{where}: {m}" for m in _field_errors(probe, op)]


def semantic_enrich(doc, spec):
    from test_cases import derive, graph as graph_mod, profile

    g = graph_mod.build_graph(spec)
    ops, refs = _op_index(spec)
    errs = []

    def known_op(where, op_id):
        if op_id in ops:
            return ops[op_id]
        errs.append(f"{where}: unknown operationId {op_id}")
        return None

    if doc.get("entity") not in g.order:
        errs.append(f"unknown entity {doc.get('entity')}")
    for i, item in enumerate(doc.get("canonical", ())):
        op = known_op(f"canonical/{i}", item["operationId"])
        if op:
            body = (item.get("request") or {}).get("body")
            errs.extend(_body_errors(f"canonical/{i}", body, op))
    for i, m in enumerate(doc.get("id_mapping", ())):
        if m["entity"] not in g.order:
            errs.append(f"id_mapping/{i}: unknown entity {m['entity']}")
        known_op(f"id_mapping/{i}", m["create"])
    for i, sample in enumerate(doc.get("pattern_samples", ())):
        owner = sample["specRef"].removesuffix("/pattern")
        if owner not in refs:
            errs.append(f"pattern_samples/{i}: unknown specRef {sample['specRef']}")

    taken = {c["id"] for c in derive.derive(spec, g, profile.resolve(None))}
    for i, case in enumerate(doc.get("cases", ())):
        where = f"cases/{i}"
        if case["id"] in taken:
            errs.append(f"{where}: id {case['id']} collides with a spec-derived case")
        op = known_op(where, case["operation"]["operationId"])
        if op:
            errs.extend(f"{where}: {m}" for m in _field_errors(case, op))
        owner = case["specRef"].removesuffix("/description")
        if owner not in refs:
            errs.append(f"{where}: unknown specRef {case['specRef']}")
        elif case["quote"] not in refs[owner]:
            errs.append(f"{where}: quote not found in description at {case['specRef']}")
    return sorted(errs)


def semantic_index(doc, raw):
    files = {f["path"]: f for f in raw.get("files", ())}
    entry = files.get(doc["file"])
    if entry is None:
        return [f"file {doc['file']} not in raw index"]
    methods = {}
    for m in entry["methods"]:
        methods.setdefault(m["name"], []).append(m)
    errs = []
    for i, t in enumerate(doc["tests"]):
        found = methods.get(t["method"])
        if not found:
            errs.append(f"tests/{i}: method {t['method']} not in {doc['file']}")
        elif not any(m["line"] <= t["line"] <= m["end_line"] for m in found):
            errs.append(f"tests/{i}: line {t['line']} outside method {t['method']}")
    return sorted(errs)
