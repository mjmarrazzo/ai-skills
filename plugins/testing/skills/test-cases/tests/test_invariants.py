import unittest

from test_cases import ir, validate

DOC = {
    "openapi": "3.0.0",
    "info": {"title": "t"},
    "paths": {"/things": {"post": {
        "operationId": "createThing",
        "parameters": [
            {"name": "limit", "in": "query", "schema": {"type": "integer"}},
            {"name": "X-A", "in": "header", "schema": {"type": "string"}},
        ],
        "requestBody": {"content": {"application/json": {"schema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "tags": {"type": "array", "items": {
                    "type": "object", "properties": {"id": {"type": "string"}}}},
            },
        }}}},
        "responses": {"201": {"description": "ok"}},
    }}},
}
SPEC = ir.build_ir(DOC, "inline", "sha")


def case(cid="t.createThing.body.name.required.missing", **kw):
    inp = {"body": {}, "remove": [], "body_mode": "merge", "raw": None,
           "content_type": None, "path": {}, "query": {}, "headers": {}}
    inp.update(kw.pop("input", {}))
    base = {
        "id": cid,
        "operation": {"method": "POST", "path": "/things", "operationId": "createThing"},
        "kind": "REQUIRED_MISSING",
        "loc": "body",
        "field": "name",
        "rule": "required.missing",
        "negative": True,
        "source": "spec",
        "specRef": "#/x",
        "auth": "valid",
        "input": inp,
        "expected": {"status": 400},
    }
    base.update(kw)
    return base


def run(*cases):
    return validate.invariants(list(cases), SPEC)


class FaultCount(unittest.TestCase):
    def test_single_fault_body(self):
        self.assertEqual(run(case(input={"body": {"name": "<<str:1>>"}})), [])

    def test_two_body_leaves(self):
        errs = run(case(input={"body": {"name": "x", "tags": []}}))
        self.assertEqual(len(errs), 1)
        self.assertIn("faults=2", errs[0])
        self.assertIn("(want 1)", errs[0])

    def test_auth_plus_header(self):
        errs = run(case(auth="malformed", input={"headers": {"X-A": "b"}}))
        self.assertEqual(len(errs), 1)
        self.assertIn("faults=2", errs[0])

    def test_raw_body_one_fault(self):
        self.assertEqual(run(case(input={"body_mode": "raw", "raw": "{"})), [])

    def test_replace_empty_body_one_fault(self):
        self.assertEqual(run(case(input={"body_mode": "replace", "body": {}})), [])

    def test_empty_merge_body_zero_faults(self):
        errs = run(case())
        self.assertIn("faults=0", errs[0])

    def test_single_query_entry(self):
        self.assertEqual(run(case(input={"query": {"limit": None}})), [])

    def test_content_type_is_a_fault(self):
        self.assertEqual(run(case(input={"content_type": "text/plain"})), [])

    def test_profile_forbidden_exempt(self):
        self.assertEqual(run(case(kind="FORBIDDEN_PERMISSION", source="profile")), [])

    def test_lifecycle_exempt(self):
        self.assertEqual(run(case(kind="LIFECYCLE")), [])

    def test_non_negative_not_counted(self):
        self.assertEqual(run(case(negative=False)), [])


class FieldPaths(unittest.TestCase):
    def test_typo_body_path(self):
        errs = run(case(input={"body": {"nmae": "x"}}))
        self.assertEqual(len(errs), 1)
        self.assertIn("nmae", errs[0])

    def test_list_paths(self):
        self.assertEqual(run(case(input={"body": {"tags": ["<<items:1>>", {"id": "x"}]}})), [])
        self.assertEqual(validate.body_paths({"tags": ["<<items:1>>", {"id": "x"}]}),
                         ["tags[]", "tags[].id"])

    def test_placeholder_value_stops_at_key(self):
        self.assertEqual(validate.body_paths({"tags": "<<items:3>>"}), ["tags"])

    def test_nested_dict_paths(self):
        self.assertEqual(validate.body_paths({"a": {"b": 1, "c": {"d": 2}}}), ["a.b", "a.c.d"])

    def test_bad_remove(self):
        errs = run(case(input={"remove": ["nope"]}))
        self.assertIn("nope", errs[0])

    def test_good_remove(self):
        self.assertEqual(run(case(input={"remove": ["name"]})), [])

    def test_query_key_typo(self):
        errs = run(case(input={"query": {"lmt": 1}}))
        self.assertEqual(len(errs), 1)
        self.assertIn("lmt", errs[0])

    def test_unknown_field_ok(self):
        c = case(kind="UNKNOWN_FIELD", input={"body": {"__unexpected_field__": "x"}})
        self.assertEqual(run(c), [])

    def test_unknown_field_inside_array_items_ok(self):
        c = case(kind="UNKNOWN_FIELD", input={"body": {"tags": [{"__unexpected_field__": "x"}]}})
        self.assertEqual(run(c), [])

    def test_mass_assignment_existing_field_errors(self):
        c = case(kind="MASS_ASSIGNMENT", input={"body": {"name": "x"}})
        errs = run(c)
        self.assertEqual(len(errs), 1)
        self.assertIn("name", errs[0])

    def test_unknown_operation(self):
        c = case()
        c["operation"] = {"method": "GET", "path": "/x", "operationId": "nope"}
        self.assertTrue(any("unknown operation nope" in e for e in run(c)))


class Traceability(unittest.TestCase):
    def test_duplicate_ids(self):
        c = case(input={"remove": ["name"]})
        errs = run(c, dict(c))
        self.assertEqual(len(errs), 1)
        self.assertIn("duplicate", errs[0])

    def test_empty_spec_ref(self):
        errs = run(case(specRef="", input={"remove": ["name"]}))
        self.assertIn("specRef", errs[0])

    def test_bad_source(self):
        self.assertTrue(run(case(source="bot", input={"remove": ["name"]})))

    def test_empty_operation_id(self):
        c = case(input={"remove": ["name"]})
        c["operation"] = {"method": "POST", "path": "/things", "operationId": ""}
        self.assertTrue(run(c))

    def test_bool_status(self):
        errs = run(case(input={"remove": ["name"]}, expected={"status": True}))
        self.assertIn("status", errs[0])

    def test_status_list(self):
        ok = case(input={"remove": ["name"]}, expected={"status": [400, 422]})
        self.assertEqual(run(ok), [])
        for bad in ([], [400, "x"], "400", None):
            self.assertTrue(run(case(input={"remove": ["name"]}, expected={"status": bad})))

    def test_sorted_output(self):
        a = case("b.id", input={"body": {"nmae": 1}})
        b = case("a.id", input={"body": {"nmae": 1}})
        errs = run(a, b)
        self.assertEqual(errs, sorted(errs))
        self.assertTrue(errs[0].startswith("a.id"))


if __name__ == "__main__":
    unittest.main()
