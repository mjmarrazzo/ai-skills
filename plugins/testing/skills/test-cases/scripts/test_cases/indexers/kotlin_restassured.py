import bisect
import fnmatch
import re

HTTP_STATUS = {"SC_OK": 200, "SC_CREATED": 201, "SC_ACCEPTED": 202, "SC_NO_CONTENT": 204, "SC_MOVED_PERMANENTLY": 301, "SC_FOUND": 302, "SC_NOT_MODIFIED": 304, "SC_BAD_REQUEST": 400, "SC_UNAUTHORIZED": 401, "SC_FORBIDDEN": 403, "SC_NOT_FOUND": 404, "SC_METHOD_NOT_ALLOWED": 405, "SC_CONFLICT": 409, "SC_GONE": 410, "SC_PRECONDITION_FAILED": 412, "SC_REQUEST_TOO_LONG": 413, "SC_UNSUPPORTED_MEDIA_TYPE": 415, "SC_UNPROCESSABLE_ENTITY": 422, "SC_TOO_MANY_REQUESTS": 429, "SC_INTERNAL_SERVER_ERROR": 500, "SC_BAD_GATEWAY": 502, "SC_SERVICE_UNAVAILABLE": 503, "SC_GATEWAY_TIMEOUT": 504}

_PASSES = 10
_TEST_ANNOTATIONS = ("Test", "TestFactory", "ParameterizedTest")
_KNOWN_ANNOTATIONS = frozenset(_TEST_ANNOTATIONS) | {"Disabled", "ManualTest", "DisplayName"}

_OBJECT_RE = re.compile(r"\bobject\s+(\w*Paths\w*)\s*\{")
_VAL_RE = re.compile(r"^[ \t]*(private\s+)?(?:const\s+)?val\s+(\w+)\s*(?::\s*String\s*)?=", re.M)
_FUN_RE = re.compile(r"^[ \t]*(private\s+)?fun\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*String\s*)?=", re.M)
_PARAM_RE = re.compile(r"(\w+)\s*:")
_IDENT_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
_TEMPLATE_RE = re.compile(r"\$\{([\w.]+)\}|\$([A-Za-z_]\w*)")
_CLASS_RE = re.compile(r"\bclass\s+(\w+)")
_METHOD_RE = re.compile(
    r"\bfun\s+(?:<[^>]*>\s*)?(`[^`\n]+`|\w+)\s*\("
    r"|\b(?:(?:public|private|protected)\s+)?(?:static\s+)?void\s+(\w+)\s*\("
)
_ANNOTATION_RE = re.compile(r"@(\w+)")
_DISPLAY_NAME_RE = re.compile(r'@DisplayName\s*\(\s*"((?:[^"\\]|\\.)*)"')
_CALL_RE = re.compile(r"(?<![\w])\.?(get|post|put|patch|delete|options|head)\s*\(")
_STATUS_RE = re.compile(r"statusCode\s*\(\s*(?:equalTo\s*\(\s*)?(?:(\d{3})|HttpStatus\.(SC_\w+))")
_PLACEHOLDER_RE = re.compile(r"\{[^}]*\}")

_CLOSERS = {"(": ")", "[": "]", "{": "}"}


class _Unresolved(Exception):
    pass


def _mask(text):
    # Keeps offsets and newlines so structure can be scanned on the mask while
    # literal text is still read from the original.
    out = list(text)
    n = len(text)

    def blank(a, b):
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    i = 0
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif text.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith("/*", j):
                    depth += 1
                    j += 2
                elif text.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            blank(i, j)
            i = j
        elif text.startswith('"""', i):
            j = text.find('"""', i + 3)
            j = n if j < 0 else j
            blank(i + 3, j)
            i = j + 3
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            blank(i + 1, j)
            i = j + 1
        else:
            i += 1
    return "".join(out)


def _match(masked, open_idx):
    open_c = masked[open_idx]
    close_c = _CLOSERS[open_c]
    depth = 0
    for k in range(open_idx, len(masked)):
        ch = masked[k]
        if ch == open_c:
            depth += 1
        elif ch == close_c:
            depth -= 1
            if depth == 0:
                return k
    return len(masked) - 1


def _string_end(expr, pos):
    j = pos + 1
    while j < len(expr) and expr[j] != '"':
        j += 2 if expr[j] == "\\" else 1
    return j


def _skip_call_args(expr, pos):
    k = pos
    while k < len(expr) and expr[k].isspace():
        k += 1
    if k >= len(expr) or expr[k] != "(":
        return pos
    depth = 0
    while k < len(expr):
        ch = expr[k]
        if ch == '"':
            k = _string_end(expr, k)
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return k + 1
        k += 1
    return len(expr)


def _template(body, lookup, final):
    def sub(m):
        value = lookup(m.group(1) or m.group(2))
        if value is None:
            if final:
                return "{?}"
            raise _Unresolved
        return value

    return _TEMPLATE_RE.sub(sub, body)


def _eval(expr, lookup, final):
    out = []
    pos, n = 0, len(expr)
    try:
        while pos < n:
            c = expr[pos]
            if c.isspace() or c == "+":
                pos += 1
            elif c == '"':
                end = _string_end(expr, pos)
                out.append(_template(expr[pos + 1:end], lookup, final))
                pos = end + 1
            else:
                m = _IDENT_RE.match(expr, pos)
                if not m:
                    raise _Unresolved
                value = lookup(m.group())
                pos = _skip_call_args(expr, m.end())
                if value is None:
                    if not final:
                        raise _Unresolved
                    value = "{?}"
                out.append(value)
    except _Unresolved:
        if not final:
            return None
        out.append("{?}")
    return "".join(out)


class _LineIndex:
    def __init__(self, text):
        self._starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]

    def line(self, pos):
        return bisect.bisect_right(self._starts, pos)


def _expr_at(text, masked, start):
    end = masked.find("\n", start)
    end = len(text) if end < 0 else end
    while masked[start:end].rstrip().endswith("+") and end < len(text):
        nxt = masked.find("\n", end + 1)
        end = len(text) if nxt < 0 else nxt
    return text[start:end].strip()


def _collect_entries(path, text, masked):
    entries = {}
    for om in _OBJECT_RE.finditer(masked):
        obj = om.group(1)
        lo, hi = om.end(), _match(masked, om.end() - 1)
        block = masked[lo:hi]
        for m in _VAL_RE.finditer(block):
            expr = _expr_at(text, masked, lo + m.end())
            entries[f"{obj}.{m.group(2)}"] = (obj, expr, (), bool(m.group(1)), path)
        for m in _FUN_RE.finditer(block):
            params = tuple(_PARAM_RE.findall(m.group(3)))
            expr = _expr_at(text, masked, lo + m.end())
            entries[f"{obj}.{m.group(2)}"] = (obj, expr, params, bool(m.group(1)), path)
    return entries


def _fold(entries):
    resolved = {}

    def lookup_for(obj, params):
        def lookup(name):
            if name in params:
                return "{" + name + "}"
            return resolved.get(name if "." in name else f"{obj}.{name}")

        return lookup

    for _ in range(_PASSES):
        progress = False
        for key in sorted(entries):
            if key in resolved:
                continue
            obj, expr, params, _, _ = entries[key]
            value = _eval(expr, lookup_for(obj, params), False)
            if value is not None:
                resolved[key] = value.replace("%s", "{}")
                progress = True
        if not progress:
            break
    leftovers = {}
    for key in sorted(entries):
        if key not in resolved:
            obj, expr, params, _, _ = entries[key]
            leftovers[key] = _eval(expr, lookup_for(obj, params), True).replace("%s", "{}")
    resolved.update(leftovers)
    return {k: resolved[k] for k in sorted(resolved)}


def _normalize(path):
    return _PLACEHOLDER_RE.sub("{}", path)


def _suffix_related(a, b):
    short, long_ = sorted((a, b), key=len)
    if short in ("", "/") or not long_.endswith(short):
        return False
    return len(short) == len(long_) or short.startswith("/") or long_[-len(short) - 1] == "/"


def _match_op(verb, path, ctx):
    norm = _normalize(path)
    server = _normalize(ctx.server_path) if ctx.server_path else None
    if server and norm.startswith(server) and (len(norm) == len(server) or norm[len(server)] == "/"):
        norm = norm[len(server):]
    spec_ops = [(m.upper(), p, _normalize(p)) for m, p in ctx.spec_ops]
    for m, p, np_ in spec_ops:
        if m == verb and np_ == norm:
            return f"{verb} {p}"
    hits = sorted({p for m, p, np_ in spec_ops if m == verb and _suffix_related(np_, norm)})
    return f"{verb} {hits[0]}" if len(hits) == 1 else None


def _annotations_before(text, masked, pos):
    start = max(masked.rfind(ch, 0, pos) for ch in "{};") + 1
    region = masked[start:pos]
    names = [n for n in _ANNOTATION_RE.findall(region) if n in _KNOWN_ANNOTATIONS]
    dn = _DISPLAY_NAME_RE.search(text[start:pos])
    return names, (dn.group(1) if dn else None)


def _expression_body_end(masked, start):
    depth = 0
    n = len(masked)
    k = start
    while k < n:
        ch = masked[k]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif ch == "\n" and depth == 0:
            j = k
            while j < n and masked[j].isspace():
                j += 1
            if j >= n or masked[j] not in ".?+&|:":
                break
        k += 1
    return len(masked[:k].rstrip())


def _first_arg(text, masked, start):
    depth = 0
    for k in range(start, len(masked)):
        ch = masked[k]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return " ".join(text[start:k].split())
            depth -= 1
        elif ch == "," and depth == 0:
            return " ".join(text[start:k].split())
    return " ".join(text[start:].split())


def _statuses(body):
    found = set()
    for num, name in _STATUS_RE.findall(body):
        if num:
            found.add(int(num))
        elif name in HTTP_STATUS:
            found.add(HTTP_STATUS[name])
    return sorted(found)


def _methods(text, masked, lines, class_disabled, lookup, ctx):
    methods = []
    for m in _METHOD_RE.finditer(masked):
        names, display = _annotations_before(text, masked, m.start())
        if not any(a in names for a in _TEST_ANNOTATIONS + ("ManualTest",)):
            continue
        kw_pos = m.start() + m.group().find("fun " if m.group(1) else "void")
        close = _match(masked, m.end() - 1)
        j = close + 1
        while j < len(masked) and masked[j] not in "{=;}":
            j += 1
        if j >= len(masked) or masked[j] in ";}":
            continue
        if masked[j] == "{":
            body_start, body_end = j + 1, _match(masked, j)
            end_pos = body_end
        else:
            body_start = j + 1
            body_end = end_pos = _expression_body_end(masked, body_start)
        body = masked[body_start:body_end]

        calls = []
        for cm in _CALL_RE.finditer(body):
            expr = _first_arg(text, masked, body_start + cm.end())
            path = _eval(expr, lookup, True)
            if not path.startswith("/"):
                continue
            verb = cm.group(1).upper()
            calls.append({
                "verb": verb,
                "expr": expr,
                "path": path,
                "op": _match_op(verb, path, ctx),
                "line": lines.line(body_start + cm.start(1)),
            })
        statuses = _statuses(body)
        if "ManualTest" in names:
            stub = "manual"
        elif "Disabled" in names or class_disabled:
            stub = "disabled"
        elif not body.strip():
            stub = "empty"
        elif not statuses:
            stub = "no_status_assert"
        else:
            stub = None
        methods.append({
            "name": (m.group(1) or m.group(2)).strip("`"),
            "line": lines.line(kw_pos),
            "end_line": lines.line(end_pos),
            "annotations": names,
            "factory": "TestFactory" in names,
            "display_name": display,
            "stub": stub,
            "calls": calls,
            "statuses": statuses,
        })
    return sorted(methods, key=lambda x: x["line"])


class KotlinRestAssuredIndexer:
    name = "kotlin-restassured"

    def detect(self, rel_paths):
        return any(p.endswith((".kt", ".java")) for p in rel_paths)

    def index(self, sources, ctx):
        ordered = sorted(sources, key=lambda s: s.path)
        masks = {s.path: _mask(s.text) for s in ordered}

        entries = {}
        for s in ordered:
            entries.update(_collect_entries(s.path, s.text, masks[s.path]))
        constants = _fold(entries)
        bare = {}
        for key in sorted(constants):
            bare.setdefault(key.split(".", 1)[1], constants[key])

        def lookup(name):
            return constants.get(name) if "." in name else bare.get(name)

        unused = []
        for key in sorted(entries):
            _, _, _, private, defined_in = entries[key]
            if private:
                continue
            word = re.compile(r"\b" + re.escape(key.split(".", 1)[1]) + r"\b")
            if not any(word.search(s.text) for s in ordered if s.path != defined_in):
                unused.append(key)

        files = []
        for s in ordered:
            masked = masks[s.path]
            cm = _CLASS_RE.search(masked)
            if not cm:
                continue
            class_names, class_display = _annotations_before(s.text, masked, cm.start())
            lines = _LineIndex(s.text)
            excluded = next((p for p in ctx.exclude_classes if fnmatch.fnmatchcase(cm.group(1), p)), None)
            files.append({
                "path": s.path,
                "class": cm.group(1),
                "excluded": excluded,
                "display_name": class_display,
                "methods": _methods(s.text, masked, lines, "Disabled" in class_names, lookup, ctx),
            })
        return {
            "version": 1,
            "indexer": self.name,
            "path_constants": constants,
            "unused_path_constants": unused,
            "files": files,
        }
