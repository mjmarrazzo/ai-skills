import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_cases import cli, derive, graph, ir, load, render
from tests import support

OAS3 = "tests/fixtures/specs/oas3.yaml"
MIN = "tests/fixtures/specs/oas3-min.json"
KOTLIN = "tests/fixtures/kotlin"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with support.in_skill_dir(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def tree(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def write_inline(tmp, name, paths):
    doc = {"openapi": "3.0.1", "info": {"title": "t", "version": "1"}, "paths": paths}
    path = Path(tmp) / name
    path.write_text(json.dumps(doc))
    return str(path)


class DeriveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.full = str(Path(cls.tmp.name) / "full")
        cls.result = run("derive", OAS3, "-o", cls.full)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_files_and_stats_line(self):
        code, _, err = self.result
        self.assertEqual(code, 0, err)
        self.assertEqual(
            sorted(tree(self.full)),
            sorted(["widgets.yaml", "parts.yaml", "health.yaml", "shapes.yaml", "graph.yaml", "ir.json"]))
        self.assertTrue(re.search(r"^entities=4 ops=10 cases=\d+ warnings=\d+$", err, re.M), err)

    def test_source_as_given_and_no_absolute_paths(self):
        doc = load.load_doc(Path(self.full) / "widgets.yaml")
        self.assertEqual(doc["spec"]["source"], OAS3)
        for blob in tree(self.full).values():
            self.assertNotIn(str(support.SKILL_DIR).encode(), blob)
        self.assertNotIn(str(support.SKILL_DIR), self.result[2])

    def test_byte_identical_runs(self):
        with tempfile.TemporaryDirectory() as t:
            run("derive", OAS3, "-o", t)
            self.assertEqual(tree(t), tree(self.full))

    def test_entity_scope_matches_full_run(self):
        with tempfile.TemporaryDirectory() as t:
            code, _, _ = run("derive", OAS3, "--entity", "widgets", "-o", t)
            self.assertEqual(code, 0)
            self.assertEqual(sorted(tree(t)), ["graph.yaml", "ir.json", "widgets.yaml"])
            self.assertEqual(load.load_doc(Path(t) / "widgets.yaml")["cases"],
                             load.load_doc(Path(self.full) / "widgets.yaml")["cases"])

    def test_op_forms_agree(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertEqual(run("derive", OAS3, "--op", "GET /v1/{tenantId}/widgets/{widgetId}", "-o", a)[0], 0)
            self.assertEqual(run("derive", OAS3, "--op", "getWidget", "-o", b)[0], 0)
            self.assertEqual(tree(a), tree(b))
            cases = load.load_doc(Path(a) / "widgets.yaml")["cases"]
            self.assertTrue(cases)
            self.assertEqual({c["operation"]["operationId"] for c in cases}, {"getWidget"})


class DeriveErrors(unittest.TestCase):
    def test_unknown_entity_lists_valid(self):
        with tempfile.TemporaryDirectory() as t:
            code, _, err = run("derive", OAS3, "--entity", "nope", "-o", t)
        self.assertEqual(code, 2)
        self.assertIn("widgets", err)

    def test_unknown_op(self):
        with tempfile.TemporaryDirectory() as t:
            code, _, err = run("derive", OAS3, "--op", "nope", "-o", t)
        self.assertEqual(code, 2)
        self.assertIn("getWidget", err)

    def test_missing_spec(self):
        self.assertEqual(run("derive", "tests/fixtures/specs/absent.yaml")[0], 2)

    def test_usage_error(self):
        self.assertEqual(run("derive")[0], 2)

    def test_invalid_profile_writes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            bad = Path(t) / "bad.yaml"
            bad.write_text("version: 1\nname: x\nbogus_key: 1\n")
            out = Path(t) / "out"
            code, _, err = run("derive", OAS3, "--profile", str(bad), "-o", str(out))
            self.assertEqual(code, 1)
            self.assertIn("bogus_key", err)
            self.assertFalse(out.exists() and any(out.iterdir()))

    def test_no_yaml_backend(self):
        with tempfile.TemporaryDirectory() as t, \
                patch.object(load, "_pyyaml", return_value=None), \
                patch.object(load, "_ruby_exe", return_value=None):
            code, _, err = run("derive", OAS3, "-o", t)
            self.assertEqual(code, 2)
            self.assertIn("no YAML backend", err)
            self.assertEqual(run("derive", MIN, "-o", t)[0], 0)

    def test_empty_spec(self):
        with tempfile.TemporaryDirectory() as t:
            spec = write_inline(t, "empty.json", {})
            out = str(Path(t) / "out")
            code, _, err = run("derive", spec, "-o", out)
            self.assertEqual(code, 0, err)
            self.assertIn("warning:", err)
            self.assertEqual(sorted(tree(out)), ["graph.yaml", "ir.json"])
            code, _, _ = run("render", "--cases", out)
            self.assertEqual(code, 0)
            self.assertIn("No operations found in spec.", (Path(out) / "README.md").read_text())

    def test_invariant_failure_writes_nothing(self):
        with support.in_skill_dir():
            spec = ir.build_ir(load.load_doc(OAS3), OAS3, "x")
            op = spec.operations[0]
        dup = derive.make_case(
            id="widgets.dup", title="t", operation={"method": op.method, "path": op.path,
                                                    "operationId": op.operation_id},
            kind="HAPPY_FULL", loc="op", rule="happy.full", negative=False, technique="x",
            priority="P1", specRef=op.spec_ref, source="spec", expected={"status": 200})
        with tempfile.TemporaryDirectory() as t, patch.object(derive, "derive", return_value=[dup, dup]):
            out = Path(t) / "out"
            code, _, err = run("derive", OAS3, "-o", str(out))
            self.assertEqual(code, 1)
            self.assertIn("duplicate id", err)
            self.assertFalse(out.exists())


class GraphTests(unittest.TestCase):
    def test_stdout_matches_render(self):
        code, out, _ = run("graph", OAS3)
        self.assertEqual(code, 0)
        with support.in_skill_dir():
            spec = ir.build_ir(load.load_doc(OAS3), OAS3, load.sha256_file(OAS3))
        self.assertEqual(out, render.graph_file(graph.build_graph(spec)))

    def test_graph_error(self):
        with tempfile.TemporaryDirectory() as t:
            op = {"get": {"operationId": "x", "responses": {"200": {"description": "ok"}}}}
            spec = write_inline(t, "clash.json", {"/a_b": op, "/a-b": {"get": {**op["get"], "operationId": "y"}}})
            code, out, err = run("graph", spec)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("GraphError", err)


class IndexTests(unittest.TestCase):
    def test_kotlin(self):
        with tempfile.TemporaryDirectory() as t:
            raw = Path(t) / "raw.json"
            code, _, err = run("index", KOTLIN, "--spec", OAS3, "-o", str(raw))
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(raw.read_text())["indexer"], "kotlin-restassured")

    def test_bogus_indexer(self):
        self.assertEqual(run("index", KOTLIN, "--spec", OAS3, "--indexer", "bogus")[0], 2)

    def test_empty_root(self):
        with tempfile.TemporaryDirectory() as t:
            code, out, _ = run("index", t, "--spec", OAS3)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["files"], [])


class CoverageAndValidate(unittest.TestCase):
    def test_raw_only_coverage_and_readme(self):
        with tempfile.TemporaryDirectory() as t:
            cases, raw = str(Path(t) / "cases"), str(Path(t) / "raw.json")
            self.assertEqual(run("derive", OAS3, "-o", cases)[0], 0)
            self.assertEqual(run("index", KOTLIN, "--spec", OAS3, "-o", raw)[0], 0)
            code, _, err = run("coverage", "--cases", cases, "--spec", OAS3, "--raw", raw)
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads((Path(cases) / "coverage.json").read_text())["mode"], "raw-only")
            self.assertTrue((Path(cases) / "README.md").is_file())

    def test_full_coverage_checks_index_docs(self):
        with tempfile.TemporaryDirectory() as t:
            cases, raw = str(Path(t) / "cases"), "tests/fixtures/llm/index-raw.json"
            run("derive", OAS3, "-o", cases)
            good = "tests/fixtures/llm/index-valid.json"
            code, _, err = run("coverage", "--cases", cases, "--spec", OAS3, "--raw", raw, "--index", good)
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads((Path(cases) / "coverage.json").read_text())["mode"], "full")
            code, _, err = run("coverage", "--cases", cases, "--spec", OAS3, "--raw", raw,
                               "--index", "tests/fixtures/llm/index-bad-line.json")
            self.assertEqual(code, 1)

    def test_validate_profile(self):
        self.assertEqual(run("validate", "--schema", "profile", "profiles/msp.yaml")[0], 0)

    def test_validate_enrich_semantic_errors(self):
        bad = "tests/fixtures/llm/enrich-bad-quote.json"
        code, _, err = run("validate", "--schema", "enrich", bad, "--spec", OAS3)
        self.assertEqual(code, 1)
        self.assertTrue(all(line.startswith(bad + ":") for line in err.splitlines() if "entities=" not in line))

    def test_validate_requires_companions(self):
        self.assertEqual(run("validate", "--schema", "enrich", "tests/fixtures/llm/enrich-valid.json")[0], 2)
        self.assertEqual(run("validate", "--schema", "index", "tests/fixtures/llm/index-valid.json")[0], 2)

    def test_validate_cases_with_invariants(self):
        with tempfile.TemporaryDirectory() as t:
            run("derive", OAS3, "-o", t)
            code, _, err = run("validate", "--schema", "cases", str(Path(t) / "widgets.yaml"), "--spec", OAS3)
        self.assertEqual(code, 0, err)


class Launcher(unittest.TestCase):
    def test_parse_via_subprocess(self):
        r = subprocess.run([sys.executable, "scripts/tc.py", "parse", MIN],
                           cwd=support.SKILL_DIR, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("operations", json.loads(r.stdout))


if __name__ == "__main__":
    unittest.main()
