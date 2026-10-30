import argparse
import sys
from pathlib import Path

from test_cases import coverage, derive, emit, graph as graph_mod, index, ir, load, profile, render, validate

_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE")
_SCHEMAS = {"cases": "case-file", "profile": "profile", "enrich": "enrich-output", "index": "index-output"}


class _Usage(Exception):
    pass


class _Failed(Exception):
    def __init__(self, lines):
        super().__init__("\n".join(lines))
        self.lines = list(lines)


class _Stats:
    def __init__(self):
        self.entities = self.ops = self.cases = 0
        self.warnings = []

    def warn(self, items):
        self.warnings.extend(items)


def _parser():
    p = argparse.ArgumentParser(prog="tc.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("parse")
    s.add_argument("spec")
    s.add_argument("-o", dest="out")

    s = sub.add_parser("graph")
    s.add_argument("spec")
    s.add_argument("-o", dest="out")

    s = sub.add_parser("derive")
    s.add_argument("spec")
    s.add_argument("--profile")
    s.add_argument("--entity")
    s.add_argument("--op")
    s.add_argument("-o", dest="out", default="./test-cases/")

    s = sub.add_parser("index")
    s.add_argument("root")
    s.add_argument("--spec", required=True)
    s.add_argument("--profile")
    s.add_argument("--indexer")
    s.add_argument("-o", dest="out")

    s = sub.add_parser("coverage")
    s.add_argument("--cases", required=True)
    s.add_argument("--spec", required=True)
    s.add_argument("--raw", required=True)
    s.add_argument("--index")
    s.add_argument("-o", dest="out")

    s = sub.add_parser("render")
    s.add_argument("--cases", required=True)
    s.add_argument("--coverage")

    s = sub.add_parser("validate")
    s.add_argument("--schema", required=True, choices=sorted(_SCHEMAS))
    s.add_argument("file")
    s.add_argument("--spec")
    s.add_argument("--raw")
    return p


def _emit(text, out):
    if out is None:
        sys.stdout.write(text)
    else:
        emit.write_text(out, text)


def _load_spec(path):
    doc = load.load_doc(path)
    return ir.build_ir(doc, path, load.sha256_file(path))


def _schema_errors(label, instance, schema_name):
    return [f"{label}:{e}" for e in validate.check(instance, load.load_schema(schema_name))]


def _entity_of(case):
    return case["id"].split(".")[0]


def _resolve_scope(args, spec, g):
    entities = ops = None
    if args.entity is not None:
        if args.entity not in g.order:
            raise _Usage(f"unknown entity {args.entity!r}; valid: {', '.join(sorted(g.order))}")
        entities = frozenset({args.entity})
    if args.op is not None:
        method, _, path = args.op.partition(" ")
        by_id = {o.operation_id: o for o in spec.operations}
        if method.upper() in _METHODS and path.startswith("/"):
            hit = [o.operation_id for o in spec.operations if o.method.upper() == method.upper() and o.path == path]
        else:
            hit = [args.op] if args.op in by_id else []
        if not hit:
            raise _Usage(f"unknown op {args.op!r}; valid: {', '.join(sorted(by_id))}")
        ops = frozenset(hit)
    scope = None if entities is None and ops is None else derive.Scope(entities, ops)
    owner = graph_mod.op_owner(g)
    in_scope = [e for e in g.order
                if (entities is None or e in entities) and (ops is None or any(owner.get(o) == e for o in ops))]
    return scope, in_scope


def _cmd_parse(args, st):
    spec = _load_spec(args.spec)
    st.ops = len(spec.operations)
    st.warn(spec.warnings)
    _emit(render.json_file(ir.to_dict(spec)), args.out)


def _cmd_graph(args, st):
    spec = _load_spec(args.spec)
    g = graph_mod.build_graph(spec)
    st.entities, st.ops = len(g.entities), len(spec.operations)
    st.warn((*spec.warnings, *g.warnings))
    _emit(render.graph_file(g), args.out)


def _cmd_derive(args, st):
    spec = _load_spec(args.spec)
    g = graph_mod.build_graph(spec)
    raw_profile = load.load_profile(args.profile)
    if raw_profile is not None:
        errs = _schema_errors(args.profile, raw_profile, "profile")
        if errs:
            raise _Failed(errs)
    prof = profile.resolve(raw_profile)
    scope, entity_ids = _resolve_scope(args, spec, g)
    cases = [*derive.derive(spec, g, prof, scope), *profile.profile_cases(spec, g, prof)]
    cases = [c for c in cases if derive.in_scope(c, scope)]
    cases = derive.order_cases(profile.apply(cases, spec, g, prof, scope), spec, g)
    st.entities, st.ops, st.cases = len(entity_ids), len(spec.operations), len(cases)
    st.warn((*spec.warnings, *g.warnings))
    errs = validate.invariants(cases, spec)
    if errs:
        raise _Failed([f"{e.split('.')[0]}.yaml:{e}" for e in errs])

    keys = prof.error["keys"]
    meta = {
        "spec": {"source": spec.source, "version": spec.version, "sha256": spec.sha256},
        "profile": {"name": prof.name, "source": args.profile},
        "error_shape": {
            "code_key": keys["code"], "violations_key": keys["violations"],
            "field_key": keys["field"], "message_key": keys["message"],
        },
    }
    files = {}
    for ent in entity_ids:
        files[f"{ent}.yaml"] = render.cases_file(ent, [c for c in cases if _entity_of(c) == ent], meta)
    files["graph.yaml"] = render.graph_file(g)
    files["ir.json"] = render.json_file(ir.to_dict(spec))
    emit.write_outputs(args.out, files)


def _cmd_index(args, st):
    spec = _load_spec(args.spec)
    prof = profile.resolve(load.load_profile(args.profile))
    st.ops = len(spec.operations)
    st.warn(spec.warnings)
    name = args.indexer or prof.tests["indexer"]
    rel = load.discover_tests(args.root, prof.tests["globs"], ())
    if not rel:
        raw = {"version": 1, "indexer": name, "path_constants": {}, "unused_path_constants": [], "files": []}
    else:
        indexer = index.select(name, rel)
        ctx = index.IndexContext(
            tuple((o.method.upper(), o.path) for o in spec.operations),
            prof.service_path or spec.server_path,
            tuple(prof.tests["exclude_classes"]),
        )
        raw = indexer.index(load.read_sources(args.root, rel), ctx)
    _emit(render.json_file(raw), args.out)


def _case_docs(directory):
    d = Path(directory)
    if not d.is_dir():
        raise load.LoadError(f"{directory}: not a directory")
    return [load.load_doc(p) for p in sorted(d.glob("*.yaml")) if p.name != "graph.yaml"]


def _cmd_coverage(args, st):
    spec = _load_spec(args.spec)
    g = graph_mod.build_graph(spec)
    docs = _case_docs(args.cases)
    raw = load.load_doc(args.raw)
    llm = None
    if args.index is not None:
        loaded = load.load_json(args.index)
        llm = loaded if isinstance(loaded, list) else [loaded]
        errs = []
        for i, item in enumerate(llm):
            found = _schema_errors(args.index, item, "index-output")
            errs.extend(found or [f"{args.index}:{e}" for e in validate.semantic_index(item, raw)])
        if errs:
            raise _Failed(errs)
    cases = [c for d in docs for c in d["cases"]]
    st.entities, st.ops, st.cases = len(docs), len(spec.operations), len(cases)
    st.warn((*spec.warnings, *g.warnings))
    cov = coverage.diff(cases, spec, raw, llm)
    out = args.out or str(Path(args.cases) / "coverage.json")
    emit.write_outputs(args.cases, {"README.md": render.report(
        render.entities_view(docs, ir.to_dict(spec), graph_mod.to_dict(g)), cov)})
    emit.write_text(out, render.json_file(cov))


def _cmd_render(args, st):
    d = Path(args.cases)
    docs = _case_docs(args.cases)
    ir_dict = load.load_doc(d / "ir.json")
    graph_dict = load.load_doc(d / "graph.yaml")
    cov = load.load_doc(args.coverage) if args.coverage else None
    st.entities, st.ops = len(graph_dict["entities"]), len(ir_dict["operations"])
    st.cases = sum(len(x["cases"]) for x in docs)
    emit.write_text(d / "README.md", render.report(render.entities_view(docs, ir_dict, graph_dict), cov))


def _cmd_validate(args, st):
    doc = load.load_doc(args.file)
    errs = _schema_errors(args.file, doc, _SCHEMAS[args.schema])
    if args.schema == "enrich" and args.spec is None:
        raise _Usage("--schema enrich requires --spec")
    if args.schema == "index" and args.raw is None:
        raise _Usage("--schema index requires --raw")
    if not errs:
        if args.schema == "cases" and args.spec:
            spec = _load_spec(args.spec)
            errs = [f"{args.file}:{e}" for e in validate.invariants(doc["cases"], spec)]
        elif args.schema == "enrich":
            errs = [f"{args.file}:{e}" for e in validate.semantic_enrich(doc, _load_spec(args.spec))]
        elif args.schema == "index":
            errs = [f"{args.file}:{e}" for e in validate.semantic_index(doc, load.load_doc(args.raw))]
    if errs:
        raise _Failed(errs)


_COMMANDS = {
    "parse": _cmd_parse, "graph": _cmd_graph, "derive": _cmd_derive, "index": _cmd_index,
    "coverage": _cmd_coverage, "render": _cmd_render, "validate": _cmd_validate,
}


def main(argv):
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    st = _Stats()
    try:
        _COMMANDS[args.cmd](args, st)
    except (load.LoadError, _Usage, LookupError) as e:
        print(e.args[0] if isinstance(e, LookupError) else e, file=sys.stderr)
        return 2
    except graph_mod.GraphError as e:
        print(f"{getattr(args, 'spec', '')}:/: GraphError: {e}", file=sys.stderr)
        return 1
    except _Failed as e:
        for line in e.lines:
            print(line, file=sys.stderr)
        return 1
    for w in st.warnings:
        print(f"warning: {w}", file=sys.stderr)
    print(f"entities={st.entities} ops={st.ops} cases={st.cases} warnings={len(st.warnings)}", file=sys.stderr)
    return 0
