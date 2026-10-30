import copy
import unittest

from test_cases import derive, graph, ir, load, profile, validate
from tests import support


def build_spec(name):
    with support.in_skill_dir():
        doc = load.load_doc(support.spec_fixture(name))
    spec = ir.build_ir(doc, name, "sha")
    return spec, graph.build_graph(spec)


def load_named(name):
    with support.in_skill_dir():
        return profile.resolve(load.load_profile(f"profiles/{name}.yaml"))


def pipeline(spec, g, prof, scope=None):
    cases = derive.derive(spec, g, prof, scope) + profile.profile_cases(spec, g, prof)
    return derive.order_cases(profile.apply(cases, spec, g, prof, scope), spec, g)


class ApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.graph = build_spec("oas3.yaml")

    def by_id(self, prof, **kw):
        return {c["id"]: c for c in pipeline(self.spec, self.graph, prof, **kw)}

    def test_msp_fills_code_and_body_generic_does_not(self):
        cid = "widgets.createWidget.body.name.maxLength.plus1"
        msp = self.by_id(load_named("msp"))
        self.assertEqual(msp[cid]["expected"]["code"], "INVALID_REQUEST")
        self.assertEqual(
            msp["widgets.createWidget.auth._.auth.missing"]["expected"]["body"], {"message": "Unauthorized"})
        generic = self.by_id(profile.resolve(None))
        self.assertIsNone(generic[cid]["expected"]["code"])
        self.assertIsNone(generic["widgets.createWidget.auth._.auth.missing"]["expected"]["body"])

    def test_messages_only_when_asserted(self):
        cid = "widgets.createWidget.body.name.maxLength.plus1"
        raw = {"error": {"assert_messages": True,
                         "messages": {"maxLength": "Should be at most {n} characters long"}}}
        got = self.by_id(profile.resolve(raw))[cid]["expected"]["violations"]
        self.assertEqual(got, [{"field": "name", "message": "Should be at most 50 characters long"}])
        off = self.by_id(profile.resolve({"error": {"messages": raw["error"]["messages"]}}))
        self.assertEqual(off[cid]["expected"]["violations"], [{"field": "name"}])

    def test_unknown_fields_reject_adds_root_case(self):
        spec, g = build_spec("oas3-min.json")
        prof = profile.resolve({"error": {"unknown_fields": "reject"}})
        cases = {c["id"]: c for c in pipeline(spec, g, prof)}
        added = cases["items.createItem.body._.additionalProperties.unknown"]
        self.assertEqual(added["source"], "profile")
        self.assertIn("profile", added["tags"])
        self.assertEqual(added["needs"], [])
        self.assertEqual(added["expected"]["status"], 400)
        self.assertNotIn("items.createItem.body._.additionalProperties.unknown",
                         self.by_id(profile.resolve(None)))
        widget = self.by_id(prof)["widgets.createWidget.body._.additionalProperties.unknown"]
        self.assertEqual(widget["source"], "spec")

    def test_reject_respects_exclude(self):
        spec, g = build_spec("oas3-min.json")
        prof = profile.resolve({"error": {"unknown_fields": "reject"}, "exclude": ["POST /items"]})
        self.assertFalse([c for c in pipeline(spec, g, prof) if c["operation"]["operationId"] == "createItem"])

    def test_scoped_equals_filtered_full(self):
        spec, g = build_spec("oas3-min.json")
        prof = profile.resolve({"error": {"unknown_fields": "reject"}})
        full = pipeline(spec, g, prof)
        for scope in (derive.Scope(frozenset({"items"}), None), derive.Scope(None, frozenset({"createItem"}))):
            self.assertEqual(pipeline(spec, g, prof, scope), [c for c in full if derive.in_scope(c, scope)])

    def test_input_not_mutated(self):
        prof = load_named("msp")
        cases = derive.derive(self.spec, self.graph, prof)
        before = copy.deepcopy(cases)
        profile.apply(cases, self.spec, self.graph, prof)
        self.assertEqual(cases, before)

    def test_cross_tenant_code_follows_status(self):
        msp = self.by_id(load_named("msp"))
        rep = self.by_id(load_named("rep"))
        self.assertEqual(msp["widgets.getWidget.op._.tenant.cross"]["expected"]["code"], "NOT_FOUND")
        self.assertIsNone(rep["widgets.getWidget.op._.tenant.cross"]["expected"]["code"])


class ProfileCasesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.graph = build_spec("oas3.yaml")

    def cases(self, raw):
        return profile.profile_cases(self.spec, self.graph, profile.resolve(raw))

    def test_auth_matrix(self):
        got = self.cases({"auth_matrix": [{"ops": "DELETE *", "actor": "account", "expect": 403}]})
        self.assertEqual([c["id"] for c in got], ["widgets.deleteWidget.op._.matrix.account"])
        c = got[0]
        self.assertEqual((c["kind"], c["actor"], c["priority"], c["technique"], c["source"], c["auth"]),
                         ("FORBIDDEN_PERMISSION", "account", "P1", "auth-matrix", "profile", "valid"))
        self.assertEqual(c["expected"]["status"], 403)

    def test_msp_tenant(self):
        got = profile.profile_cases(self.spec, self.graph, load_named("msp"))
        ops = {c["operation"]["operationId"] for c in got if c["kind"] == "CROSS_TENANT"}
        self.assertEqual(ops, {"getWidget", "updateWidget", "deleteWidget", "archiveWidget", "getPart"})
        c = next(c for c in got if c["operation"]["operationId"] == "getPart")
        self.assertEqual((c["rule"], c["actor"], c["technique"], c["expected"]["status"]),
                         ("tenant.cross", "account", "owasp-api1", 404))

    def test_conflicts(self):
        got = self.cases({"conflicts": {"POST /v1/{tenantId}/widgets": ["name"]}})
        self.assertEqual(len(got), 1)
        c = got[0]
        self.assertEqual((c["kind"], c["field"], c["rule"], c["priority"], c["expected"]["status"]),
                         ("DUPLICATE", "name", "conflict.name", "P2", 409))

    def test_state_machine(self):
        sm = {"widgets": {"field": "kind", "transition_op": "updateWidget",
                          "states": {"SMALL": ["LARGE"], "LARGE": []}}}
        got = self.cases({"state_machines": sm})
        self.assertEqual([c["rule"] for c in got], ["state.LARGE_to_SMALL"])
        c = got[0]
        self.assertEqual((c["kind"], c["field"], c["input"]["body"], c["technique"], c["expected"]["status"]),
                         ("STATE_CONFLICT", "kind", {"kind": "SMALL"}, "state-transition", 409))
        self.assertEqual(self.cases({"state_machines": {"nope": sm["widgets"]}}), [])


class WholePipelineTests(unittest.TestCase):
    def test_invariants_clean_under_example_profiles(self):
        spec, g = build_spec("oas3.yaml")
        for name in ("msp", "rep"):
            prof = load_named(name)
            self.assertEqual(validate.invariants(pipeline(spec, g, prof), spec), [], name)

    def test_generic_yaml_is_defaults(self):
        with support.in_skill_dir():
            self.assertEqual(profile.resolve(load.load_profile("profiles/generic.yaml")), profile.resolve(None))


if __name__ == "__main__":
    unittest.main()
