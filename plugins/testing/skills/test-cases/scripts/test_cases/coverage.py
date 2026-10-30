import re

KIND_EQUIV = {
    "INVALID_QUERY_PARAM": frozenset({
        "LENGTH_INVALID", "RANGE_INVALID", "PATTERN_INVALID", "ENUM_INVALID",
        "FORMAT_INVALID", "TYPE_INVALID", "REQUIRED_MISSING",
    }),
}

_BRACES = re.compile(r"\{[^}]*\}")
_KEYWORD_LOCS = ("body", "path", "query", "header")


def norm_path(p):
    return _BRACES.sub("{}", p)


def _ref(path, line):
    return "%s:%d" % (path, line)


def _drift(type_, test=None, method=None, path=None, status=None, detail=None):
    return {"type": type_, "test": test, "method": method, "path": path,
            "status": status, "detail": detail}


def _statuses(case):
    s = case["expected"]["status"]
    return s if isinstance(s, list) else [s]


def _kind_matches(case, kind):
    if case["kind"] == kind:
        return True
    return case["loc"] == "query" and kind in KIND_EQUIV.get(case["kind"], ())


def _matches(case, entry):
    op = case["operation"]
    return (
        op["method"].upper() == entry["method"]
        and norm_path(op["path"]) == entry["npath"]
        and _kind_matches(case, entry["kind"])
        and case["field"] == entry["field"]
        and entry["status"] in _statuses(case)
    )


def _raw_methods(raw):
    for f in raw.get("files", []):
        for m in f["methods"]:
            yield f, m


def _find_raw(raw, file, name, line):
    for f in raw.get("files", []):
        if f["path"] != file:
            continue
        for m in f["methods"]:
            if m["name"] == name and m["line"] <= line <= m["end_line"]:
                return f, m
        return f, None
    return None, None


def _entries(raw, llm, ops):
    out, drift = [], []
    for doc in llm:
        for t in doc["tests"]:
            f, m = _find_raw(raw, doc["file"], t["method"], t["line"])
            if f is not None and f.get("excluded"):
                continue
            e = {
                "ref": _ref(doc["file"], t["line"]),
                "method": t["http_method"].upper(),
                "path": t["path"],
                "npath": norm_path(t["path"]),
                "kind": t["kind"],
                "field": t["field"],
                "status": t["status"],
                "stub": m["stub"] if m is not None else None,
            }
            op = ops.get((e["method"], e["npath"]))
            if op is None:
                drift.append(_drift("unknown_endpoint", e["ref"], e["method"], e["path"], e["status"],
                                    "no such operation in spec"))
                continue
            e["op_key"] = op["key"]
            if str(e["status"]) not in op["documented"]:
                drift.append(_drift("undeclared_status", e["ref"], e["method"], op["path"], e["status"],
                                    "status not documented for %s" % op["key"]))
            out.append(e)
    return out, drift


def _raw_only(raw, ops):
    seen, drift = {}, []
    for f, m in _raw_methods(raw):
        if f.get("excluded") or m["stub"]:
            continue
        resolved = [c for c in m["calls"] if c["op"]]
        if not resolved:
            continue
        call = resolved[-1]
        verb, path = call["op"].split(" ", 1)
        op = ops[(verb, norm_path(path))]
        for s in m["statuses"]:
            seen.setdefault(op["key"], set()).add(str(s))
            if str(s) not in op["documented"]:
                drift.append(_drift("undeclared_status", _ref(f["path"], m["line"]), op["method"],
                                    op["path"], s, "status not documented for %s" % op["key"]))
    return seen, drift


def _ops_index(spec):
    ops = {}
    for o in spec.operations:
        documented = sorted(r.status for r in o.responses if len(r.status) == 3 and r.status.isdigit())
        ops[(o.method.upper(), norm_path(o.path))] = {
            "key": "%s %s" % (o.method.upper(), o.path), "method": o.method.upper(),
            "path": o.path, "documented": documented, "operation_id": o.operation_id,
        }
    return ops


def _operations(ops, cases, case_cov, seen):
    out = {}
    for op in ops.values():
        key, documented = op["key"], op["documented"]
        mine = [c for c in cases if c["operation"]["operationId"] == op["operation_id"]]
        kw = [c for c in mine if c["loc"] in _KEYWORD_LOCS]
        au = [c for c in mine if c["loc"] == "auth"]
        gone = lambda c: case_cov[c["id"]]["status"] != "covered"  # noqa: E731
        out[key] = {
            "status_codes": {"documented": documented,
                             "covered": [s for s in documented if s in seen.get(key, ())]},
            "keywords": {"total": len(kw), "covered": sum(not gone(c) for c in kw),
                         "missing": [c["id"] for c in kw if gone(c)]},
            "auth": {"total": len(au), "covered": sum(not gone(c) for c in au),
                     "missing": [c["rule"] for c in au if gone(c)]},
        }
    return out


def diff(cases, spec, raw, llm):
    ops = _ops_index(spec)
    case_cov = {c["id"]: {"status": "gap", "tests": []} for c in cases}
    drift, unattributed, seen = [], [], {}

    if llm is None:
        mode = "raw-only"
        seen, drift = _raw_only(raw, ops)
    else:
        mode = "full"
        entries, drift = _entries(raw, llm, ops)
        hits = {c["id"]: ([], []) for c in cases}
        for e in entries:
            matched = False
            for c in cases:
                if _matches(c, e):
                    hits[c["id"]][1 if e["stub"] else 0].append(e["ref"])
                    matched = True
            if not matched:
                unattributed.append({"test": e["ref"], "method": e["method"], "path": e["path"],
                                     "status": e["status"]})
            if not e["stub"]:
                seen.setdefault(e["op_key"], set()).add(str(e["status"]))
        for cid, (real, stubs) in hits.items():
            if real:
                case_cov[cid] = {"status": "covered", "tests": sorted(set(real))}
            elif stubs:
                case_cov[cid] = {"status": "stub", "tests": sorted(set(stubs))}

    stubs = [{"test": _ref(f["path"], m["line"]), "reason": m["stub"]}
             for f, m in _raw_methods(raw) if not f.get("excluded") and m["stub"]]
    drift += [_drift("unused_path_constant", detail=name) for name in raw.get("unused_path_constants", [])]
    drift.sort(key=lambda d: (d["type"], d["test"] or "", d["detail"] or ""))
    unattributed.sort(key=lambda u: (u["test"], u["status"]))

    return {
        "version": 1,
        "mode": mode,
        "cases": case_cov,
        "operations": _operations(ops, cases, case_cov, seen),
        "test_drift": drift,
        "stubs": sorted(stubs, key=lambda s: s["test"]),
        "unattributed": unattributed,
    }
