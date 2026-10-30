import copy
import dataclasses
import hashlib
import re
from dataclasses import dataclass
from typing import NamedTuple

CONSTRAINT_KEYS = (
    "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "multipleOf", "pattern", "enum", "minItems", "maxItems", "uniqueItems", "default", "example",
    "additionalProperties",
)

MAX_DEPTH = 8
_ADDITIONAL_PROP = re.compile(r"^additionalProp\d+$")
_NOT_KEYWORDS = frozenset({"$ref", "allOf", "oneOf", "anyOf", "properties", "required", "items"})


@dataclass(frozen=True, slots=True)
class Field:
    path: str
    name: str
    type: str | None
    format: str | None
    required: bool
    nullable: bool
    read_only: bool
    write_only: bool
    constraints: dict
    schema_ref: str | None
    spec_ref: str
    description: str
    truncated: bool


@dataclass(frozen=True, slots=True)
class Param:
    name: str
    location: str
    required: bool
    field: Field
    spec_ref: str


@dataclass(frozen=True, slots=True)
class Body:
    content_types: tuple[str, ...]
    media: str
    required: bool
    schema_name: str | None
    root_type: str
    additional_properties: bool | None
    fields: tuple[Field, ...]
    spec_ref: str


@dataclass(frozen=True, slots=True)
class Security:
    secured: bool
    schemes: tuple[str, ...]
    header_param: bool
    optional: bool


@dataclass(frozen=True, slots=True)
class Response:
    status: str
    description: str
    schema_name: str | None
    content_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Operation:
    method: str
    path: str
    operation_id: str
    op_id_synthesized: bool
    spec_ref: str
    tags: tuple[str, ...]
    summary: str
    description: str
    params: tuple[Param, ...]
    body: Body | None
    security: Security
    responses: tuple[Response, ...]
    unsupported: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Spec:
    source: str
    sha256: str
    version: str
    title: str
    server_path: str | None
    operations: tuple[Operation, ...]
    schemas: dict
    security_schemes: dict
    warnings: tuple[str, ...]


class FieldWalk(NamedTuple):
    fields: tuple
    unsupported: tuple
    warnings: tuple
    root_type: str
    additional_properties: bool | None
    schema_name: str | None


def _token(name):
    return str(name).replace("~", "~0").replace("/", "~1")


def _untoken(token):
    return token.replace("~1", "/").replace("~0", "~")


class _View:
    """A schema after $ref resolution and allOf merging."""

    def __init__(self):
        self.ref_name = None
        self.refs = []
        self.props = {}  # name -> (schema, pointer, containing component)
        self.required = []
        self.kw = {}
        self.items = None  # (schema, pointer, component)
        self.combos = []  # (kind, pointer)
        self.issues = []  # (kind, pointer, detail)
        self.broken = False  # own $ref chain could not be followed


def _lookup(doc, ref):
    node = doc
    for token in ref[2:].split("/") if ref != "#" else []:
        token = _untoken(token)
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            return None
    return node


def _view(doc, schema, ptr, comp, chain):
    view = _View()
    if not isinstance(schema, dict):
        schema = {}
    chain = tuple(chain)
    while "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str) or not (ref == "#" or ref.startswith("#/")):
            view.issues.append(("external", ptr, str(ref)))
            view.broken = True
            return view
        if ref in chain:
            view.issues.append(("recursion", ptr, ref))
            view.broken = True
            return view
        target = _lookup(doc, ref)
        if not isinstance(target, dict):
            view.issues.append(("unresolved", ptr, ref))
            view.broken = True
            return view
        chain += (ref,)
        view.refs.append(ref)
        ptr, comp = ref, _untoken(ref.rsplit("/", 1)[-1])
        view.ref_name = comp
        schema = target

    def absorb(sub):
        for name, entry in sub.props.items():
            view.props[name] = entry
        for name in sub.required:
            if name not in view.required:
                view.required.append(name)
        view.kw.update(sub.kw)
        if sub.items is not None:
            view.items = sub.items
        view.combos.extend(sub.combos)
        view.issues.extend(sub.issues)

    branches = schema.get("allOf")
    for i, branch in enumerate(branches if isinstance(branches, list) else []):
        absorb(_view(doc, branch, f"{ptr}/allOf/{i}", comp, chain))

    own = _View()
    props = schema.get("properties")
    for name, val in (props.items() if isinstance(props, dict) else []):
        own.props[name] = (val, f"{ptr}/properties/{_token(name)}", comp)
    req = schema.get("required")
    own.required = [r for r in req if isinstance(r, str)] if isinstance(req, list) else []
    own.kw = {k: v for k, v in schema.items() if k not in _NOT_KEYWORDS}
    if isinstance(schema.get("items"), dict):
        own.items = (schema["items"], f"{ptr}/items", comp)
    for kind in ("oneOf", "anyOf"):
        if kind in schema:
            own.combos.append((kind, ptr))
    absorb(own)
    return view


def _first_type(kw):
    t = kw.get("type")
    if isinstance(t, list):
        return next((x for x in t if isinstance(x, str) and x != "null"), None)
    return t if isinstance(t, str) else None


def _constraints(kw):
    out = {}
    for key in CONSTRAINT_KEYS:
        if key == "additionalProperties":
            if kw.get(key) is False:
                out[key] = False
            continue
        if key in ("minimum", "maximum"):
            if isinstance(kw.get("exclusive" + key.capitalize()), bool) and kw["exclusive" + key.capitalize()]:
                continue
        if key in ("exclusiveMinimum", "exclusiveMaximum"):
            flag = kw.get(key)
            if isinstance(flag, bool):
                base = key[len("exclusive"):].lower()
                if flag and base in kw:
                    out[key] = copy.deepcopy(kw[base])
                continue
        if key in kw:
            out[key] = copy.deepcopy(kw[key])
    return out


class _Walker:
    def __init__(self, doc):
        self.doc = doc
        self.fields = []
        self.unsupported = []
        self.warnings = []

    def note(self, unsupported=None, warning=None):
        if unsupported and unsupported not in self.unsupported:
            self.unsupported.append(unsupported)
        if warning and warning not in self.warnings:
            self.warnings.append(warning)

    def report_issues(self, view):
        for kind, ptr, detail in view.issues:
            if kind == "recursion":
                self.note(f"recursion at {ptr}")
            else:
                label = "external $ref" if kind == "external" else "unresolved $ref"
                self.note(f"{label} at {ptr}", f"{label} {detail} at {ptr} not resolved")

    def walk_props(self, view, prefix, stack, depth):
        for name, (val, ptr, comp) in view.props.items():
            if _ADDITIONAL_PROP.match(name):
                self.note(warning=f"dropped {name} at {ptr}")
                continue
            path = f"{prefix}.{name}" if prefix else name
            self.emit(path, name, val, ptr, comp, name in view.required, stack, depth)

    def emit(self, path, name, val, ptr, comp, required, stack, depth):
        view = _view(self.doc, val, ptr, comp, ())
        kw = view.kw
        truncated = view.broken
        self.report_issues(view)
        if not truncated:
            if any(r in stack for r in view.refs):
                truncated = True
                self.note(f"recursion at {ptr}")
            elif depth > MAX_DEPTH:
                truncated = True
                self.note(f"depth cap at {ptr}")

        nullable = (
            kw.get("nullable") is True or kw.get("x-nullable") is True
            or (isinstance(kw.get("type"), list) and "null" in kw["type"])
        )
        desc = kw.get("description")
        self.fields.append(Field(
            path=path, name=name, type=_first_type(kw),
            format=kw["format"] if isinstance(kw.get("format"), str) else None,
            required=required, nullable=nullable,
            read_only=kw.get("readOnly") is True, write_only=kw.get("writeOnly") is True,
            constraints=_constraints(kw),
            schema_ref=view.ref_name or comp, spec_ref=ptr,
            description=desc if isinstance(desc, str) else "", truncated=truncated,
        ))
        if truncated:
            return
        for kind, cptr in view.combos:
            self.note(f"{kind} at {cptr}")
        if view.combos:
            return
        inner = stack + tuple(view.refs)
        if view.props:
            self.walk_props(view, path, inner, depth + 1)
        if view.items is not None or _first_type(kw) == "array":
            items, iptr, icomp = view.items if view.items is not None else ({}, f"{ptr}/items", comp)
            self.emit(f"{path}[]", f"{name}[]", items, iptr, icomp, False, inner, depth + 1)


def walk_schema(doc, schema, spec_ref, prefix=""):
    walker = _Walker(doc)
    view = _view(doc, schema, spec_ref, None, ())
    walker.report_issues(view)
    kw = view.kw
    root_type = _first_type(kw) or ("object" if view.props else "array" if view.items is not None else "")
    additional = False if kw.get("additionalProperties") is False else None
    if view.combos:
        for kind, cptr in view.combos:
            walker.note(f"{kind} at {cptr}")
    elif root_type != "array":
        walker.walk_props(view, prefix, tuple(view.refs), 1)
    return FieldWalk(
        tuple(walker.fields), tuple(walker.unsupported), tuple(walker.warnings),
        root_type, additional, view.ref_name,
    )


METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
_DEFAULT_FORM_MEDIA = "application/x-www-form-urlencoded"


def _ref_name(schema):
    ref = schema.get("$ref") if isinstance(schema, dict) else None
    if isinstance(ref, str) and ref.startswith("#/"):
        return _untoken(ref.rsplit("/", 1)[-1])
    return None


def _resolve(doc, node, ptr):
    """Follow a local $ref chain; returns (node, pointer) or (None, ptr) when unresolvable."""
    seen = set()
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/") or ref in seen:
            return None, ptr
        seen.add(ref)
        node, ptr = _lookup(doc, ref), ref
    return (node if isinstance(node, dict) else None), ptr


def _synth_id(method, path):
    segs = [s for s in path.split("/") if s]
    parts = []
    for seg in segs:
        if seg.startswith("{") and seg.endswith("}"):
            continue
        parts.extend(p[:1].upper() + p[1:] for p in re.split(r"[^A-Za-z0-9]+", seg) if p)
    by_id = bool(segs) and segs[-1].startswith("{") and segs[-1].endswith("}")
    return method.lower() + "".join(parts) + ("ById" if by_id else "")


class _Collector:
    def __init__(self):
        self.unsupported = []
        self.warnings = []

    def absorb(self, unsupported, warnings):
        for u in unsupported:
            if u not in self.unsupported:
                self.unsupported.append(u)
        for w in warnings:
            if w not in self.warnings:
                self.warnings.append(w)


def _single_field(doc, path, name, val, ptr, required):
    w = _Walker(doc)
    w.emit(path, name, val, ptr, None, required, (), 1)
    return w.fields[0], w.unsupported, w.warnings


def _params(doc, item, op, base, op_ptr):
    def collect(owner, owner_ptr):
        raw = owner.get("parameters")
        out = []
        for i, p in enumerate(raw if isinstance(raw, list) else []):
            node, ptr = _resolve(doc, p, f"{owner_ptr}/parameters/{i}")
            if node is not None:
                out.append((node, ptr))
        return out

    own = collect(op, op_ptr)
    taken = {(n.get("name"), n.get("in")) for n, _ in own}
    inherited = [(n, p) for n, p in collect(item, base) if (n.get("name"), n.get("in")) not in taken]
    return inherited + own


def _security(doc, op, header_required, header_param):
    eff = op["security"] if "security" in op else doc.get("security")
    reqs = [r for r in eff if isinstance(r, dict)] if isinstance(eff, list) else []
    schemes = sorted({name for r in reqs for name in r})
    return Security(
        secured=any(reqs) or header_required,
        schemes=tuple(schemes),
        header_param=header_param,
        optional=any(not r for r in reqs),
    )


def _responses(doc, op, swagger2):
    produces = op.get("produces", doc.get("produces")) if swagger2 else None
    out = []
    raw = op.get("responses")
    for status, resp in (raw.items() if isinstance(raw, dict) else []):
        node, _ = _resolve(doc, resp, "")
        node = node or {}
        if swagger2:
            schema_name = _ref_name(node.get("schema"))
            ctypes = tuple(produces) if isinstance(produces, list) else ()
        else:
            content = node.get("content")
            content = content if isinstance(content, dict) else {}
            pick = "application/json" if "application/json" in content else next(iter(sorted(content)), None)
            entry = content.get(pick) if pick else None
            schema_name = _ref_name(entry.get("schema")) if isinstance(entry, dict) else None
            ctypes = tuple(content)
        desc = node.get("description")
        out.append(Response(str(status), desc if isinstance(desc, str) else "", schema_name, ctypes))
    return tuple(out)


def _body(doc, op, path_params, op_ptr, swagger2, sink):
    if swagger2:
        consumes = op.get("consumes", doc.get("consumes"))
        consumes = tuple(c for c in consumes if isinstance(c, str)) if isinstance(consumes, list) else ()
        body_param = next(((n, p) for n, p in path_params if n.get("in") == "body"), None)
        if body_param:
            node, ptr = body_param
            media = consumes[0] if consumes else "application/json"
            walk = walk_schema(doc, node.get("schema", {}), f"{ptr}/schema")
            sink.absorb(walk.unsupported, walk.warnings)
            fields = walk.fields
            if walk.root_type == "array":
                sink.absorb((f"array body at {ptr}/schema",), ())
                fields = ()
            return Body(consumes or (media,), media, bool(node.get("required")), walk.schema_name,
                        walk.root_type, walk.additional_properties, fields, ptr)
        form = [(n, p) for n, p in path_params if n.get("in") == "formData"]
        if not form:
            return None
        media = consumes[0] if consumes else _DEFAULT_FORM_MEDIA
        fields = []
        for node, ptr in form:
            field, unsupported, warnings = _single_field(
                doc, node["name"], node["name"], node, ptr, bool(node.get("required")))
            sink.absorb(unsupported, warnings)
            fields.append(field)
        return Body(consumes or (media,), media, any(f.required for f in fields), None, "object",
                    None, tuple(fields), f"{op_ptr}/parameters")

    node, ptr = _resolve(doc, op.get("requestBody"), f"{op_ptr}/requestBody")
    if node is None:
        return None
    content = node.get("content")
    content = content if isinstance(content, dict) else {}
    media = "application/json" if "application/json" in content else next(iter(sorted(content)), "application/json")
    entry = content.get(media)
    schema = entry.get("schema", {}) if isinstance(entry, dict) else {}
    schema_ptr = f"{ptr}/content/{_token(media)}/schema"
    walk = walk_schema(doc, schema, schema_ptr)
    sink.absorb(walk.unsupported, walk.warnings)
    fields = walk.fields
    if walk.root_type == "array":
        sink.absorb((f"array body at {schema_ptr}",), ())
        fields = ()
    return Body(tuple(content) or (media,), media, bool(node.get("required")), walk.schema_name,
                walk.root_type, walk.additional_properties, fields, ptr)


def _build_op(doc, item, path, method, swagger2, warnings):
    base = f"#/paths/{_token(path)}"
    op = item[method]
    op_ptr = f"{base}/{method}"
    sink = _Collector()
    pairs = _params(doc, item, op, base, op_ptr)

    header_param = header_required = False
    params = []
    for node, ptr in pairs:
        loc = node.get("in")
        if loc in ("body", "formData") or not isinstance(node.get("name"), str):
            continue
        if loc == "header" and node["name"].lower() == "authorization":
            header_param = True
            header_required = header_required or bool(node.get("required"))
            continue
        required = bool(node.get("required")) or loc == "path"
        if swagger2:
            field, unsupported, warns = _single_field(doc, node["name"], node["name"], node, ptr, required)
        else:
            field, unsupported, warns = _single_field(
                doc, node["name"], node["name"], node.get("schema", {}), f"{ptr}/schema", required)
        sink.absorb(unsupported, warns)
        params.append(Param(node["name"], loc, required, field, ptr))

    body = _body(doc, op, pairs, op_ptr, swagger2, sink)
    tags = op.get("tags")
    given = op.get("operationId")
    synthesized = not (isinstance(given, str) and given)
    raw_id = _synth_id(method, path) if synthesized else given
    summary, desc = op.get("summary"), op.get("description")
    warnings.extend(sink.warnings)
    return Operation(
        method=method.upper(), path=path,
        operation_id=re.sub(r"[^A-Za-z0-9_]", "_", raw_id), op_id_synthesized=synthesized,
        spec_ref=op_ptr,
        tags=tuple(t for t in tags if isinstance(t, str)) if isinstance(tags, list) else (),
        summary=summary if isinstance(summary, str) else "",
        description=desc if isinstance(desc, str) else "",
        params=tuple(params), body=body,
        security=_security(doc, op, header_required, header_param),
        responses=_responses(doc, op, swagger2), unsupported=tuple(sink.unsupported),
    )


def _server_path(doc, swagger2):
    if swagger2:
        base = doc.get("basePath")
        base = base.rstrip("/") if isinstance(base, str) else ""
        return base or None
    servers = doc.get("servers")
    url = servers[0].get("url") if isinstance(servers, list) and servers and isinstance(servers[0], dict) else None
    if not isinstance(url, str):
        return None
    return re.sub(r"^[^:/?#]+://[^/]*", "", url) or None


def _dedupe_ids(ops, warnings):
    groups = {}
    for op in ops:
        groups.setdefault(op.operation_id, []).append(op)
    out = []
    for op in ops:
        if len(groups[op.operation_id]) > 1:
            tail = hashlib.sha1(f"{op.method} {op.path}".encode()).hexdigest()[:6]
            op = dataclasses.replace(op, operation_id=f"{op.operation_id}_{tail}")
        out.append(op)
    for oid in groups:
        if len(groups[oid]) > 1:
            warnings.append(f"duplicate operationId {oid}; suffixed every member")
    return out


def build_ir(doc, source, sha256):
    swagger2 = "swagger" in doc
    warnings = []
    ops = []
    paths = doc.get("paths")
    paths = paths if isinstance(paths, dict) else {}
    if not paths:
        warnings.append("no paths")
    for path, raw_item in paths.items():
        if str(path).startswith("x-"):
            continue
        item, _ = _resolve(doc, raw_item, "")
        if item is None:
            continue
        if "x-amazon-apigateway-any-method" in item:
            warnings.append(f"skipped x-amazon-apigateway-any-method at {path}")
        for method in METHODS:
            if isinstance(item.get(method), dict):
                ops.append(_build_op(doc, item, str(path), method, swagger2, warnings))
    ops = _dedupe_ids(ops, warnings)
    schemas = doc.get("definitions") if swagger2 else (doc.get("components") or {}).get("schemas")
    schemes = doc.get("securityDefinitions") if swagger2 else (doc.get("components") or {}).get("securitySchemes")
    info = doc.get("info")
    title = info.get("title") if isinstance(info, dict) else None
    return Spec(
        source=source, sha256=sha256, version=str(doc.get("swagger") or doc.get("openapi") or ""),
        title=title if isinstance(title, str) else "",
        server_path=_server_path(doc, swagger2), operations=tuple(ops),
        schemas=schemas if isinstance(schemas, dict) else {},
        security_schemes=schemes if isinstance(schemes, dict) else {},
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _plain(obj):
    if dataclasses.is_dataclass(obj):
        return {f.name: _plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [_plain(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    return obj


def to_dict(spec):
    return _plain(spec)
