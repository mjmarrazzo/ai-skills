import collections
import json
import os
import tempfile
import unittest

from test_cases import graph, ir, load, profile, render, validate
from tests import support
from tests.test_derive_ops import build

SCHEMAS = ("case-file", "profile", "enrich-output", "index-output")
LLM = support.FIXTURES / "llm"

META = {
    "spec": {"source": "oas3.yaml", "version": "3.0.3", "sha256": "abc"},
    "profile": {"name": "msp", "source": None},
    "error_shape": {"code_key": "code", "violations_key": "propertyPath",
                    "field_key": "propertyPath", "message_key": "message"},
}


def read(name):
    return json.loads((LLM / name).read_text(encoding="utf-8"))


class Subset(unittest.TestCase):
    def test_shipped_schemas_are_in_subset(self):
        for name in SCHEMAS:
            with self.subTest(name):
                validate.assert_supported(load.load_schema(name))

    def test_unsupported_keyword_raises(self):
        with self.assertRaisesRegex(ValueError, "unsupported keyword oneOf at /properties/a"):
            validate.assert_supported({"properties": {"a": {"oneOf": []}}})

    def test_check_enforces_subset_at_runtime(self):
        with self.assertRaises(ValueError):
            validate.check({}, {"oneOf": []})

    def test_missing_schema(self):
        with self.assertRaises(load.LoadError):
            load.load_schema("nope")

    def test_integer_rejects_bool(self):
        self.assertTrue(validate.check(True, {"type": "integer"}))
        self.assertTrue(validate.check(True, {"type": "number"}))
        self.assertEqual(validate.check(3, {"type": "number"}), [])
        self.assertTrue(validate.check(1.5, {"type": "integer"}))

    def test_type_list_with_items(self):
        schema = {"type": ["integer", "array"], "items": {"type": "integer"}}
        self.assertEqual(validate.check(400, schema), [])
        self.assertEqual(validate.check([400, 413], schema), [])
        self.assertEqual(validate.check([400, "x"], schema), ["/1: expected integer"])

    def test_additional_properties_false_reports_key(self):
        schema = {"type": "object", "additionalProperties": False, "properties": {"a": {}}}
        errs = validate.check({"a": 1, "foo": 2}, schema)
        self.assertEqual(len(errs), 1)
        self.assertTrue(errs[0].startswith("/foo: "))

    def test_additional_properties_schema(self):
        schema = {"type": "object", "additionalProperties": {"type": "string"}}
        self.assertEqual(validate.check({"a": "x"}, schema), [])
        self.assertEqual(validate.check({"a": 1}, schema), ["/a: expected string"])

    def test_ref_resolves(self):
        schema = {"$defs": {"n": {"type": "integer"}}, "properties": {"a": {"$ref": "#/$defs/n"}}}
        self.assertEqual(validate.check({"a": 1}, schema), [])
        self.assertEqual(validate.check({"a": "x"}, schema), ["/a: expected integer"])

    def test_pointer_escaping(self):
        schema = {"properties": {"a/b": {"type": "integer"}}}
        self.assertEqual(validate.check({"a/b": "x"}, schema), ["/a~1b: expected integer"])

    def test_errors_sorted_and_root_pointer(self):
        schema = {"type": "object", "required": ["z", "a"]}
        errs = validate.check({}, schema)
        self.assertEqual(errs, sorted(errs))
        self.assertEqual(len(errs), 2)
        self.assertTrue(validate.check([], {"type": "object"})[0].startswith("/: "))

    def test_pattern_uses_search(self):
        self.assertEqual(validate.check("xxabcxx", {"pattern": "abc"}), [])
        self.assertTrue(validate.check("xxabxx", {"pattern": "abc"}))

    def test_bounds_and_enum(self):
        self.assertTrue(validate.check("ab", {"minLength": 3}))
        self.assertTrue(validate.check("abcd", {"maxLength": 3}))
        self.assertTrue(validate.check(5, {"minimum": 6}))
        self.assertTrue(validate.check(5, {"maximum": 4}))
        self.assertTrue(validate.check([1], {"minItems": 2}))
        self.assertTrue(validate.check([1, 2], {"maxItems": 1}))
        self.assertTrue(validate.check(1, {"enum": [True]}))
        self.assertEqual(validate.check(None, {"enum": [None, "a"]}), [])
        self.assertTrue(validate.check("b", {"const": "a"}))


class ShippedArtifacts(unittest.TestCase):
    def test_rendered_entity_files_match_case_schema(self):
        spec, g, prof, cases = build("oas3.yaml", {
            "tenant": {"model": "path-param", "param": "tenantId", "actor_other": "other"},
            "conflicts": {"POST /v1/{tenantId}/widgets": ["name"]},
        })
        cases = profile.apply(cases, spec, g, prof) + profile.profile_cases(spec, g, prof)
        owner = graph.op_owner(g)
        by_entity = collections.defaultdict(list)
        for c in cases:
            by_entity[owner[c["operation"]["operationId"]]].append(c)
        schema = load.load_schema("case-file")
        self.assertTrue(by_entity)
        for entity, group in by_entity.items():
            with self.subTest(entity):
                text = render.cases_file(entity, group, META)
                with tempfile.TemporaryDirectory() as d:
                    p = os.path.join(d, "e.yaml")
                    with open(p, "w") as f:
                        f.write(text)
                    with support.in_skill_dir():
                        doc = load.load_doc(p)
                self.assertEqual(validate.check(doc, schema), [])

    def test_profiles_match_profile_schema(self):
        schema = load.load_schema("profile")
        for name in ("generic", "msp", "rep"):
            with self.subTest(name):
                with support.in_skill_dir():
                    doc = load.load_doc(f"profiles/{name}.yaml")
                self.assertEqual(validate.check(doc, schema), [])

    def test_profile_schema_rejects_unknown_key(self):
        errs = validate.check({"foo": 1}, load.load_schema("profile"))
        self.assertEqual(len(errs), 1)
        self.assertTrue(errs[0].startswith("/foo: "))

    def test_profile_schema_rejects_bad_enum(self):
        errs = validate.check({"tenant": {"model": "weird"}}, load.load_schema("profile"))
        self.assertTrue(errs[0].startswith("/tenant/model: "))

    def test_llm_case_tracks_case_def(self):
        case = load.load_schema("case-file")["$defs"]["case"]["properties"]
        llm = load.load_schema("enrich-output")["$defs"]["llm_case"]["properties"]
        narrowed = {"kind", "source", "review", "quote"}
        self.assertEqual({k: v for k, v in case.items() if k not in narrowed},
                         {k: v for k, v in llm.items() if k not in narrowed})
        self.assertEqual(set(llm) - set(case), {"quote"})


def spec_for_fixtures():
    with support.in_skill_dir():
        doc = load.load_doc(support.spec_fixture("oas3.yaml"))
    return doc, ir.build_ir(doc, "oas3.yaml", "sha")


class LlmFixtures(unittest.TestCase):
    ENRICH = {
        "enrich-valid.json": None,
        "enrich-bad-extra-key.json": "/foo: ",
        "enrich-bad-kind.json": "/cases/0/kind: ",
        "enrich-bad-unknown-op.json": "unknown operationId",
        "enrich-bad-field-not-in-spec.json": "colour",
        "enrich-bad-quote.json": "quote",
        "enrich-bad-id-collision.json": "widgets.createWidget.body.name.maxLength.plus1",
    }
    INDEX = {
        "index-valid.json": None,
        "index-bad-kind.json": "/tests/0/kind: ",
        "index-bad-status.json": "/tests/0/status: ",
        "index-bad-method.json": "method",
        "index-bad-line.json": "line",
        "index-unknown-endpoint.json": None,
    }

    @classmethod
    def setUpClass(cls):
        _, cls.spec = spec_for_fixtures()
        cls.raw = read("index-raw.json")
        cls.enrich_schema = load.load_schema("enrich-output")
        cls.index_schema = load.load_schema("index-output")

    def outcome(self, name):
        doc = read(name)
        if name.startswith("enrich"):
            errs = validate.check(doc, self.enrich_schema)
            return errs or validate.semantic_enrich(doc, self.spec)
        errs = validate.check(doc, self.index_schema)
        return errs or validate.semantic_index(doc, self.raw)

    def test_each_fixture(self):
        for name, want in {**self.ENRICH, **self.INDEX}.items():
            with self.subTest(name):
                errs = self.outcome(name)
                if want is None:
                    self.assertEqual(errs, [])
                else:
                    self.assertTrue(errs, "expected errors")
                    self.assertTrue(any(want in e for e in errs), errs)

    def test_schema_and_semantic_layers_are_separate(self):
        for name in ("enrich-bad-unknown-op.json", "enrich-bad-field-not-in-spec.json",
                     "enrich-bad-quote.json", "enrich-bad-id-collision.json"):
            with self.subTest(name):
                self.assertEqual(validate.check(read(name), self.enrich_schema), [])
        for name in ("index-bad-method.json", "index-bad-line.json", "index-unknown-endpoint.json"):
            with self.subTest(name):
                self.assertEqual(validate.check(read(name), self.index_schema), [])


if __name__ == "__main__":
    unittest.main()
