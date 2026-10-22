import copy
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
