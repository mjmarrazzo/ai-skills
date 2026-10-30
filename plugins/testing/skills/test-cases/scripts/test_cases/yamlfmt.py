import json
import math
import re

# PyYAML folds raw U+0085 into a space and rejects raw DEL/ESC, so these are
# written as \u escapes instead of relying on JSON's own (narrower) escaping.
_ESCAPE = re.compile("[\x00-\x1f\x7f-\x9f  ﻿￾￿\ud800-\udfff]")
_BARE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_YAML11_WORDS = frozenset(
    "y Y yes Yes YES n N no No NO true True TRUE false False FALSE "
    "on On ON off Off OFF null Null NULL".split()
)


def _str(s):
    return _ESCAPE.sub(lambda m: "\\u%04x" % ord(m.group()), json.dumps(s, ensure_ascii=False))


def _key(k):
    k = str(k)
    return k if _BARE_KEY.match(k) and k not in _YAML11_WORDS else _str(k)


def _float(f):
    if math.isnan(f) or math.isinf(f):
        raise ValueError("cannot emit non-finite float: %r" % f)
    r = repr(f)
    if "e" in r and "." not in r:
        m, e = r.split("e")
        r = m + ".0e" + e
    return r


def _scalar(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return _float(v)
    if isinstance(v, str):
        return _str(v)
    raise TypeError("unsupported type: %s" % type(v).__name__)


def _container(v):
    return isinstance(v, (dict, list)) and len(v) > 0


def _lines(v, indent):
    pad = "  " * indent
    out = []
    if isinstance(v, dict):
        for k, val in v.items():
            if _container(val):
                out.append("%s%s:" % (pad, _key(k)))
                out.extend(_lines(val, indent + 1))
            else:
                out.append("%s%s: %s" % (pad, _key(k), _inline(val)))
    else:
        for item in v:
            if isinstance(item, dict) and item:
                sub = _lines(item, indent + 1)
                out.append("%s- %s" % (pad, sub[0][len(pad) + 2:]))
                out.extend(sub[1:])
            elif isinstance(item, list) and item:
                out.append("%s-" % pad)
                out.extend(_lines(item, indent + 1))
            else:
                out.append("%s- %s" % (pad, _inline(item)))
    return out


def _inline(v):
    if isinstance(v, dict):
        return "{}"
    if isinstance(v, list):
        return "[]"
    return _scalar(v)


def dump(obj):
    if _container(obj):
        return "\n".join(_lines(obj, 0)) + "\n"
    return _inline(obj) + "\n"
