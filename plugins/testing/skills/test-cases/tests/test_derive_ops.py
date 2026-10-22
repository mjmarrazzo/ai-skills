import unittest

from test_cases import derive, graph, ir, load, profile, rules, validate, yamlfmt
from tests import support

FIXTURES = ("swagger2.yaml", "oas3.yaml", "oas3-min.json", "oas3-added-field.yaml")
STRICT = {"error": {"unknown_fields": "reject"}, "tenant": {"param": "tenantId"}}


def build(name, raw_profile=None):
    with support.in_skill_dir():
        doc = load.load_doc(support.spec_fixture(name))
    spec = ir.build_ir(doc, name, "sha")
    g = graph.build_graph(spec)
    prof = profile.resolve(raw_profile)
    return spec, g, prof, derive.derive(spec, g, prof)


class Oas3Ops(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.graph, cls.profile, cls.cases = build("oas3.yaml")
        cls.by_id = {c["id"]: c for c in cls.cases}

    def get(self, cid):
        self.assertTrue(cid in self.by_id, f"{cid!r} not found")
        return self.by_id[cid]

    def has(self, cid):
        return cid in self.by_id

    def ids(self, prefix):
        return [i for i in self.by_id if i.startswith(prefix)]

    def test_happy_rows(self):
        full = self.get("widgets.createWidget.op._.happy.full")
        self.assertEqual((full["kind"], full["priority"], full["negative"]), ("HAPPY_FULL", "P1", False))
        self.assertEqual(full["expected"]["status"], 201)
        self.assertEqual(full["input"]["body"], {})
        mini = self.get("widgets.createWidget.op._.happy.min")
        optional = [f.path for f in self.spec.operations[1].body.fields
                    if not f.required and "." not in f.path and "[]" not in f.path]
        self.assertEqual(mini["input"]["remove"], optional)
        self.assertEqual(mini["priority"], "P2")
        for path in optional:
            c = self.get(f"widgets.createWidget.body.{path}.optional.absent")
            self.assertEqual(c["kind"], "OPTIONAL_ABSENT")
            self.assertEqual(c["input"]["remove"], [path])
            self.assertFalse(c["negative"])

    def test_happy_min_absent_without_optionals(self):
        self.assertFalse(self.has("parts.createPart.op._.happy.min"))
        self.assertTrue(self.has("parts.createPart.op._.happy.full"))

    def test_all_missing(self):
        c = self.get("widgets.createWidget.op._.required.all_missing")
        self.assertEqual(c["input"]["body"], {})
        self.assertEqual(c["input"]["body_mode"], "replace")
        self.assertIsNone(c["field"])
        self.assertEqual(c["kind"], "REQUIRED_MISSING")
        self.assertEqual(c["loc"], "op")

    def test_body_rows(self):
        mal = self.get("widgets.createWidget.op._.body.malformed")
        self.assertEqual((mal["input"]["body_mode"], mal["input"]["raw"]), ("raw", '{"'))
        self.assertEqual(self.get("widgets.createWidget.op._.body.array")["input"]["raw"], "[]")
        empty = self.get("widgets.createWidget.op._.body.empty")
        self.assertEqual((empty["kind"], empty["input"]["body_mode"]), ("EMPTY_BODY", "none"))
        ct = self.get("widgets.createWidget.op._.body.content_type")
        self.assertEqual(ct["input"]["content_type"], "text/plain")
        self.assertEqual(ct["expected"]["status"], 415)
        self.assertEqual(ct["kind"], "WRONG_CONTENT_TYPE")
        self.assertFalse(self.ids("widgets.getWidget.op._.body."))

    def test_oversize(self):
        c = self.get("widgets.createWidget.body.note.unbounded.oversize")
        self.assertEqual(c["expected"]["status"], [400, 413])
        self.assertEqual(c["input"]["body"], {"note": "<<str:10000>>"})
        self.assertEqual((c["kind"], c["priority"], c["technique"]), ("RESOURCE_LIMIT", "P3", "owasp-api4"))
        self.assertFalse(self.has("widgets.createWidget.body.name.unbounded.oversize"))

    def test_root_additional_properties(self):
        c = self.get("widgets.createWidget.body._.additionalProperties.unknown")
        self.assertEqual(c["input"]["body"], {"__unexpected_field__": "x"})
        self.assertIsNone(c["field"])
        self.assertFalse(self.ids("widgets.createWidget.body.role.mass_assignment"))
        self.assertFalse([i for i in self.by_id if ".mass_assignment." in i and "createWidget" in i])
        self.assertTrue([i for i in self.by_id if ".mass_assignment." in i and "createPart" in i])
        self.assertFalse(self.has("parts.createPart.body._.additionalProperties.unknown"))

    def test_oneof_body(self):
        self.assertTrue(self.has("shapes.createShape.op._.happy.full"))
        shape = [c for c in self.cases if c["operation"]["operationId"] == "createShape"]
        self.assertFalse([c for c in shape if c["loc"] == "body"])
        self.assertTrue([c for c in shape if c["loc"] == "auth"])

    def test_path_rows(self):
        mal = self.get("widgets.getWidget.path.widgetId.path.malformed")
        self.assertEqual(mal["input"]["path"], {"widgetId": "not-a-uuid"})
        self.assertEqual(mal["kind"], "INVALID_ID_FORMAT")
        nf = self.get("widgets.getWidget.path.widgetId.path.not_found")
        self.assertEqual(nf["input"]["path"], {"widgetId": "<<nonexistent:widgetId>>"})
        self.assertEqual((nf["kind"], nf["expected"]["status"]), ("NOT_FOUND", 404))
        self.assertTrue(self.has("widgets.getWidget.path.tenantId.path.not_found"))
        self.assertFalse(self.has("widgets.getWidget.path.tenantId.path.malformed"))
        self.assertIn("undocumented-status", self.get("parts.getPart.path.partId.path.not_found")["tags"])
        self.assertNotIn("undocumented-status", nf["tags"])

    def test_tenant_param_excluded(self):
        _, _, _, cases = build("oas3.yaml", {"tenant": {"param": "tenantId"}})
        ids = {c["id"] for c in cases}
        self.assertNotIn("widgets.getWidget.path.tenantId.path.not_found", ids)
        self.assertIn("widgets.getWidget.path.widgetId.path.not_found", ids)

    def test_query_rows(self):
        walk = self.get("widgets.listWidgets.query.cursor.pagination.walk")
        self.assertEqual((walk["kind"], walk["negative"], walk["input"]["query"]), ("PAGINATION", False, {}))
        bad = self.get("widgets.listWidgets.query.cursor.pagination.bad_cursor")
        self.assertEqual(bad["input"]["query"], {"cursor": "not-a-valid-cursor"})
        self.assertEqual(bad["kind"], "INVALID_QUERY_PARAM")
        self.assertEqual(self.get("widgets.listWidgets.query.limit.limit.negative")["input"]["query"], {"limit": -1})
        huge = self.get("widgets.listWidgets.query.limit.limit.huge")
        self.assertEqual((huge["input"]["query"], huge["kind"]), ({"limit": 1000000000}, "RESOURCE_LIMIT"))
        self.assertFalse(self.has("widgets.listWidgets.query.limit.limit.zero"))
        self.assertFalse(self.has("widgets.listWidgets.query.limit.limit.over_max"))
        self.assertTrue(self.has("widgets.listWidgets.query.limit.minimum.minus1"))

    def test_query_missing(self):
        doc = {
            "openapi": "3.0.0", "info": {"title": "t"},
            "paths": {"/things": {"get": {
                "operationId": "listThings",
                "parameters": [{"name": "q", "in": "query", "required": True, "schema": {"type": "string"}}],
                "responses": {"200": {"description": "ok"}},
            }}},
        }
        spec = ir.build_ir(doc, "inline", "sha")
        cases = derive.derive(spec, graph.build_graph(spec), profile.resolve(None))
        c = {x["id"]: x for x in cases}["things.listThings.query.q.query.missing"]
        self.assertEqual(c["input"]["query"], {"q": None})
        self.assertEqual(c["kind"], "INVALID_QUERY_PARAM")
        self.assertEqual(c["expected"]["violations"], [{"field": "q"}])

    def test_auth_rows(self):
        pub = self.get("health.health.auth._.auth.public")
        self.assertEqual((pub["auth"], pub["expected"]["status"], pub["kind"]), ("none", 200, "PUBLIC_REACHABLE"))
        self.assertIn("security", pub["tags"])
        self.assertFalse(pub["negative"])
        self.assertFalse(self.has("health.health.auth._.auth.missing"))
        miss = self.get("widgets.getWidget.auth._.auth.missing")
        mal = self.get("widgets.getWidget.auth._.auth.malformed")
        self.assertEqual((miss["auth"], miss["expected"]["status"], miss["kind"]), ("none", 401, "AUTH_MISSING"))
        self.assertEqual((mal["auth"], mal["expected"]["status"], mal["kind"]), ("malformed", 401, "AUTH_INVALID"))
        self.assertEqual((miss["priority"], miss["technique"]), ("P1", "auth-matrix"))

    def test_needs(self):
        self.assertEqual(self.get("widgets.getWidget.op._.happy.full")["needs"], ["widgets"])
        self.assertEqual(self.get("parts.createPart.op._.happy.full")["needs"], ["widgets"])
        self.assertEqual(self.get("parts.getPart.op._.happy.full")["needs"], ["widgets", "parts"])
        self.assertEqual(self.get("parts.getPart.path.partId.path.not_found")["needs"], ["widgets"])

    def test_spec_refs(self):
        op = next(o for o in self.spec.operations if o.operation_id == "getWidget")
        self.assertEqual(self.get("widgets.getWidget.auth._.auth.missing")["specRef"], op.spec_ref)
        param = next(p for p in op.params if p.name == "widgetId")
        self.assertEqual(self.get("widgets.getWidget.path.widgetId.path.malformed")["specRef"], param.spec_ref)

    def test_pattern_path_param(self):
        def run(pattern):
            doc = {
                "openapi": "3.0.0", "info": {"title": "t"},
                "paths": {"/things/{code}": {"get": {
                    "operationId": "getThing",
                    "parameters": [{"name": "code", "in": "path", "required": True,
                                    "schema": {"type": "string", "pattern": pattern}}],
                    "responses": {"200": {"description": "ok"}},
                }}},
            }
            spec = ir.build_ir(doc, "inline", "sha")
            return {c["rule"] + c["loc"]: c for c in derive.derive(
                spec, graph.build_graph(spec), profile.resolve(None))}

        c = run("^[A-Z]{3}$")["path.malformedpath"]
        self.assertIsNone(__import__("re").search("^[A-Z]{3}$", c["input"]["path"]["code"]))
        llm = run(r"^\p{IsLatin}+$")["path.malformedpath"]
        self.assertEqual(llm["input"]["path"], {"code": "<<pattern-negative>>"})
        self.assertIn("llm:pattern-sample", llm["needs"])

    def test_mass_assignment_modes(self):
        _, _, _, cases = build("oas3-min.json")
        mass = [c for c in cases if c["rule"].startswith("mass_assignment.")]
        self.assertEqual(sorted(c["rule"] for c in mass), sorted(f"mass_assignment.{n}" for n, _ in rules.MASS_ASSIGNMENT_PROBES))
        for c in mass:
            self.assertEqual(c["expected"]["status"], [201, 400])
            self.assertEqual(c["expected"]["not_persisted"], [c["field"]])
            self.assertEqual((c["priority"], c["technique"], c["kind"]), ("P1", "owasp-api3", "MASS_ASSIGNMENT"))
            self.assertEqual(list(c["input"]["body"]), [c["field"]])
        _, _, _, reject = build("oas3-min.json", {"error": {"unknown_fields": "reject"}})
        for c in (c for c in reject if c["rule"].startswith("mass_assignment.")):
            self.assertEqual((c["expected"]["status"], c["expected"]["not_persisted"]), (400, []))


class Invariants(unittest.TestCase):
    def test_every_fixture_and_profile(self):
        for name in FIXTURES:
            for raw in (None, STRICT):
                spec, g, prof, _ = build(name, raw)
                cases = derive.order_cases(derive.derive(spec, g, prof), spec, g)
                label = f"{name} {bool(raw)}"
                self.assertEqual(validate.invariants(cases, spec), [], label)
                for c in cases:
                    self.assertIn(c["kind"], rules.KINDS, label)
                    self.assertNotIn(c["kind"], rules.RESERVED_KINDS, label)
                    self.assertIn(c["rule"], rules.RULE_IDS | {"enum.each"}, c["id"])
                again = derive.derive(spec, g, prof)
                self.assertEqual(yamlfmt.dump(cases), yamlfmt.dump(again), label)

    def test_id_stability(self):
        _, _, _, base = build("oas3.yaml")
        _, _, _, added = build("oas3-added-field.yaml")
        added_by_id = {c["id"]: c for c in added}
        self.assertTrue(base)
        for c in base:
            self.assertIn(c["id"], added_by_id)
            self.assertEqual(c, added_by_id[c["id"]], c["id"])

    def test_scoped_equals_full(self):
        for name in FIXTURES:
            spec, g, prof, full = build(name)
            owners = graph.op_owner(g)
            scopes = [derive.Scope(frozenset({e}), None) for e in g.order]
            scopes += [derive.Scope(None, frozenset({o.operation_id})) for o in spec.operations]
            self.assertTrue(owners)
            for scope in scopes:
                got = derive.derive(spec, g, prof, scope)
                self.assertEqual(got, [c for c in full if derive.in_scope(c, scope)], f"{name} {scope}")


if __name__ == "__main__":
    unittest.main()
