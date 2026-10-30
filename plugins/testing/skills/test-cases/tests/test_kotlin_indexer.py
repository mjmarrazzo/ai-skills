import unittest

from test_cases import index, ir, load
from test_cases.indexers import kotlin_restassured as kra
from tests.support import FIXTURES, spec_fixture

ROOT = FIXTURES / "kotlin"
GLOBS = ["**/src/test/**/*.kt", "**/src/test/**/*.java"]
POST_TEST = "src/test/kotlin/com/example/widgets/WidgetsPostTest.kt"


def _ctx():
    doc = load.load_doc(str(FIXTURES / "specs" / "oas3.yaml"))
    spec = ir.build_ir(doc, spec_fixture("oas3.yaml"), "sha")
    ops = tuple((o.method.upper(), o.path) for o in spec.operations)
    return index.IndexContext(ops, "/{stage}/widgets-svc", ("*TestBase", "*Support"))


class KotlinIndexerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rels = load.discover_tests(str(ROOT), GLOBS, [])
        cls.sources = load.read_sources(str(ROOT), rels)
        cls.indexer = kra.KotlinRestAssuredIndexer()
        cls.ctx = _ctx()
        cls.out = cls.indexer.index(cls.sources, cls.ctx)
        cls.files = {f["path"]: f for f in cls.out["files"]}
        cls.post = {m["name"]: m for m in cls.files[POST_TEST]["methods"]}
        cls.post_lines = next(s.text for s in cls.sources if s.path == POST_TEST).split("\n")

    def line_of(self, needle):
        return next(i for i, t in enumerate(self.post_lines, 1) if needle in t)

    def check(self, name, op, statuses, stub=None):
        m = self.post[name]
        self.assertEqual([c["op"] for c in m["calls"]], [op] if op else [], name)
        self.assertEqual(m["statuses"], statuses, name)
        self.assertEqual(m["stub"], stub, name)
        return m

    def test_output_key_order(self):
        self.assertEqual(
            list(self.out),
            ["version", "indexer", "path_constants", "unused_path_constants", "files"],
        )
        self.assertEqual(self.out["version"], 1)
        self.assertEqual(self.out["indexer"], "kotlin-restassured")
        self.assertEqual(list(self.files[POST_TEST]), ["path", "class", "excluded", "display_name", "methods"])
        self.assertEqual(
            list(self.post["createWidget_ok"]),
            ["name", "line", "end_line", "annotations", "factory", "display_name", "stub", "calls", "statuses"],
        )
        self.assertEqual(list(self.post["createWidget_ok"]["calls"][0]), ["verb", "expr", "path", "op", "line"])

    def test_files_sorted_and_methods_in_line_order(self):
        paths = [f["path"] for f in self.out["files"]]
        self.assertEqual(paths, sorted(paths))
        lines = [m["line"] for m in self.files[POST_TEST]["methods"]]
        self.assertEqual(lines, sorted(lines))
        self.assertEqual(len(lines), 13)

    def test_paths_file_without_class_is_omitted(self):
        self.assertFalse(any(p.endswith("Paths.kt") for p in self.files))

    def test_row1_ok(self):
        m = self.check("createWidget_ok", "POST /v1/{tenantId}/widgets", [201])
        self.assertEqual(m["calls"][0]["verb"], "POST")
        self.assertEqual(m["calls"][0]["expr"], "Paths.WIDGETS")
        self.assertEqual(m["calls"][0]["path"], "/v1/{tenantId}/widgets")
        self.assertEqual(m["annotations"], ["Test"])
        self.assertFalse(m["factory"])

    def test_row2_http_status_constant(self):
        self.check("createWidget_nameTooLong", "POST /v1/{tenantId}/widgets", [400])

    def test_row3_disabled(self):
        m = self.check("createWidget_disabled", "POST /v1/{tenantId}/widgets", [201], "disabled")
        self.assertEqual(m["annotations"], ["Disabled", "Test"])

    def test_row4_manual(self):
        self.check("createWidget_manual", "POST /v1/{tenantId}/widgets", [201], "manual")

    def test_row5_empty(self):
        self.check("createWidget_empty", None, [], "empty")

    def test_row6_no_status_assert(self):
        self.check("createWidget_noAssert", "POST /v1/{tenantId}/widgets", [], "no_status_assert")

    def test_row7_unmapped_status_kept(self):
        self.check("createWidget_teapot", "POST /v1/{tenantId}/widgets", [418])

    def test_row8_factory(self):
        m = self.check("createWidget_invalidNames", "POST /v1/{tenantId}/widgets", [400])
        self.assertTrue(m["factory"])
        self.assertEqual(m["annotations"], ["TestFactory"])

    def test_row9_backtick_name(self):
        self.check("archive returns 200", "POST /v1/{tenantId}/widgets/{widgetId}/archive", [200])

    def test_row10_helper_hides_call(self):
        self.check("createWidget_viaHelper", None, [201])

    def test_row11_braces_in_string_and_comment(self):
        m = self.check("getWidget_braceInString", "GET /v1/{tenantId}/widgets/{widgetId}", [404])
        start = self.line_of("fun getWidget_braceInString")
        self.assertEqual(m["line"], start)
        self.assertEqual(m["end_line"], start + 4)
        self.assertEqual(self.post_lines[m["end_line"] - 1].strip(), "}")

    def test_row12_function_path(self):
        self.check("createPart_fn", "POST /v1/{tenantId}/parts", [201])

    def test_row13_same_line_and_non_path_get_ignored(self):
        m = self.check("getWidget_sameLine", "GET /v1/{tenantId}/widgets/{widgetId}", [404])
        self.assertEqual(len(m["calls"]), 1)
        self.assertEqual(m["line"], self.line_of("@Test fun getWidget_sameLine() {"))
        self.assertEqual(m["calls"][0]["expr"], "Paths.WIDGET")

    def test_java_method(self):
        f = self.files["src/test/java/com/example/widgets/PartsGetTest.java"]
        self.assertEqual(f["class"], "PartsGetTest")
        (m,) = f["methods"]
        self.assertEqual(m["name"], "getPart_notFound")
        self.assertEqual([c["op"] for c in m["calls"]], ["GET /v1/{tenantId}/parts/{partId}"])
        self.assertEqual(m["calls"][0]["path"], "/v1/{}/parts/{}")
        self.assertEqual(m["statuses"], [404])

    def test_path_constants(self):
        pc = self.out["path_constants"]
        self.assertEqual(pc["Paths.WIDGET_ARCHIVE"], "/v1/{tenantId}/widgets/{widgetId}/archive")
        self.assertEqual(pc["Paths.parts"], "/v1/{tenant}/parts")
        self.assertEqual(pc["Paths.UNRESOLVED"], "{?}/x")
        self.assertEqual(pc["Paths.WIDGETS"], "/v1/{tenantId}/widgets")
        self.assertEqual(list(pc), sorted(pc))

    def test_unused_path_constants(self):
        self.assertEqual(self.out["unused_path_constants"], ["Paths.LEGACY", "Paths.UNRESOLVED"])

    def test_excluded_class(self):
        base = next(f for p, f in self.files.items() if p.endswith("WidgetTestBase.kt"))
        self.assertEqual(base["excluded"], "*TestBase")
        self.assertIsNone(self.files[POST_TEST]["excluded"])

    def test_class_level_disabled(self):
        f = next(f for p, f in self.files.items() if p.endswith("LegacyWidgetsTest.kt"))
        self.assertEqual(f["methods"][0]["name"], "old")
        self.assertEqual(f["methods"][0]["stub"], "disabled")

    def test_detect(self):
        self.assertTrue(self.indexer.detect(["a.kt"]))
        self.assertTrue(self.indexer.detect(["x/B.java"]))
        self.assertFalse(self.indexer.detect(["a.py"]))

    def test_source_order_does_not_matter(self):
        rev = self.indexer.index(list(reversed(self.sources)), self.ctx)
        self.assertEqual(rev, self.out)
        self.assertEqual(list(rev), list(self.out))

    def test_registered(self):
        self.assertIsInstance(index.INDEXERS["kotlin-restassured"], kra.KotlinRestAssuredIndexer)
        self.assertEqual(kra.HTTP_STATUS["SC_NOT_FOUND"], 404)


class MaskHardeningTests(unittest.TestCase):
    def test_java_block_comments_do_not_nest(self):
        src = "/* see /* x */\nclass A {}\n"
        self.assertIn("class A", kra._mask(src, nested=False))
        self.assertNotIn("class A", kra._mask(src, nested=True))

    def test_raw_string_with_extra_closing_quotes(self):
        masked = kra._mask('val s = """x"""" + y\nval z = 1', True)
        self.assertIn("+ y", masked)
        self.assertNotIn("x", masked.split("+")[0])

    def test_first_arg_bounded_by_method_body(self):
        src = 'class T {\n @Test fun a() { get("/x" \n}\n @Test fun b() { post("/y") }\n}\n'
        out = kra.KotlinRestAssuredIndexer().index([index.SourceFile("T.kt", src)], _ctx())
        a = out["files"][0]["methods"][0]
        self.assertTrue(all("post" not in c["expr"] for c in a["calls"]))

    def test_fun_keyword_followed_by_tab(self):
        src = 'class T {\n @Test fun\tt() { get("/x") }\n}\n'
        out = kra.KotlinRestAssuredIndexer().index([index.SourceFile("T.kt", src)], _ctx())
        self.assertEqual(out["files"][0]["methods"][0]["line"], 2)


if __name__ == "__main__":
    unittest.main()
