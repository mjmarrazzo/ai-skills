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
