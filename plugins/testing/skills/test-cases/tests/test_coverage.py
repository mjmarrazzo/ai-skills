import json
import unittest

from test_cases import coverage, index, ir, load, profile, render
from tests import support
from tests.test_kotlin_indexer import GLOBS, ROOT, _ctx
from tests.test_profile_cases import build_spec, pipeline
from tests.test_render import view_for

POST = "src/test/kotlin/com/example/widgets/WidgetsPostTest.kt"
WIDGETS = "POST /v1/{tenantId}/widgets"


def _entry(method, line, http_method, path, kind, field, status):
    return {"method": method, "line": line, "http_method": http_method, "path": path,
            "kind": kind, "field": field, "status": status, "actor": None,
            "factory_entry": None, "confidence": "high"}


def _doc(tests, file=POST):
    return {"version": 1, "file": file, "class": "WidgetsPostTest", "tests": tests}


class CoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, g = build_spec("oas3.yaml")
        cls.cases = pipeline(cls.spec, g, profile.resolve(None))
        rels = load.discover_tests(str(ROOT), GLOBS, [])
        sources = load.read_sources(str(ROOT), rels)
        cls.raw = index.INDEXERS["kotlin-restassured"].index(sources, _ctx())
        cls.methods = {m["name"]: m for f in cls.raw["files"] for m in f["methods"]}

    def line(self, name):
        return self.methods[name]["line"]

    def full(self, tests):
        return coverage.diff(self.cases, self.spec, self.raw, [_doc(tests)])

    def too_long(self, **kw):
        row = ("createWidget_nameTooLong", self.line("createWidget_nameTooLong"), "POST",
               "/v1/{t}/widgets", "LENGTH_INVALID", "name", 400)
        return _entry(*(kw.get(k, v) for k, v in zip(
            ("method", "line", "http_method", "path", "kind", "field", "status"), row)))

    def test_matching_entry_covers_case(self):
        ok = _entry("createWidget_ok", self.line("createWidget_ok"), "POST", "/v1/{t}/widgets",
                    "HAPPY_FULL", None, 201)
        cov = self.full([ok, self.too_long()])
        got = cov["cases"]["widgets.createWidget.body.name.maxLength.plus1"]
        self.assertEqual(got, {"status": "covered", "tests": ["%s:%d" % (POST, self.line("createWidget_nameTooLong"))]})
        self.assertEqual(cov["mode"], "full")
        self.assertEqual(list(cov), ["version", "mode", "cases", "operations", "test_drift", "stubs", "unattributed"])

    def test_stub_method_makes_case_stub_not_covered(self):
        row = _entry("createWidget_disabled", self.line("createWidget_disabled"), "POST", "/v1/{t}/widgets",
                     "LENGTH_INVALID", "name", 400)
        got = self.full([row])["cases"]["widgets.createWidget.body.name.maxLength.plus1"]
        self.assertEqual(got["status"], "stub")
        self.assertEqual(got["tests"], ["%s:%d" % (POST, self.line("createWidget_disabled"))])

    def test_real_test_wins_over_stub(self):
        stub = _entry("createWidget_disabled", self.line("createWidget_disabled"), "POST", "/v1/{t}/widgets",
                      "LENGTH_INVALID", "name", 400)
        got = self.full([stub, self.too_long()])["cases"]["widgets.createWidget.body.name.maxLength.plus1"]
        self.assertEqual(got["status"], "covered")
        self.assertEqual(len(got["tests"]), 1)

    def test_query_kind_equivalence(self):
        row = _entry("createWidget_ok", self.line("createWidget_ok"), "GET", "/v1/{t}/widgets",
                     "RANGE_INVALID", "limit", 400)
        cov = self.full([row])
        self.assertEqual(cov["cases"]["widgets.listWidgets.query.limit.maximum.plus1"]["status"], "covered")
        body = _entry("createWidget_ok", self.line("createWidget_ok"), "POST", "/v1/{t}/widgets",
                      "RANGE_INVALID", "name", 400)
        self.assertEqual(self.full([body])["unattributed"][0]["test"], "%s:%d" % (POST, self.line("createWidget_ok")))

    def test_auth_case_matches_null_field(self):
        row = _entry("getWidget_sameLine", self.line("getWidget_sameLine"), "GET", "/v1/{t}/widgets/{id}",
                     "AUTH_MISSING", None, 401)
        cov = self.full([row])
        self.assertEqual(cov["cases"]["widgets.getWidget.auth._.auth.missing"]["status"], "covered")
        auth = cov["operations"]["GET /v1/{tenantId}/widgets/{widgetId}"]["auth"]
        rules = [c["rule"] for c in self.cases if c["loc"] == "auth" and c["operation"]["operationId"] == "getWidget"]
        self.assertEqual(auth["total"], len(rules))
        self.assertEqual(auth["missing"], [r for r in rules if r != "auth.missing"])

    def test_null_field_never_matches_named_field_case(self):
        row = _entry("createWidget_nameTooLong", self.line("createWidget_nameTooLong"), "POST", "/v1/{t}/widgets",
                     "LENGTH_INVALID", None, 400)
        cov = self.full([row])
        self.assertEqual(cov["cases"]["widgets.createWidget.body.name.maxLength.plus1"]["status"], "gap")
        self.assertEqual(len(cov["unattributed"]), 1)

    def test_status_in_case_status_list(self):
        row = _entry("createWidget_nameTooLong", self.line("createWidget_nameTooLong"), "POST", "/v1/{t}/widgets",
                     "RESOURCE_LIMIT", "note", 413)
        cov = self.full([row])
        self.assertEqual(cov["cases"]["widgets.createWidget.body.note.unbounded.oversize"]["status"], "covered")
        self.assertEqual(cov["unattributed"], [])

    def test_undeclared_status_is_drift_and_unattributed(self):
        row = _entry("createWidget_teapot", self.line("createWidget_teapot"), "POST", "/v1/{t}/widgets",
                     "HAPPY_FULL", None, 418)
        cov = self.full([row])
        ref = "%s:%d" % (POST, self.line("createWidget_teapot"))
        self.assertEqual([(d["type"], d["test"], d["status"]) for d in cov["test_drift"]
                          if d["type"] != "unused_path_constant"], [("undeclared_status", ref, 418)])
        self.assertEqual([u["test"] for u in cov["unattributed"]], [ref])

    def test_unknown_endpoint_is_drift_only(self):
        row = _entry("createWidget_ok", self.line("createWidget_ok"), "GET", "/nope", "HAPPY_FULL", None, 200)
        cov = self.full([row])
        self.assertIn("unknown_endpoint", [d["type"] for d in cov["test_drift"]])
        self.assertEqual(cov["unattributed"], [])

    def test_excluded_class_entries_are_ignored(self):
        base = "src/test/kotlin/com/example/widgets/WidgetTestBase.kt"
        row = _entry("x", 3, "GET", "/nope", "HAPPY_FULL", None, 200)
        cov = coverage.diff(self.cases, self.spec, self.raw, [_doc([row], base)])
        self.assertEqual([d for d in cov["test_drift"] if d["type"] == "unknown_endpoint"], [])

    def test_full_mode_status_codes_come_from_entries(self):
        cov = self.full([self.too_long()])
        self.assertEqual(cov["operations"][WIDGETS]["status_codes"],
                         {"documented": ["201", "400", "409"], "covered": ["400"]})

    def test_operation_keyword_summary(self):
        cov = self.full([self.too_long()])
        kw = cov["operations"][WIDGETS]["keywords"]
        mine = [c for c in self.cases if c["operation"]["operationId"] == "createWidget"
                and c["loc"] in ("body", "path", "query", "header")]
        self.assertEqual(kw["total"], len(mine))
        self.assertEqual(kw["covered"], 1)
        self.assertEqual(kw["missing"], [c["id"] for c in mine
                                         if c["id"] != "widgets.createWidget.body.name.maxLength.plus1"])
        self.assertEqual(list(cov["operations"]), ["%s %s" % (o.method, o.path) for o in self.spec.operations])


class RawOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, g = build_spec("oas3.yaml")
        cls.cases = pipeline(cls.spec, g, profile.resolve(None))
        sources = load.read_sources(str(ROOT), load.discover_tests(str(ROOT), GLOBS, []))
        cls.raw = index.INDEXERS["kotlin-restassured"].index(sources, _ctx())
        cls.cov = coverage.diff(cls.cases, cls.spec, cls.raw, None)

    def test_mode_and_all_gap(self):
        self.assertEqual(self.cov["mode"], "raw-only")
        self.assertEqual({v["status"] for v in self.cov["cases"].values()}, {"gap"})
        self.assertEqual(len(self.cov["cases"]), len(self.cases))

    def test_status_codes_from_non_stub_methods(self):
        sc = self.cov["operations"]["POST /v1/{tenantId}/widgets"]["status_codes"]
        self.assertEqual(sc["covered"], ["201", "400"])

    def test_undeclared_418(self):
        rows = [d for d in self.cov["test_drift"] if d["type"] == "undeclared_status"]
        self.assertIn(("POST", "/v1/{tenantId}/widgets", 418), [(d["method"], d["path"], d["status"]) for d in rows])

    def test_stubs_sorted(self):
        stubs = self.cov["stubs"]
        self.assertEqual([s["test"] for s in stubs], sorted(s["test"] for s in stubs))
        reasons = {s["reason"] for s in stubs}
        self.assertEqual(reasons, {"disabled", "manual", "empty", "no_status_assert"})
        names = {s["test"].rsplit(":", 1)[0] for s in stubs}
        self.assertNotIn("src/test/kotlin/com/example/widgets/WidgetTestBase.kt", names)

    def test_unused_path_constants(self):
        rows = [d for d in self.cov["test_drift"] if d["type"] == "unused_path_constant"]
        self.assertEqual([d["detail"] for d in rows], ["Paths.LEGACY", "Paths.UNRESOLVED"])
        self.assertEqual(set(rows[0]), {"type", "test", "method", "path", "status", "detail"})

    def test_empty_files_all_gap(self):
        raw = {"version": 1, "indexer": "x", "path_constants": {}, "unused_path_constants": [], "files": []}
        cov = coverage.diff(self.cases, self.spec, raw, None)
        self.assertEqual({v["status"] for v in cov["cases"].values()}, {"gap"})
        self.assertEqual(cov["test_drift"], [])

    def test_deterministic(self):
        again = coverage.diff(self.cases, self.spec, self.raw, None)
        self.assertEqual(json.dumps(self.cov), json.dumps(again))

    def test_report_shows_missing_cell(self):
        _, entities, _ = view_for()
        text = render.report(entities, self.cov)
        row = next(l for l in text.splitlines() if l.startswith("| `POST /v1/{tenantId}/widgets` |"))
        self.assertIn("missing [", row)


class NormPathTests(unittest.TestCase):
    def test_norm_path(self):
        self.assertEqual(coverage.norm_path("/v1/{tenantId}/w/{id}"), "/v1/{}/w/{}")
        self.assertEqual(coverage.norm_path("/v1/{}/w"), "/v1/{}/w")

    def test_kind_equiv_shape(self):
        self.assertEqual(list(coverage.KIND_EQUIV), ["INVALID_QUERY_PARAM"])
        self.assertIsInstance(coverage.KIND_EQUIV["INVALID_QUERY_PARAM"], frozenset)


if __name__ == "__main__":
    unittest.main()
