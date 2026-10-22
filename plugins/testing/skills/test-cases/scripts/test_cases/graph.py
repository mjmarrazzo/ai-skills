import heapq
import re
from dataclasses import dataclass

from test_cases import ir

_VERSION_SEG = re.compile(r"^v\d+$")
_PARAM_SEG = re.compile(r"^\{[^}]*\}$")
_LOGIN_LIKE = re.compile(r"login|logout|token|oauth|auth|session|signin|signup")
_ID_FIELD = re.compile(r"^(.+?)(?:Id|Ids)$")
_FLAGS = ("C", "L", "R", "U", "P", "D")
_ITEM_FLAGS = {"GET": "R", "PUT": "U", "PATCH": "P", "DELETE": "D"}


class GraphError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Entity:
    id: str
    collection_path: str
    item_path: str | None
    id_param: str | None
    parent: str | None
    ops: dict
    actions: tuple
    singleton: bool
    lifecycle: bool
    id_candidate: dict | None
    depends_on: tuple
    needs: tuple


@dataclass(frozen=True, slots=True)
class Graph:
    entities: tuple
    order: tuple
    warnings: tuple


def singular(word):
    if word.endswith("ies"):
        return word[:-3] + "y"
    for suffix in ("ses", "xes", "zes", "ches", "shes"):
        if word.endswith(suffix):
            return word[:-2]
    if word.endswith("ss"):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def _segments(path):
    return [s for s in path.split("/") if s and not _VERSION_SEG.match(s)]


def _slug(segs):
    parts = []
    for seg in segs:
        if _PARAM_SEG.match(seg):
            continue
        part = re.sub(r"[^a-z0-9]+", "-", seg.lower()).strip("-")
        if part:
            parts.append(part)
    return "-".join(parts) or "root"


class _Key:
    def __init__(self, segs, order):
        self.segs = segs
        self.order = order
        self.collection = []  # (doc index, op)
        self.item = []
        self.folded_into = None


def _group(spec):
    keys = {}
    for index, op in enumerate(spec.operations):
        segs = _segments(op.path)
        is_item = bool(segs) and _PARAM_SEG.match(segs[-1]) is not None
        key_segs = tuple("{}" if _PARAM_SEG.match(s) else s for s in (segs[:-1] if is_item else segs))
        key = keys.setdefault(key_segs, _Key(key_segs, len(keys)))
        (key.item if is_item else key.collection).append((index, op))
    return keys


def _raw_flags(key):
    flags = {}
    extra = []
    for index, op in key.collection:
        flag = {"POST": "C", "GET": "L"}.get(op.method)
        if flag and flag not in flags:
            flags[flag] = op
        else:
            extra.append((index, op))
    for index, op in key.item:
        flag = _ITEM_FLAGS.get(op.method)
        if flag and flag not in flags:
            flags[flag] = op
        else:
            extra.append((index, op))
    return flags, extra


def _find_parent(key, item_index):
    for n in range(len(key.segs) - 1, 0, -1):
        hit = item_index.get(key.segs[:n])
        if hit is not None:
            return hit
    return None


def _top_level_fields(spec, schema_name):
    schema = spec.schemas.get(schema_name)
    if not isinstance(schema, dict):
        return ()
    token = schema_name.replace("~", "~0").replace("/", "~1")
    doc = {"definitions": spec.schemas, "components": {"schemas": spec.schemas}}
    walk = ir.walk_schema(doc, {"$ref": f"#/components/schemas/{token}"}, f"#/components/schemas/{token}")
    return tuple(f.name for f in walk.fields if f.path == f.name and not f.name.endswith("[]"))


def _id_candidate(spec, create_op, id_param, entity_id):
    if create_op is None:
        return None
    ok = sorted(r.status for r in create_op.responses if re.fullmatch(r"2\d\d", r.status) and r.schema_name)
    if not ok:
        return None
    resp = next(r for r in create_op.responses if r.status == ok[0] and r.schema_name)
    names = _top_level_fields(spec, resp.schema_name)
    wanted = [id_param, "id", singular(entity_id.rsplit("-", 1)[-1]) + "Id"]
    for field in wanted:
        if field and field in names:
            return {"field": field, "source": "spec-candidate"}
    return None


def _tarjan(nodes, adj):
    index = {}
    low = {}
    on_stack = set()
    stack = []
    sccs = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(sorted(adj.get(root, ()))))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(sorted(adj.get(nxt, ())))))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    top = stack.pop()
                    on_stack.discard(top)
                    comp.append(top)
                    if top == node:
                        break
                sccs.append(comp)
    return sccs


def _topo(ids, deps):
    indeg = {i: len(deps[i]) for i in ids}
    dependents = {i: [] for i in ids}
    for i in ids:
        for d in deps[i]:
            dependents[d].append(i)
    heap = [i for i in ids if indeg[i] == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        cur = heapq.heappop(heap)
        order.append(cur)
        for nxt in dependents[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                heapq.heappush(heap, nxt)
    return order


def build_graph(spec):
    warnings = []
    keys = _group(spec)
    entities = {}  # segs -> record dict
    item_index = {}

    for key in sorted(keys.values(), key=lambda k: (len(k.segs), k.order)):
        flags, extra = _raw_flags(key)
        parent = _find_parent(key, item_index)
        no_clr = not any(f in flags for f in "CLR")
        post_only = not key.item and "L" not in flags
        if parent is not None and (no_clr or post_only):
            rec = entities[parent]
            rec["actions"].extend(key.collection + key.item)
            key.folded_into = parent
            continue

        rec = {
            "key": key, "parent": parent, "flags": flags, "actions": list(extra),
            "singleton": not key.item and "C" not in flags,
        }
        if rec["singleton"]:
            rec["flags"], rec["actions"] = {}, []
            for index, op in key.collection:
                flag = {"GET": "R", "PUT": "U"}.get(op.method)
                if flag and flag not in rec["flags"]:
                    rec["flags"][flag] = op
                else:
                    rec["actions"].append((index, op))
        entities[key.segs] = rec
        if key.item:
            item_index[key.segs + ("{}",)] = key.segs

    ids = {}
    for segs, rec in entities.items():
        eid = _slug(segs)
        if eid in ids:
            raise GraphError(f"entities {ids[eid]!r} and {'/' + '/'.join(segs)!r} share id {eid!r}")
        ids[eid] = "/" + "/".join(segs)
        rec["id"] = eid
    by_segs = {segs: rec["id"] for segs, rec in entities.items()}

    for segs, rec in entities.items():
        key = rec["key"]
        rec["item_path"] = key.item[0][1].path if key.item else None
        if key.collection:
            rec["collection_path"] = key.collection[0][1].path
        elif key.item:
            rec["collection_path"] = key.item[0][1].path.rsplit("/", 1)[0]
        else:
            rec["collection_path"] = ""
        rec["id_param"] = None
        for _, op in key.item:
            name = _segments(op.path)[-1][1:-1]
            if rec["id_param"] is None:
                rec["id_param"] = name
            elif name != rec["id_param"]:
                warnings.append(
                    f"{rec['id']}: id_param {{{name}}} differs from {{{rec['id_param']}}}; keeping first")

    can_create = {rec["id"]: "C" in rec["flags"] for rec in entities.values()}
    login_like = {rec["id"]: bool(_LOGIN_LIKE.search("/".join(segs).lower())) for segs, rec in entities.items()}
    singular_ids = {}
    for rec in entities.values():
        singular_ids.setdefault(singular(rec["id"].rsplit("-", 1)[-1]), []).append(rec["id"])

    edges = {rec["id"]: {} for rec in entities.values()}  # src -> {dst: {"parent"|"body"}}
    llm = {rec["id"]: set() for rec in entities.values()}

    def link(src, dst, kind):
        if src == dst or login_like[dst]:
            return
        if not can_create[dst]:
            marker = f"llm:create-{dst}"
            if marker not in llm[src]:
                llm[src].add(marker)
                warnings.append(f"{src}: depends on {dst} which has no create operation")
            return
        edges[src].setdefault(dst, set()).add(kind)

    for segs in sorted(entities, key=lambda s: entities[s]["id"]):
        rec = entities[segs]
        rec["parent_id"] = by_segs[rec["parent"]] if rec["parent"] is not None else None
        if rec["parent_id"] is not None:
            link(rec["id"], rec["parent_id"], "parent")
        create = rec["flags"].get("C")
        if create is not None and create.body is not None:
            for field in create.body.fields:
                if not field.required or field.path != field.name:
                    continue
                m = _ID_FIELD.match(field.name)
                if m:
                    for target in sorted(singular_ids.get(m.group(1).lower(), ())):
                        link(rec["id"], target, "body")

    ids_sorted = sorted(edges)
    adj = {s: set(d) for s, d in edges.items()}
    for comp in _tarjan(ids_sorted, adj):
        if len(comp) < 2:
            continue
        members = set(comp)
        for src in sorted(members):
            for dst in sorted(edges[src]):
                if dst in members and "body" in edges[src][dst]:
                    edges[src][dst].discard("body")
                    if not edges[src][dst]:
                        del edges[src][dst]
        warnings.append(f"dependency cycle among {', '.join(sorted(members))}; body-field edges dropped")

    deps = {s: set(d) for s, d in edges.items()}
    order = _topo(ids_sorted, deps)
    if len(order) != len(ids_sorted):
        raise GraphError("dependency cycle remains after dropping body-field edges")
    pos = {i: n for n, i in enumerate(order)}

    def closure(start):
        seen = set()
        todo = list(deps[start])
        while todo:
            cur = todo.pop()
            if cur not in seen:
                seen.add(cur)
                todo.extend(deps[cur])
        return sorted(seen, key=pos.__getitem__)

    built = {}
    for rec in entities.values():
        eid = rec["id"]
        flags = rec["flags"]
        built[eid] = Entity(
            id=eid,
            collection_path=rec["collection_path"],
            item_path=rec["item_path"],
            id_param=rec["id_param"],
            parent=rec["parent_id"],
            ops={f: flags[f].operation_id for f in _FLAGS if f in flags},
            actions=tuple(o.operation_id for _, o in sorted(rec["actions"], key=lambda p: p[0])),
            singleton=rec["singleton"],
            lifecycle="C" in flags and "R" in flags,
            id_candidate=_id_candidate(spec, flags.get("C"), rec["id_param"], eid),
            depends_on=tuple(sorted(deps[eid], key=pos.__getitem__)),
            needs=tuple(closure(eid)) + tuple(sorted(llm[eid])),
        )
    return Graph(
        entities=tuple(built[i] for i in order),
        order=tuple(order),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def to_dict(graph):
    def plain(e):
        return {
            "id": e.id, "collection_path": e.collection_path, "item_path": e.item_path,
            "id_param": e.id_param, "parent": e.parent, "ops": dict(e.ops),
            "actions": list(e.actions), "singleton": e.singleton, "lifecycle": e.lifecycle,
            "id_candidate": dict(e.id_candidate) if e.id_candidate else None,
            "depends_on": list(e.depends_on), "needs": list(e.needs),
        }

    return {
        "version": 1,
        "entities": [plain(e) for e in graph.entities],
        "order": list(graph.order),
        "warnings": list(graph.warnings),
    }


def op_owner(graph):
    owner = {}
    for e in graph.entities:
        for op_id in (*e.ops.values(), *e.actions):
            owner[op_id] = e.id
    return owner
