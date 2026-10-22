import re
import unittest

from test_cases import derive, graph, ir, load, profile, rules, validate
from tests import support


def build(name, raw_profile=None):
    with support.in_skill_dir():
        doc = load.load_doc(support.spec_fixture(name))
    spec = ir.build_ir(doc, name, "sha")
    g = graph.build_graph(spec)
    prof = profile.resolve(raw_profile)
    return spec, g, prof, derive.derive(spec, g, prof)


def inline(schema_props, extra=None, prof=None):
    doc = {
        "openapi": "3.0.0", "info": {"title": "t"},
        "paths": {"/things": {"post": {
            "operationId": "createThing",
            "requestBody": {"content": {"application/json": {"schema": {
                "type": "object", "properties": schema_props, **(extra or {}),
            }}}},
            "responses": {"201": {"description": "ok"}},
        }}},
    }
    spec = ir.build_ir(doc, "inline", "sha")
    g = graph.build_graph(spec)
    return derive.derive(spec, g, profile.resolve(prof))


class Oas3Fields(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.graph, cls.profile, cls.cases = build("oas3.yaml")
        cls.by_id = {c["id"]: c for c in cls.cases}

    def case(self, suffix):
        return self.by_id[f"widgets.createWidget.body.{suffix}"]

    def test_max_length_plus1(self):
        c = self.case("name.maxLength.plus1")
        self.assertEqual(c["kind"], "LENGTH_INVALID")
        self.assertTrue(c["negative"])
        self.assertEqual(c["input"]["body"], {"name": "<<str:51>>"})
        self.assertEqual(c["expected"]["status"], 400)
        self.assertEqual(c["expected"]["violations"], [{"field": "name"}])
        self.assertEqual(c["specRef"], "#/components/schemas/WidgetCreate/properties/name/maxLength")

    def test_required_missing(self):
        c = self.case("name.required.missing")
        self.assertEqual(c["input"]["remove"], ["name"])
        self.assertEqual(c["input"]["body"], {})

    def test_dedupe_keeps_first(self):
        self.assertIn("widgets.createWidget.body.name.required.empty", self.by_id)
        self.assertNotIn("widgets.createWidget.body.name.minLength.minus1", self.by_id)

    def test_nested_object_delta(self):
        c = self.case("dimensions.width.minimum.minus1")
        self.assertEqual(c["input"]["body"], {"dimensions": {"width": 0}})

    def test_array_item_deltas(self):
        self.assertEqual(self.case("tags_items.maxLength.plus1")["input"]["body"], {"tags": ["<<str:21>>"]})
        c = self.case("parts_items.id.format.short")
        self.assertEqual(c["input"]["body"], {"parts": [{"id": "123e4567-e89b-12d3-a456-42661417400"}]})
        self.assertEqual(len(c["input"]["body"]["parts"][0]["id"]), 35)

    def test_money_bump(self):
        price = [c for c in self.cases if c["field"] == "price"]
        self.assertTrue(price)
        self.assertEqual({c["priority"] for c in price}, {"P1"})

    def test_update_negatives_expect_422(self):
        row_ids = {r.id for r in rules.RULES} | {"type.wrong"} | {
            f"format.{n}" for v in rules.FORMAT_INVALID.values() for n, _ in v}
        checked = 0
        for c in self.cases:
            if (c["operation"]["operationId"] == "updateWidget" and c["negative"] and c["loc"] == "body"
                    and c["rule"] in row_ids and c["rule"] != "readOnly.sent"):
                self.assertEqual(c["expected"]["status"], 422, c["id"])
                checked += 1
        self.assertGreater(checked, 20)

    def test_read_only_sent_unknown_mode(self):
        c = self.by_id["widgets.updateWidget.body.id.readOnly.sent"]
        self.assertEqual(c["expected"]["status"], [200, 422])
        self.assertEqual(c["expected"]["not_persisted"], ["id"])

    def test_query_rekinding(self):
        c = self.by_id["widgets.listWidgets.query.limit.maximum.plus1"]
        self.assertEqual(c["kind"], "INVALID_QUERY_PARAM")
        self.assertEqual(c["rule"], "maximum.plus1")
        self.assertEqual(c["input"]["query"], {"limit": 101})
        self.assertEqual(c["expected"]["violations"], [{"field": "limit"}])
        self.assertEqual(self.by_id["widgets.listWidgets.query.limit.minimum.min"]["kind"], "RANGE_BOUNDARY_VALID")

    def test_query_skips_required_rows(self):
        self.assertFalse([c for c in self.cases if c["loc"] == "query" and c["rule"].startswith("required.")])

    def test_enum_each(self):
        c = self.case("kind.enum.each.SMALL")
        self.assertFalse(c["negative"])
        self.assertEqual(c["input"]["body"], {"kind": "SMALL"})

    def test_pattern_llm(self):
        ids = [c["id"] for c in self.cases if c["field"] == "sku"]
        self.assertFalse([i for i in ids if ".pattern.empty" in i or "out_of_class" in i])
        llm = [c for c in self.cases if c["field"] == "sku" and c["rule"] == "pattern.llm"
               and c["operation"]["operationId"] == "createWidget"]
        self.assertEqual(len(llm), 1)
        self.assertEqual(llm[0]["input"]["body"], {"sku": "<<pattern-negative>>"})
        self.assertIn("llm:pattern-sample", llm[0]["needs"])

    def test_unanchored_pattern(self):
        ids = [c["id"] for c in self.cases if c["field"] == "code"]
        self.assertFalse([i for i in ids if "lead_space" in i or "trail_space" in i])
        oc = self.case("code.pattern.out_of_class")
        value = oc["input"]["body"]["code"]
        self.assertIsNone(re.search("[A-Z]{3}", value))

    def test_needs(self):
        part = [c for c in self.cases if c["operation"]["operationId"] == "createPart"][0]
        self.assertEqual(part["needs"], ["widgets"])
        upd = self.by_id["widgets.updateWidget.body.name.maxLength.plus1"]
        self.assertEqual(upd["needs"], ["widgets"])
        self.assertEqual(self.case("name.maxLength.plus1")["needs"], [])

    def test_undocumented_status_tag(self):
        self.assertIn("undocumented-status", self.by_id["widgets.listWidgets.query.limit.maximum.plus1"]["tags"])
        self.assertNotIn("undocumented-status", self.case("name.maxLength.plus1")["tags"])

    def test_excluded_ops_skipped(self):
        _, _, _, cases = build("oas3.yaml", {"exclude": ["DELETE *"]})
        self.assertFalse([c for c in cases if c["operation"]["operationId"] == "deleteWidget"])

    def test_key_order(self):
        for c in self.cases:
            self.assertEqual(tuple(c), derive.CASE_KEYS)
            self.assertEqual(tuple(c["operation"]), ("method", "path", "operationId"))
            self.assertEqual(tuple(c["input"]), (
                "body", "remove", "body_mode", "raw", "content_type", "path", "query", "headers"))
            self.assertEqual(tuple(c["expected"]), ("status", "code", "violations", "body", "not_persisted"))
            self.assertEqual(tuple(c["coverage"]), ("status", "tests"))

    def test_deterministic(self):
        again = derive.derive(self.spec, self.graph, self.profile)
        self.assertEqual(again, self.cases)

    def test_invariants_hold(self):
        self.assertEqual(validate.invariants(self.cases, self.spec), [])

    def test_order(self):
        order = list(self.graph.order)
        idx = [order.index(c["id"].split(".")[0]) for c in self.cases]
        self.assertEqual(idx, sorted(idx))

    def test_scope(self):
        scoped = derive.derive(self.spec, self.graph, self.profile,
                               derive.Scope(frozenset({"widgets"}), frozenset({"createWidget"})))
        self.assertTrue(scoped)
        self.assertEqual({c["operation"]["operationId"] for c in scoped}, {"createWidget"})
        self.assertEqual(scoped, [c for c in self.cases if c["operation"]["operationId"] == "createWidget"])

    def test_inputs_not_shared(self):
        first = {c["id"]: c for c in derive.derive(self.spec, self.graph, self.profile)}
        first["widgets.createWidget.body.tags_items.maxLength.plus1"]["input"]["body"]["tags"].append("x")
        again = {c["id"]: c for c in derive.derive(self.spec, self.graph, self.profile)}
        self.assertEqual(
            again["widgets.createWidget.body.tags_items.maxLength.plus1"]["input"]["body"],
            {"tags": ["<<str:21>>"]})


class Swagger2Fields(unittest.TestCase):
    def test_read_only_sent_generic(self):
        _, _, _, cases = build("swagger2.yaml")
        c = {x["id"]: x for x in cases}["accounts.postAccounts.body.id.readOnly.sent"]
        self.assertEqual(c["priority"], "P1")
        self.assertEqual(c["expected"]["status"], [200, 400])
        self.assertEqual(c["expected"]["not_persisted"], ["id"])

    def test_read_only_modes(self):
        for mode, status, persisted in (("ignore", 200, ["id"]), ("reject", 400, [])):
            _, _, _, cases = build("swagger2.yaml", {"error": {"unknown_fields": mode}})
            c = {x["id"]: x for x in cases}["accounts.postAccounts.body.id.readOnly.sent"]
            self.assertEqual(c["expected"]["status"], status)
            self.assertEqual(c["expected"]["not_persisted"], persisted)


class InlineCases(unittest.TestCase):
    def test_enum_slug_hash(self):
        cases = inline({"v": {"type": "string", "enum": ["a b", "a_b"]}})
        ids = [c["id"] for c in cases if c["rule"] == "enum.each"]
        self.assertEqual(len(ids), 2)
        self.assertTrue(re.search(r"\.a_b_[0-9a-f]{6}$", ids[0]))
        self.assertTrue(ids[1].endswith(".enum.each.a_b"))

    def test_ids_are_names_not_positions(self):
        before = {c["id"] for c in inline({"v": {"type": "string", "maxLength": 5}})}
        after = {c["id"] for c in inline({"w": {"type": "string"}, "v": {"type": "string", "maxLength": 5}})}
        self.assertTrue(before <= after)

    def test_status_ignores_range_keys(self):
        doc = {
            "openapi": "3.0.0", "info": {"title": "t"},
            "paths": {"/things": {"post": {
                "operationId": "createThing",
                "requestBody": {"content": {"application/json": {"schema": {
                    "type": "object", "properties": {"v": {"type": "string", "maxLength": 5}}}}}},
                "responses": {"default": {"description": "x"}, "2XX": {"description": "y"}},
            }}},
        }
        spec = ir.build_ir(doc, "inline", "sha")
        cases = derive.derive(spec, graph.build_graph(spec), profile.resolve(None))
        c = {x["id"]: x for x in cases}["things.createThing.body.v.maxLength.max"]
        self.assertEqual(c["expected"]["status"], 200)
        self.assertIn("undocumented-status", c["tags"])

    def test_array_min_items_padding(self):
        cases = inline({"a": {"type": "array", "minItems": 3, "items": {"type": "string", "maxLength": 2}}})
        c = {x["id"]: x for x in cases}["things.createThing.body.a_items.maxLength.plus1"]
        self.assertEqual(c["input"]["body"], {"a": ["<<items:1>>", "<<items:1>>", "<<str:3>>"]})

    def test_header_param_rows(self):
        doc = {
            "openapi": "3.0.0", "info": {"title": "t"},
            "paths": {"/things": {"get": {
                "operationId": "listThings",
                "parameters": [{"name": "X-Trace", "in": "header", "required": True,
                                "schema": {"type": "string", "maxLength": 4}}],
                "responses": {"200": {"description": "ok"}},
            }}},
        }
        spec = ir.build_ir(doc, "inline", "sha")
        cases = derive.derive(spec, graph.build_graph(spec), profile.resolve(None))
        rows = sorted(c["rule"] for c in cases if c["loc"] == "header")
        self.assertEqual(rows, ["required.empty", "required.missing"])
        miss = [c for c in cases if c["rule"] == "required.missing"][0]
        self.assertEqual(miss["input"]["headers"], {"X-Trace": None})
        self.assertEqual(miss["specRef"], "#/paths/~1things/get/parameters/0")
        self.assertEqual(miss["expected"]["violations"], [{"field": "X-Trace"}])


if __name__ == "__main__":
    unittest.main()
