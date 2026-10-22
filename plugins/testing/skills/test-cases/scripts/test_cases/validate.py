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
    for path in body_paths(inp.get("body")):
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
