import re
import warnings
from dataclasses import dataclass
from decimal import Decimal

KINDS = (
    "HAPPY_FULL", "HAPPY_MIN", "OPTIONAL_ABSENT", "REQUIRED_MISSING", "LENGTH_INVALID",
    "LENGTH_BOUNDARY_VALID", "PATTERN_INVALID", "RANGE_INVALID", "RANGE_BOUNDARY_VALID",
    "ENUM_INVALID", "ENUM_EACH_VALID", "ARRAY_BOUNDS", "CROSS_FIELD", "MALFORMED_BODY",
    "EMPTY_BODY", "DUPLICATE", "STATE_CONFLICT", "NOT_FOUND", "INVALID_ID_FORMAT",
    "AUTH_MISSING", "AUTH_INVALID", "AUTH_WRONG_TYPE", "FORBIDDEN_PERMISSION", "CROSS_TENANT",
    "PAGINATION", "INVALID_QUERY_PARAM", "SORT_FILTER", "CORS_VALID", "CORS_INVALID",
    "RATE_LIMIT", "ASYNC_ACCEPTED", "SIDE_EFFECT", "SMOKE",
    "FORMAT_INVALID", "TYPE_INVALID", "UNKNOWN_FIELD", "MASS_ASSIGNMENT", "READONLY_SENT",
    "WRONG_CONTENT_TYPE", "RESOURCE_LIMIT", "PUBLIC_REACHABLE", "LIFECYCLE", "DELETE_TWICE",
)
RESERVED_KINDS = (
    "CROSS_FIELD", "SORT_FILTER", "CORS_VALID", "CORS_INVALID", "RATE_LIMIT", "ASYNC_ACCEPTED",
    "SIDE_EFFECT", "SMOKE", "AUTH_WRONG_TYPE",
)
TECHNIQUES = (
    "ep", "bva-3", "error-guess", "state-transition", "auth-matrix", "lifecycle", "owasp-api1",
    "owasp-api3", "owasp-api4", "owasp-api5", "owasp-api7", "llm",
)

TYPE_WRONG = {
    "integer": (("string", "1"), ("float", 1.5), ("bool", True)),
    "number": (("string", "1.0"), ("bool", True)),
    "boolean": (("string", "true"), ("int", 1)),
    "string": (("int", 123),),
    "object": (("string", "x"),),
    "array": (("string", "x"),),
}
FORMAT_INVALID = {
    "date-time": (
        ("no_tz", "2026-01-01T00:00:00"), ("bad_month", "2026-13-01T00:00:00Z"),
        ("bad_day", "2026-02-30T00:00:00Z"), ("date_only", "2026-01-01"),
    ),
    "date": (("non_leap", "2023-02-29"), ("slashes", "2026/01/01"), ("us_order", "01-01-2026")),
    "uuid": (
        ("short", "123e4567-e89b-12d3-a456-42661417400"),
        ("long", "123e4567-e89b-12d3-a456-4266141740000"),
        ("non_hex", "123e4567-e89b-12d3-a456-42661417400g"),
        ("no_hyphens", "123e4567e89b12d3a456426614174000"),
    ),
    "email": (
        ("no_at", "user.example.test"), ("two_at", "a@b@example.test"),
        ("no_domain", "user@"), ("space", "us er@example.test"),
    ),
    "uri": (
        ("relative", "/relative/path"), ("javascript", "javascript:alert(1)"),
        ("internal_ip", "http://169.254.169.254/latest/meta-data/"),
    ),
    "url": (
        ("relative", "/relative/path"), ("javascript", "javascript:alert(1)"),
        ("internal_ip", "http://169.254.169.254/latest/meta-data/"),
    ),
}
FORMAT_P3 = {"format.no_hyphens"}
PATTERN_TRANSLATIONS = {
    "Alnum": ("[A-Za-z0-9]", "A-Za-z0-9"),
    "Alpha": ("[A-Za-z]", "A-Za-z"),
    "Digit": ("[0-9]", "0-9"),
    "Upper": ("[A-Z]", "A-Z"),
    "Lower": ("[a-z]", "a-z"),
    "Space": ("\\s", "\\s"),
    "Punct": ("[!-/:-@\\[-`{-~]", "!-/:-@\\[-`{-~"),
}
PROBE_CHARS = (" ", "!", "#", "%", "<", "é", "0", "a", "A")
PAGINATION_NAMES = ("cursor", "nextToken", "next", "pageToken", "page", "offset")
LIMIT_NAMES = ("limit", "size", "pageSize", "per_page", "maxResults")
MONEY_HINTS = ("amount", "price", "fee", "cost", "total", "balance")
MASS_ASSIGNMENT_PROBES = (
    ("role", "admin"), ("tenantId", "other-tenant"), ("status", "ACTIVE"), ("price", 0),
    ("id", "00000000-0000-0000-0000-000000000000"), ("isAdmin", True),
)

_PATTERN_MAX = 1000
_PROBE_MAX = 64


class _Remove:
    def __repr__(self):
        return "REMOVE"


REMOVE = _Remove()


@dataclass(frozen=True)
class BodyMode:
    mode: str
    raw: str | None = None


@dataclass(frozen=True)
class Variant:
    rule_id: str
    value: object
    slug: str | None = None


@dataclass(frozen=True)
class Rule:
    id: str
    keyword: str
    applies: tuple
    guard: str | None
    kind: str
    valid: bool
    technique: str
    priority: str
    value: tuple
    tags: tuple = ()


def compile_pattern(p):
    if not isinstance(p, str) or len(p) > _PATTERN_MAX:
        return None
    out = []
    in_class = False
    i = 0
    while i < len(p):
        ch = p[i]
        if ch == "\\" and i + 1 < len(p):
            nxt = p[i + 1]
            if nxt in "pP":
                m = re.match(r"\{(\w+)\}", p[i + 2:])
                if not m:
                    return None
                names = PATTERN_TRANSLATIONS.get(m.group(1))
                if nxt == "P" or names is None:
                    return None
                out.append(names[1] if in_class else names[0])
                i += 2 + m.end()
                continue
            out.append(p[i:i + 2])
            i += 2
            continue
        if ch == "[" and not in_class:
            in_class = True
        elif ch == "]" and in_class:
            in_class = False
        out.append(ch)
        i += 1
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return re.compile("".join(out))
    except re.error:
        return None


def _num(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return Decimal(str(x))


GUARDS = {
    "m_gt_0": lambda f: (_num(f.constraints.get("minLength")) or 0) > 0,
    "anchored": lambda f: isinstance(f.constraints.get("pattern"), str)
    and f.constraints["pattern"].startswith("^") and f.constraints["pattern"].endswith("$"),
    "not_nullable": lambda f: not f.nullable,
    "optional": lambda f: not f.required,
    "is_string": lambda f: f.type == "string",
    "int_format": lambda f: f.format in ("int32", "int64"),
    "enum_is_string": lambda f: bool(f.constraints.get("enum"))
    and all(isinstance(v, str) for v in f.constraints["enum"]),
    "min_items_ge_1": lambda f: (_num(f.constraints.get("minItems")) or 0) >= 1,
    "multiple_of_not_1_int": lambda f: not (f.type == "integer" and f.constraints.get("multipleOf") == 1),
}


def _has(kw):
    return lambda f: kw in f.constraints


def _pattern_ok(f):
    return "pattern" in f.constraints and compile_pattern(f.constraints["pattern"]) is not None


def _pattern_bad(f):
    return "pattern" in f.constraints and compile_pattern(f.constraints["pattern"]) is None


TRIGGERS = {
    **{kw: _has(kw) for kw in (
        "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
        "multipleOf", "enum", "minItems", "maxItems", "additionalProperties",
    )},
    "uniqueItems": lambda f: f.constraints.get("uniqueItems") is True,
    "required": lambda f: f.required,
    "type": lambda f: f.type is not None,
    "nullable": lambda f: f.nullable,
    "readOnly": lambda f: f.read_only,
    # uri/url belong to format.uri so its security tagging survives dedupe
    "format": lambda f: f.format in FORMAT_INVALID and f.format not in ("uri", "url"),
    "format.uri": lambda f: f.format in ("uri", "url"),
    "format.int": lambda f: f.format in ("int32", "int64"),
    "pattern": _pattern_ok,
    "pattern.uncompilable": _pattern_bad,
}


def _r(id, kw, applies, guard, kind, valid, tech, prio, value, tags=()):
    base = kw.split(".")[0]
    return Rule(
        id, kw, tuple(applies.split()), guard, kind, valid, tech, prio, tuple(value),
        (f"constraint:{base}",) + tuple(tags),
    )


_NUM = "integer number"
RULES = (
    _r("required.missing", "required", "any", None, "REQUIRED_MISSING", False, "ep", "P2", ("remove",)),
    _r("required.null", "required", "any", None, "REQUIRED_MISSING", False, "ep", "P2", ("null",)),
    _r("required.empty", "required", "string", None, "REQUIRED_MISSING", False, "ep", "P2", ("literal", "")),
    _r("type.wrong", "type", "integer number boolean string object array", None, "TYPE_INVALID", False, "error-guess", "P2", ("type_wrong",)),
    _r("type.null", "type", "any", "not_nullable", "TYPE_INVALID", False, "error-guess", "P3", ("null",)),
    _r("type.overflow", "format.int", "integer", "int_format", "TYPE_INVALID", False, "bva-3", "P3", ("overflow",)),
    _r("nullable.null", "nullable", "any", None, "OPTIONAL_ABSENT", True, "ep", "P3", ("null",)),
    _r("minLength.min", "minLength", "string", None, "LENGTH_BOUNDARY_VALID", True, "bva-3", "P3", ("strlen", "minLength", 0)),
    _r("minLength.plus1", "minLength", "string", None, "LENGTH_BOUNDARY_VALID", True, "bva-3", "P3", ("strlen", "minLength", 1)),
    _r("minLength.minus1", "minLength", "string", "m_gt_0", "LENGTH_INVALID", False, "bva-3", "P2", ("strlen", "minLength", -1)),
    _r("maxLength.minus1", "maxLength", "string", None, "LENGTH_BOUNDARY_VALID", True, "bva-3", "P3", ("strlen", "maxLength", -1)),
    _r("maxLength.max", "maxLength", "string", None, "LENGTH_BOUNDARY_VALID", True, "bva-3", "P3", ("strlen", "maxLength", 0)),
    _r("maxLength.plus1", "maxLength", "string", None, "LENGTH_INVALID", False, "bva-3", "P2", ("strlen", "maxLength", 1)),
    _r("minimum.min", "minimum", _NUM, None, "RANGE_BOUNDARY_VALID", True, "bva-3", "P3", ("num", "minimum", 0)),
    _r("minimum.plus1", "minimum", _NUM, None, "RANGE_BOUNDARY_VALID", True, "bva-3", "P3", ("num", "minimum", 1)),
    _r("minimum.minus1", "minimum", _NUM, None, "RANGE_INVALID", False, "bva-3", "P2", ("num", "minimum", -1)),
    _r("maximum.minus1", "maximum", _NUM, None, "RANGE_BOUNDARY_VALID", True, "bva-3", "P3", ("num", "maximum", -1)),
    _r("maximum.max", "maximum", _NUM, None, "RANGE_BOUNDARY_VALID", True, "bva-3", "P3", ("num", "maximum", 0)),
    _r("maximum.plus1", "maximum", _NUM, None, "RANGE_INVALID", False, "bva-3", "P2", ("num", "maximum", 1)),
    _r("exclusiveMinimum.plus1", "exclusiveMinimum", _NUM, None, "RANGE_BOUNDARY_VALID", True, "bva-3", "P3", ("num", "exclusiveMinimum", 1)),
    _r("exclusiveMinimum.at", "exclusiveMinimum", _NUM, None, "RANGE_INVALID", False, "bva-3", "P2", ("num", "exclusiveMinimum", 0)),
    _r("exclusiveMaximum.minus1", "exclusiveMaximum", _NUM, None, "RANGE_BOUNDARY_VALID", True, "bva-3", "P3", ("num", "exclusiveMaximum", -1)),
    _r("exclusiveMaximum.at", "exclusiveMaximum", _NUM, None, "RANGE_INVALID", False, "bva-3", "P2", ("num", "exclusiveMaximum", 0)),
    _r("multipleOf.k1", "multipleOf", _NUM, None, "RANGE_BOUNDARY_VALID", True, "bva-3", "P3", ("num", "multipleOf", 0)),
    _r("multipleOf.k2", "multipleOf", _NUM, None, "RANGE_BOUNDARY_VALID", True, "bva-3", "P3", ("num", "multipleOf", 1)),
    _r("multipleOf.off", "multipleOf", _NUM, "multiple_of_not_1_int", "RANGE_INVALID", False, "bva-3", "P2", ("multiple_off",)),
    _r("pattern.empty", "pattern", "string", None, "PATTERN_INVALID", False, "ep", "P2", ("pattern_probe", "empty")),
    _r("pattern.out_of_class", "pattern", "string", None, "PATTERN_INVALID", False, "ep", "P2", ("pattern_probe", "out_of_class")),
    _r("pattern.lead_space", "pattern", "string", "anchored", "PATTERN_INVALID", False, "ep", "P2", ("pattern_probe", "lead_space")),
    _r("pattern.trail_space", "pattern", "string", "anchored", "PATTERN_INVALID", False, "ep", "P2", ("pattern_probe", "trail_space")),
    _r("pattern.llm", "pattern.uncompilable", "string", None, "PATTERN_INVALID", False, "llm", "P2", ("pattern_llm",)),
    _r("format", "format", "string", None, "FORMAT_INVALID", False, "ep", "P2", ("format_invalid",)),
    _r("format.uri", "format.uri", "string", None, "FORMAT_INVALID", False, "owasp-api7", "P2", ("format_invalid",), ("security",)),
    _r("enum.each", "enum", "any", None, "ENUM_EACH_VALID", True, "ep", "P3", ("enum_each",)),
    _r("enum.not_in_set", "enum", "any", None, "ENUM_INVALID", False, "ep", "P2", ("enum_variant", "not_in_set")),
    _r("enum.case_changed", "enum", "any", "enum_is_string", "ENUM_INVALID", False, "ep", "P2", ("enum_variant", "case_changed")),
    _r("enum.trailing_space", "enum", "any", "enum_is_string", "ENUM_INVALID", False, "ep", "P2", ("enum_variant", "trailing_space")),
    _r("enum.empty", "enum", "any", "enum_is_string", "ENUM_INVALID", False, "ep", "P2", ("enum_variant", "empty")),
    _r("minItems.min", "minItems", "array", None, "ARRAY_BOUNDS", True, "bva-3", "P3", ("items", "minItems", 0)),
    _r("minItems.minus1", "minItems", "array", None, "ARRAY_BOUNDS", False, "bva-3", "P2", ("items", "minItems", -1)),
    _r("maxItems.max", "maxItems", "array", None, "ARRAY_BOUNDS", True, "bva-3", "P3", ("items", "maxItems", 0)),
    _r("maxItems.plus1", "maxItems", "array", None, "ARRAY_BOUNDS", False, "bva-3", "P2", ("items", "maxItems", 1)),
    _r("items.empty", "minItems", "array", "min_items_ge_1", "ARRAY_BOUNDS", False, "bva-3", "P2", ("items_empty",)),
    _r("uniqueItems.dup", "uniqueItems", "array", None, "ARRAY_BOUNDS", False, "bva-3", "P2", ("items_dup",)),
    _r("additionalProperties.unknown", "additionalProperties", "object", None, "UNKNOWN_FIELD", False, "error-guess", "P2", ("literal", {"__unexpected_field__": "x"})),
    _r("readOnly.sent", "readOnly", "any", None, "READONLY_SENT", False, "owasp-api3", "P1", ("valid_sample",)),
)

DERIVE_RULE_IDS = frozenset(
    {
        "required.all_missing", "unbounded.oversize", "additionalProperties.unknown",
        "body.malformed", "body.array", "body.empty", "body.content_type",
        "path.malformed", "path.not_found", "query.missing",
        "pagination.walk", "pagination.bad_cursor",
        "limit.over_max", "limit.zero", "limit.negative", "limit.huge",
        "auth.missing", "auth.malformed", "auth.public",
        "happy.full", "happy.min", "optional.absent", "lifecycle.crud", "lifecycle.delete_twice",
    }
    | {f"mass_assignment.{name}" for name, _ in MASS_ASSIGNMENT_PROBES}
)
RULE_IDS = frozenset(
    {r.id for r in RULES}
    | {f"format.{name}" for variants in FORMAT_INVALID.values() for name, _ in variants}
    | {"type.wrong"}
    | DERIVE_RULE_IDS
)


def fires(rule, field):
    if field.truncated:
        return False
    if rule.applies != ("any",) and field.type not in rule.applies:
        return False
    if not TRIGGERS[rule.keyword](field):
        return False
    return rule.guard is None or bool(GUARDS[rule.guard](field))


def _typed(field, d):
    return int(d) if field.type == "integer" else float(d)


def _in_range(field, d):
    c = field.constraints
    for key, ok in (
        ("minimum", lambda b: d >= b), ("maximum", lambda b: d <= b),
        ("exclusiveMinimum", lambda b: d > b), ("exclusiveMaximum", lambda b: d < b),
    ):
        b = _num(c.get(key))
        if b is not None and not ok(b):
            return False
    return True


def _strlen(rule, field):
    kw, delta = rule.value[1], rule.value[2]
    base = _num(field.constraints[kw])
    if base is None:
        return []
    n = int(base) + delta
    if n < 0:
        return []
    if rule.valid:
        lo, hi = _num(field.constraints.get("minLength")), _num(field.constraints.get("maxLength"))
        if (lo is not None and n < lo) or (hi is not None and n > hi):
            return []
    return [Variant(rule.id, "" if n == 0 else f"<<str:{n}>>")]


def _numeric(rule, field):
    kw, mult = rule.value[1], rule.value[2]
    base = _num(field.constraints[kw])
    if base is None:
        return []
    step = _num(field.constraints.get("multipleOf")) or Decimal(1)
    d = base + mult * step
    if rule.valid and not _in_range(field, d):
        return []
    return [Variant(rule.id, _typed(field, d))]


def _multiple_off(rule, field):
    k = _num(field.constraints["multipleOf"])
    if k is None:
        return []
    d = k + 1 if field.type == "integer" else k / 2
    return [Variant(rule.id, _typed(field, d))]


def _items(rule, field):
    kw, delta = rule.value[1], rule.value[2]
    base = _num(field.constraints[kw])
    if base is None:
        return []
    n = int(base) + delta
    if n < 0:
        return []
    if rule.valid:
        lo, hi = _num(field.constraints.get("minItems")), _num(field.constraints.get("maxItems"))
        if (lo is not None and n < lo) or (hi is not None and n > hi):
            return []
    return [Variant(rule.id, [] if n == 0 else f"<<items:{n}>>")]


def _enum_variant(rule, field):
    values = field.constraints["enum"]
    which = rule.value[1]
    if which == "not_in_set":
        nums = [_num(v) for v in values]
        if values and all(n is not None for n in nums):
            top = max(nums) + 1
            return [Variant(rule.id, int(top) if all(isinstance(v, int) for v in values) else float(top))]
        probe = "NOT_IN_ENUM_VALUE"
        while probe in values:
            probe += "_X"
        return [Variant(rule.id, probe)]
    if which == "case_changed":
        for v in values:
            if v.swapcase() != v and v.swapcase() not in values:
                return [Variant(rule.id, v.swapcase())]
        return []
    if which == "trailing_space":
        return [Variant(rule.id, values[0] + " ")]
    return [] if "" in values else [Variant(rule.id, "")]


def _sample_for(field):
    c = field.constraints
    for key in ("example", "default"):
        if key in c:
            return c[key]
    fmt, t = field.format, field.type
    if t == "string":
        fixed = {
            "uuid": "00000000-0000-4000-8000-000000000000",
            "date-time": "2026-01-01T00:00:00Z",
            "date": "2026-01-01",
            "email": "a@b.co",
        }
        if fmt in fixed:
            return fixed[fmt]
        n = int(_num(c.get("minLength")) or 0)
        return f"<<str:{max(n, 1)}>>"
    if t in ("integer", "number"):
        base = _num(c.get("minimum"))
        if t == "integer":
            return int(base) if base is not None else 1
        return float(base) if base is not None else 1.0
    if t == "boolean":
        return True
    if t == "object":
        return {}
    if t == "array":
        return []
    return None


def _probe_ok(rx, s):
    return rx.search(s) is None and rx.fullmatch(s) is None


def _pattern_probe(rule, field):
    which = rule.value[1]
    c = field.constraints
    rx = compile_pattern(c["pattern"])
    if which == "empty":
        s = ""
    elif which == "out_of_class":
        n = min(max(int(_num(c.get("minLength")) or 1), 1), _PROBE_MAX)
        s = next((ch * n for ch in PROBE_CHARS if _probe_ok(rx, ch * n)), None)
        if s is None:
            return []
    else:
        sample = next(
            (c[k] for k in ("example", "default") if isinstance(c.get(k), str) and rx.fullmatch(c[k])),
            None,
        )
        lead = which == "lead_space"
        if sample is None:
            return [Variant(rule.id, " <<pattern-sample>>" if lead else "<<pattern-sample>> ")]
        s = " " + sample if lead else sample + " "
    return [Variant(rule.id, s)] if _probe_ok(rx, s) else []


def expand(rule, field):
    if not fires(rule, field):
        return []
    op = rule.value[0]
    if op == "strlen":
        return _strlen(rule, field)
    if op == "num":
        return _numeric(rule, field)
    if op == "multiple_off":
        return _multiple_off(rule, field)
    if op == "items":
        return _items(rule, field)
    if op == "items_dup":
        return [Variant(rule.id, "<<items:dup>>")]
    if op == "items_empty":
        return [Variant(rule.id, [])]
    if op == "literal":
        return [Variant(rule.id, rule.value[1])]
    if op == "remove":
        return [Variant(rule.id, REMOVE)]
    if op == "null":
        return [Variant(rule.id, None)]
    if op == "type_wrong":
        return [Variant("type.wrong", v, slug) for slug, v in TYPE_WRONG[field.type]]
    if op == "overflow":
        return [Variant(rule.id, 2**31 if field.format == "int32" else 2**63)]
    if op == "enum_each":
        return [Variant("enum.each", v, str(v)) for v in field.constraints["enum"]]
    if op == "enum_variant":
        return _enum_variant(rule, field)
    if op == "format_invalid":
        return [Variant(f"format.{name}", v) for name, v in FORMAT_INVALID[field.format]]
    if op == "pattern_probe":
        return _pattern_probe(rule, field)
    if op == "pattern_llm":
        return [Variant(rule.id, "<<pattern-negative>>")]
    if op == "valid_sample":
        return [Variant(rule.id, _sample_for(field))]
    if op == "body_mode":
        return [Variant(rule.id, BodyMode(rule.value[1], rule.value[2] if len(rule.value) > 2 else None))]
    raise ValueError(f"unknown DSL op {op!r} in rule {rule.id}")
