import json
import unittest

from test_cases import graph, ir, load
from tests import support


def build(name):
    with support.in_skill_dir():
        doc = load.load_doc(support.spec_fixture(name))
    return graph.build_graph(ir.build_ir(doc, name, "sha"))


def inline(paths, schemas=None):
    doc = {"openapi": "3.0.0", "info": {"title": "t"}, "paths": paths}
    if schemas:
        doc["components"] = {"schemas": schemas}
    return graph.build_graph(ir.build_ir(doc, "inline", "sha"))


def ents(g):
    return {e.id: e for e in g.entities}


def op(method_ops, body_required=None):
    out = {}
    for method, op_id in method_ops.items():
        node = {"operationId": op_id, "responses": {"200": {"description": "ok"}}}
        if method == "post" and body_required is not None:
            node["requestBody"] = {"content": {"application/json": {"schema": {
                "type": "object",
                "required": list(body_required),
                "properties": {n: {"type": "string"} for n in body_required},
            }}}}
        out[method] = node
    return out


class Oas3Graph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = build("oas3.yaml")
        cls.e = ents(cls.g)

    def test_order(self):
        self.assertEqual(self.g.order, ("health", "shapes", "widgets", "parts"))
        self.assertEqual(tuple(e.id for e in self.g.entities), self.g.order)

    def test_widgets(self):
        w = self.e["widgets"]
        self.assertEqual(w.ops, {
            "C": "createWidget", "L": "listWidgets", "R": "getWidget",
            "U": "updateWidget", "D": "deleteWidget",
        })
        self.assertEqual(w.actions, ("archiveWidget",))
        self.assertTrue(w.lifecycle)
        self.assertEqual(w.id_param, "widgetId")
        self.assertEqual(w.id_candidate, {"field": "id", "source": "spec-candidate"})
        self.assertEqual(w.collection_path, "/v1/{tenantId}/widgets")
        self.assertEqual(w.item_path, "/v1/{tenantId}/widgets/{widgetId}")

    def test_parts(self):
        p = self.e["parts"]
        self.assertEqual(p.depends_on, ("widgets",))
        self.assertEqual(p.needs, ("widgets",))
        self.assertEqual(p.id_candidate["field"], "partId")
        self.assertIsNone(p.parent)

    def test_health(self):
        h = self.e["health"]
        self.assertTrue(h.singleton)
        self.assertEqual(h.ops, {"R": "health"})
        self.assertFalse(h.lifecycle)

    def test_shapes(self):
        s = self.e["shapes"]
        self.assertEqual(s.ops, {"C": "createShape"})
        self.assertFalse(s.lifecycle)
        self.assertIsNone(s.id_candidate)

    def test_op_owner(self):
        owner = graph.op_owner(self.g)
        self.assertEqual(owner["archiveWidget"], "widgets")
        self.assertEqual(owner["health"], "health")
        self.assertEqual(len(owner), 10)

    def test_deterministic(self):
        again = build("oas3.yaml")
        self.assertEqual(json.dumps(graph.to_dict(self.g)), json.dumps(graph.to_dict(again)))

    def test_to_dict_shape(self):
        d = graph.to_dict(self.g)
        self.assertEqual(list(d), ["version", "entities", "order", "warnings"])
        self.assertEqual(d["version"], 1)
        self.assertEqual(d["order"], list(self.g.order))
        self.assertIsInstance(d["entities"][0]["depends_on"], list)


class Singular(unittest.TestCase):
    def test_table(self):
        cases = {
            "addresses": "address", "statuses": "status", "categories": "category",
            "boxes": "box", "churches": "church", "class": "class", "widgets": "widget",
            "data": "data",
        }
        for word, want in cases.items():
            self.assertEqual(graph.singular(word), want, word)


class Swagger2Graph(unittest.TestCase):
    def test_actions_and_notes(self):
        g = build("swagger2.yaml")
        e = ents(g)
        self.assertIn("uploadAvatar", e["accounts"].actions)
        self.assertEqual(e["accounts-notes"].parent, "accounts")
        self.assertEqual(e["accounts-notes"].needs, ("accounts",))


class InlineGraph(unittest.TestCase):
    def test_post_only_parentless_stays_entity(self):
        g = inline({"/v1/{tenant}/consent/accept": op({"post": "accept"})})
        self.assertIn("consent-accept", ents(g))
        self.assertEqual(g.order, ("consent-accept",))

    def test_login_like_never_a_target(self):
        g = inline({
            "/auth/token": op({"post": "mkToken"}),
            "/orders": op({"post": "createOrder"}, body_required=["tokenId"]),
        })
        self.assertEqual(ents(g)["orders"].depends_on, ())
        self.assertEqual(ents(g)["orders"].needs, ())

    def test_body_field_edge(self):
        g = inline({
            "/orgs": op({"post": "createOrg"}),
            "/orders": op({"post": "createOrder"}, body_required=["orgId"]),
        })
        self.assertEqual(ents(g)["orders"].depends_on, ("orgs",))
        self.assertEqual(g.order, ("orgs", "orders"))

    def test_parent_without_create_marks_llm_need(self):
        g = inline({
            "/orgs/{orgId}": op({"get": "getOrg"}),
            "/orgs/{orgId}/users": op({"post": "createUser", "get": "listUsers"}),
        })
        users = ents(g)["orgs-users"]
        self.assertIn("llm:create-orgs", users.needs)
        self.assertEqual(users.depends_on, ())
        self.assertTrue(any("orgs" in w for w in g.warnings))

    def test_cycle_drops_body_edges(self):
        g = inline({
            "/a": op({"post": "createA"}, body_required=["bId"]),
            "/b": op({"post": "createB"}, body_required=["aId"]),
        })
        e = ents(g)
        self.assertEqual(e["a"].depends_on, ())
        self.assertEqual(e["b"].depends_on, ())
        self.assertEqual(g.order, ("a", "b"))
        self.assertTrue(g.warnings)

    def test_slug_collision(self):
        with self.assertRaises(graph.GraphError):
            inline({"/a_b": op({"post": "x"}), "/a-b": op({"post": "y"})})

    def test_root_id(self):
        g = inline({"/": op({"get": "root"})})
        self.assertEqual(g.order, ("root",))

    def test_singleton_extra_ops_become_actions(self):
        g = inline({"/profile/config": op({"get": "getCfg", "put": "putCfg", "delete": "delCfg"})})
        e = ents(g)["profile-config"]
        self.assertEqual(e.ops, {"R": "getCfg", "U": "putCfg"})
        self.assertEqual(e.actions, ("delCfg",))

    def test_id_param_mismatch_warns(self):
        g = inline({
            "/things": op({"post": "c"}),
            "/things/{a}": op({"get": "g"}),
            "/things/{b}": op({"put": "u"}),
        })
        e = ents(g)["things"]
        self.assertEqual(e.id_param, "a")
        self.assertTrue(any("id_param" in w or "{b}" in w for w in g.warnings))

    def test_nested_fold_chains_to_non_folded_ancestor(self):
        g = inline({
            "/w": op({"post": "cw"}),
            "/w/{id}": op({"get": "gw"}),
            "/w/{id}/x/y": op({"post": "xy"}),
        })
        self.assertEqual(ents(g)["w"].actions, ("xy",))
        self.assertEqual(graph.op_owner(g)["xy"], "w")


if __name__ == "__main__":
    unittest.main()
