import collections
import os
import tempfile
import unittest

from test_cases import ENGINE, graph, ir, load, render, rules, yamlfmt
from tests import support
from tests.test_derive_ops import build

META = {
    "spec": {"source": "oas3.yaml", "version": "3.0.1", "sha256": "abc"},
    "profile": {"name": "generic", "source": None},
    "error_shape": {"code_key": "code", "violations_key": "violations",
                    "field_key": "propertyPath", "message_key": "message", "extra": "dropped"},
}


def view_for(name="oas3.yaml", raw_profile=None):
    spec, g, prof, cases = build(name, raw_profile)
    by_entity = collections.defaultdict(list)
    owner = graph.op_owner(g)
    for c in cases:
        by_entity[owner[c["operation"]["operationId"]]].append(c)
    docs = [{"entity": e, "cases": by_entity.get(e, [])} for e in g.order]
    return cases, render.entities_view(docs, ir.to_dict(spec), graph.to_dict(g)), g


class CasesFile(unittest.TestCase):
    def test_key_order_and_round_trip(self):
        cases, _, _ = view_for()
        with support.in_skill_dir():
            text = render.cases_file("widgets", cases[:3], META)
            with tempfile.TemporaryDirectory() as d:
                p = os.path.join(d, "w.yaml")
                with open(p, "w") as f:
                    f.write(text)
                back = load.load_doc(p)
        self.assertEqual(list(back), ["version", "engine", "spec", "profile", "error_shape", "entity", "cases"])
        self.assertEqual(back["engine"], ENGINE)
        self.assertEqual(list(back["error_shape"]),
                         ["code_key", "violations_key", "field_key", "message_key"])
        self.assertEqual(back["cases"], cases[:3])
        self.assertEqual(back["spec"], META["spec"])

    def test_graph_file_round_trips(self):
        _, _, g = view_for()
        self.assertEqual(render.graph_file(g), yamlfmt.dump(graph.to_dict(g)))

    def test_json_file(self):
        self.assertEqual(render.json_file({"a": "é"}), '{\n  "a": "é"\n}\n')


class Report(unittest.TestCase):
    def test_no_coverage_counts_match_hand_count(self):
        cases, entities, _ = view_for()
        text = render.report(entities, None)
        self.assertIn("## widgets", text)
        mine = [c for c in cases if c["kind"] == "LENGTH_INVALID" and c["id"].startswith("widgets.")]
        self.assertTrue(mine)
        counts = collections.Counter(c["priority"] for c in mine)
        row = "| LENGTH_INVALID | %d | %d | %d |" % tuple(counts[p] for p in ("P1", "P2", "P3"))
        self.assertIn(row, text.split("## widgets")[1].split("\n## ")[0])
        total = len(cases)
        self.assertIn("%d cases (P1 %d / P2 %d / P3 %d)" % (
            total, *(sum(1 for c in cases if c["priority"] == p) for p in ("P1", "P2", "P3"))), text)
        self.assertNotIn("coverage:", text.splitlines()[2])

    def test_kind_rows_follow_kinds_order_and_skip_zero(self):
        _, entities, _ = view_for()
        text = render.report(entities, None)
        for block in text.split("\n## ")[1:]:
            rows = [l.split("|")[1].strip() for l in block.splitlines()
                    if l.startswith("| ") and l.split("|")[1].strip() in rules.KINDS]
            self.assertEqual(rows, sorted(rows, key=rules.KINDS.index))
        self.assertNotIn("| SMOKE |", text)

    def test_coverage_row(self):
        _, entities, _ = view_for()
        cov = {"mode": "full", "operations": {
            "POST /v1/{tenantId}/widgets": {
                "status_codes": {"documented": ["200", "400", "409"], "covered": ["200", "400"]},
                "keywords": {"total": 12, "covered": 11,
                             "missing": ["widgets.createWidget.body.price.multipleOf.off"]},
                "auth": {"total": 2, "covered": 1, "missing": ["auth.malformed"]},
            },
            "GET /v1/{tenantId}/widgets": {
                "status_codes": {"documented": ["200"], "covered": ["200"]},
                "keywords": {"total": 3, "covered": 3, "missing": []},
                "auth": {"total": 2, "covered": 2, "missing": []},
            }}, "test_drift": [], "stubs": [], "unattributed": []}
        text = render.report(entities, cov)
        self.assertIn(
            "| `POST /v1/{tenantId}/widgets` | 2/3 missing [409] | "
            "11/12 missing [widgets.createWidget.body.price.multipleOf.off] | "
            "1/2 missing [auth.malformed] |", text)
        self.assertIn("| `GET /v1/{tenantId}/widgets` | 1/1 | 3/3 | 2/2 |", text)
        self.assertIn("| Operation | Status codes | Keywords | Auth |", text)
        self.assertIn(" · coverage: full", text.splitlines()[2])

    def test_drift_section_is_scoped_to_entity_ops(self):
        _, entities, _ = view_for()
        cov = {"mode": "full", "operations": {}, "stubs": [], "unattributed": [], "test_drift": [
            {"type": "undeclared_status", "test": "A.kt:9", "method": "POST",
             "path": "/v1/{tenantId}/widgets", "status": 418, "detail": "not documented"},
            {"type": "unknown_endpoint", "test": "B.kt:3", "method": "GET",
             "path": "/nowhere", "status": 200, "detail": "no such op"}]}
        text = render.report(entities, cov)
        self.assertIn("### Drift", text)
        self.assertIn("A.kt:9", text)
        self.assertNotIn("B.kt:3", text)

    def test_unsupported_lists_oneof(self):
        _, entities, _ = view_for()
        text = render.report(entities, None)
        self.assertIn("### Unsupported", text)
        self.assertIn("oneOf at ", text)

    def test_excluded_lists_delete(self):
        _, entities, _ = view_for(raw_profile={"exclude": ["DELETE *"]})
        text = render.report(entities, None)
        self.assertIn("### Excluded", text)
        self.assertIn("deleteWidget", text.split("### Excluded")[1])

    def test_section_order_and_needs_review(self):
        entity = {"id": "x", "ops": [
            {"operationId": "o", "method": "GET", "path": "/x", "unsupported": ["oneOf at #/a"], "excluded": True}],
            "cases": [{"id": "x.o.llm", "kind": "HAPPY_FULL", "priority": "P1", "source": "llm",
                       "coverage": {"status": "stub", "tests": []}}]}
        text = render.report([entity], None)
        heads = [l for l in text.splitlines() if l.startswith("### ")]
        self.assertEqual(heads, ["### Stubs", "### Unsupported", "### Excluded", "### Needs review"])

    def test_empty(self):
        text = render.report([], None)
        self.assertIn("No operations found in spec.", text)
        self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"))

    def test_single_trailing_newline_and_deterministic(self):
        _, entities, _ = view_for()
        a, b = render.report(entities, None), render.report(entities, None)
        self.assertEqual(a, b)
        self.assertTrue(a.endswith("\n") and not a.endswith("\n\n"))


class EntitiesView(unittest.TestCase):
    def test_shape_and_order(self):
        cases, entities, g = view_for()
        self.assertEqual([e["id"] for e in entities], list(g.order))
        e = next(e for e in entities if e["id"] == "widgets")
        self.assertEqual(list(e), ["id", "ops", "cases"])
        self.assertEqual(list(e["ops"][0]), ["operationId", "method", "path", "unsupported", "excluded"])
        self.assertFalse(any(o["excluded"] for o in e["ops"]))
        self.assertEqual(sum(len(x["cases"]) for x in entities), len(cases))


if __name__ == "__main__":
    unittest.main()
