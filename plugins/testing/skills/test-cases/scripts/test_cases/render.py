import json
import re
from collections import Counter

from test_cases import ENGINE, graph, rules, yamlfmt

_SHAPE_KEYS = ("code_key", "violations_key", "field_key", "message_key")
_PRIORITIES = ("P1", "P2", "P3")
_BRACES = re.compile(r"\{[^}]*\}")


def cases_file(entity, cases, meta):
    doc = {
        "version": 1,
        "engine": ENGINE,
        "spec": meta["spec"],
        "profile": meta["profile"],
        "error_shape": {k: meta["error_shape"][k] for k in _SHAPE_KEYS},
        "entity": entity,
        "cases": cases,
    }
    return yamlfmt.dump(doc)


def graph_file(g):
    return yamlfmt.dump(graph.to_dict(g))


def json_file(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def entities_view(case_docs, ir_dict, graph_dict):
    ops = {o["operation_id"]: o for o in ir_dict["operations"]}
    cases_by_entity = {d["entity"]: d["cases"] for d in case_docs}
    out = []
    for ent in graph_dict["entities"]:
        cases = cases_by_entity.get(ent["id"], [])
        with_cases = {c["operation"]["operationId"] for c in cases}
        rows = []
        for op_id in (*ent["ops"].values(), *ent["actions"]):
            op = ops[op_id]
            rows.append({
                "operationId": op_id,
                "method": op["method"],
                "path": op["path"],
                "unsupported": list(op["unsupported"]),
                "excluded": op_id not in with_cases,
            })
        out.append({"id": ent["id"], "ops": rows, "cases": cases})
    return out


def _norm(path):
    return _BRACES.sub("{}", path)


def _missing(covered, total, missing):
    base = "%d/%d" % (covered, total)
    return "%s missing [%s]" % (base, ", ".join(missing)) if missing else base


def _op_row(op, cov_ops):
    key = "%s %s" % (op["method"], op["path"])
    cell = "`%s`" % key
    entry = cov_ops.get(key)
    if entry is None:
        return "| %s | - | - | - |" % cell
    sc = entry["status_codes"]
    documented = sc["documented"]
    covered = [s for s in documented if s in set(sc["covered"])]
    status = _missing(len(covered), len(documented), [s for s in documented if s not in set(covered)])
    kw, au = entry["keywords"], entry["auth"]
    return "| %s | %s | %s | %s |" % (
        cell, status,
        _missing(kw["covered"], kw["total"], kw["missing"]),
        _missing(au["covered"], au["total"], au["missing"]),
    )


def _kind_table(cases):
    counts = Counter((c["kind"], c["priority"]) for c in cases)
    lines = ["| Kind | P1 | P2 | P3 |", "|---|---|---|---|"]
    for kind in rules.KINDS:
        row = [counts[(kind, p)] for p in _PRIORITIES]
        if any(row):
            lines.append("| %s | %d | %d | %d |" % (kind, *row))
    return lines


def _section(title, items):
    return ["### " + title, "", *items, ""] if items else []


def _drift_lines(entity, drift):
    keys = {(op["method"], _norm(op["path"])) for op in entity["ops"]}
    return ["- %s `%s %s` %s at %s: %s" % (
        d["type"], d["method"], d["path"], d.get("status", ""), d["test"], d.get("detail", ""))
        for d in drift if (d["method"], _norm(d["path"])) in keys]


def report(entities, coverage):
    all_cases = [c for e in entities for c in e["cases"]]
    n_ops = sum(len(e["ops"]) for e in entities)
    prio = Counter(c["priority"] for c in all_cases)
    summary = "%d entities · %d operations · %d cases (P1 %d / P2 %d / P3 %d)" % (
        len(entities), n_ops, len(all_cases), *(prio[p] for p in _PRIORITIES))
    if coverage is not None:
        summary += " · coverage: %s" % coverage["mode"]
    lines = ["# Test cases", "", summary, ""]
    if not entities:
        lines += ["No operations found in spec.", ""]
    for e in entities:
        lines += ["## " + e["id"], ""]
        if coverage is not None:
            lines += ["| Operation | Status codes | Keywords | Auth |", "|---|---|---|---|"]
            lines += [_op_row(op, coverage["operations"]) for op in e["ops"]]
        else:
            lines += _kind_table(e["cases"])
        lines.append("")
        if coverage is not None:
            lines += _section("Drift", _drift_lines(e, coverage.get("test_drift", [])))
        lines += _section("Stubs", ["- " + c["id"] for c in e["cases"] if c["coverage"]["status"] == "stub"])
        lines += _section("Unsupported", ["- `%s`: %s" % (op["operationId"], u)
                                          for op in e["ops"] for u in op["unsupported"]])
        lines += _section("Excluded", ["- " + op["operationId"] for op in e["ops"] if op["excluded"]])
        lines += _section("Needs review", ["- " + c["id"] for c in e["cases"] if c["source"] == "llm"])
    return "\n".join(lines).rstrip("\n") + "\n"
