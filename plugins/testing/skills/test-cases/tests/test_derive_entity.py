import copy
import unittest

from test_cases import derive, graph, ir, load, profile, validate
from tests import support
from tests.test_derive_ops import FIXTURES, build


def steps_of(case):
    return [(s["operationId"], s["expect"], s["capture"]) for s in case["steps"]]


class Oas3Lifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.graph, cls.profile, cls.cases = build("oas3.yaml")
        cls.by_id = {c["id"]: c for c in cls.cases}

    def get(self, cid):
        self.assertTrue(cid in self.by_id, f"{cid!r} not found")
        return self.by_id[cid]

    def test_widget_crud(self):
        c = self.get("widgets.createWidget.lifecycle._.lifecycle.crud")
        self.assertEqual(steps_of(c), [
            ("createWidget", 201, {"widgetId": "id"}),
            ("getWidget", 200, None),
            ("updateWidget", 200, None),
            ("getWidget", 200, None),
            ("deleteWidget", 204, None),
            ("getWidget", 404, None),
        ])
        self.assertEqual(list(c["steps"][0]), ["operationId", "expect", "capture"])
        self.assertEqual(c["expected"]["status"], 404)
        self.assertEqual((c["kind"], c["loc"], c["priority"], c["technique"]),
                         ("LIFECYCLE", "lifecycle", "P1", "lifecycle"))
        self.assertFalse(c["negative"])
        self.assertIsNone(c["field"])
        self.assertEqual(c["operation"]["operationId"], "createWidget")
        self.assertEqual(c["specRef"], self.spec.operations[1].spec_ref)
        self.assertNotIn("llm:id-threading", c["needs"])

    def test_widget_delete_twice(self):
        c = self.get("widgets.createWidget.lifecycle._.lifecycle.delete_twice")
        self.assertEqual(steps_of(c), [
            ("createWidget", 201, {"widgetId": "id"}),
            ("deleteWidget", 204, None),
            ("deleteWidget", 404, None),
        ])
        self.assertEqual((c["kind"], c["priority"], c["negative"]), ("DELETE_TWICE", "P2", True))
        self.assertEqual(c["expected"]["status"], 404)

    def test_parts_crud_only(self):
        c = self.get("parts.createPart.lifecycle._.lifecycle.crud")
        self.assertEqual(steps_of(c), [
            ("createPart", 201, {"partId": "partId"}),
            ("getPart", 200, None),
        ])
        self.assertEqual(c["needs"], ["widgets"])
        self.assertEqual(c["expected"]["status"], 200)
        self.assertNotIn("parts.createPart.lifecycle._.lifecycle.delete_twice", self.by_id)

    def test_no_lifecycle_without_create_and_read(self):
        for entity in ("health", "shapes"):
            self.assertEqual([i for i in self.by_id if i.startswith(f"{entity}.") and ".lifecycle." in i], [])

    def test_excluded_create_drops_lifecycle(self):
        _, _, _, cases = build("oas3.yaml", {"exclude": ["POST *"]})
        self.assertEqual([c["id"] for c in cases if c["loc"] == "lifecycle"], [])

    def test_excluded_delete_drops_tail_and_twice(self):
        _, _, _, cases = build("oas3.yaml", {"exclude": ["DELETE *"]})
        by_id = {c["id"]: c for c in cases}
        crud = by_id["widgets.createWidget.lifecycle._.lifecycle.crud"]
        self.assertEqual([s["operationId"] for s in crud["steps"]],
                         ["createWidget", "getWidget", "updateWidget", "getWidget"])
        self.assertNotIn("widgets.createWidget.lifecycle._.lifecycle.delete_twice", by_id)

    def test_lifecycle_sorts_last_within_entity(self):
        ids = [c["id"] for c in self.cases if c["id"].startswith("widgets.")]
        last = max(i for i, x in enumerate(ids) if ".lifecycle." in x)
        first = min(i for i, x in enumerate(ids) if ".lifecycle." in x)
        self.assertTrue(all(".lifecycle." in x for x in ids[first:last + 1]))

    def test_scope_filters_lifecycle(self):
        scope = derive.Scope(entities=frozenset({"parts"}))
        cases = derive.derive(self.spec, self.graph, self.profile, scope)
        self.assertEqual([c["id"] for c in cases if c["loc"] == "lifecycle"],
                         ["parts.createPart.lifecycle._.lifecycle.crud"])

    def test_inputs_not_mutated(self):
        before = copy.deepcopy(ir.to_dict(self.spec)), copy.deepcopy(graph.to_dict(self.graph))
        derive.derive(self.spec, self.graph, self.profile)
        self.assertEqual(before, (ir.to_dict(self.spec), graph.to_dict(self.graph)))


class IdThreading(unittest.TestCase):
    DOC = {
        "openapi": "3.0.3",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/things": {"post": {"operationId": "createThing", "responses": {"201": {"description": "ok"}}}},
            "/things/{thingId}": {
                "get": {
                    "operationId": "getThing",
                    "parameters": [{"name": "thingId", "in": "path", "required": True,
                                    "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    def test_no_response_schema_needs_llm(self):
        spec = ir.build_ir(copy.deepcopy(self.DOC), "inline", "sha")
        g = graph.build_graph(spec)
        cases = derive.derive(spec, g, profile.resolve(None))
        crud = next(c for c in cases if c["rule"] == "lifecycle.crud")
        self.assertIsNone(crud["steps"][0]["capture"])
        self.assertIn("llm:id-threading", crud["needs"])
        self.assertEqual(crud["needs"].count("llm:id-threading"), 1)


class Invariants(unittest.TestCase):
    def test_invariants_clean_on_every_fixture(self):
        for name in FIXTURES:
            with self.subTest(name):
                spec, _, _, cases = build(name)
                self.assertEqual(validate.invariants(cases, spec), [])


if __name__ == "__main__":
    unittest.main()
