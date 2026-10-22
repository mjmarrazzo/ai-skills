import copy
import re
import unittest
from unittest import mock

from test_cases import load

from tests.support import FIXTURES

SPECS = FIXTURES / "specs"


def doc(name):
    return load.load_doc(SPECS / name)


def walk(o):
    yield o
    if isinstance(o, dict):
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def dicts_with(o, key):
    return [d for d in walk(o) if isinstance(d, dict) and key in d]


class Swagger2Fixture(unittest.TestCase):
    def setUp(self):
        self.d = doc("swagger2.yaml")

    def test_structure(self):
        d = self.d
        self.assertEqual(d["swagger"], "2.0")
        self.assertEqual(d["basePath"], "/api")
        self.assertNotIn("security", d)
        params = [p for p in walk(d["paths"]) if isinstance(p, dict) and "in" in p and "name" in p]
        self.assertTrue([p for p in params if p["in"] == "body"])
        self.assertTrue([p for p in params if p["in"] == "formData"])
        self.assertTrue([p for p in params if p["in"] == "header" and p["name"] == "Authorization" and p.get("required")])
        self.assertIn("x-amazon-apigateway-any-method", d["paths"]["/proxy"])

    def test_operation_ids(self):
        ops = [op for item in self.d["paths"].values() for m, op in item.items() if isinstance(op, dict) and m != "parameters"]
        ids = [op.get("operationId") for op in ops if isinstance(op, dict)]
        self.assertIn(None, [self.d["paths"]["/accounts"]["post"].get("operationId")])
        self.assertEqual(ids.count("getAccount"), 2)

    def test_schema_features(self):
        defs = self.d["definitions"]
        self.assertTrue(dicts_with(defs, "x-nullable"))
        self.assertIn("additionalProp1", defs["Account"]["properties"]["metadata"]["properties"])
        acct = defs["Account"]
        self.assertIn("allOf", acct)
        self.assertEqual(acct["required"], ["name"])
        self.assertIs(acct["properties"]["age"]["exclusiveMinimum"], True)
        self.assertEqual(defs["Node"]["properties"]["children"]["items"], {"$ref": "#/definitions/Node"})

    def test_unquoted_int_status_key(self):
        text = (SPECS / "swagger2.yaml").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^\s+200:")


class Oas3Fixture(unittest.TestCase):
    def setUp(self):
        self.d = doc("oas3.yaml")
        self.schemas = self.d["components"]["schemas"]
        self.create = self.schemas["WidgetCreate"]

    def test_patterns_formats_and_constraints(self):
        props = self.create["properties"]
        self.assertTrue(re.fullmatch(r"\^.*\$", props["name"]["pattern"]))
        self.assertFalse(props["code"]["pattern"].startswith("^"))
        self.assertIn(r"\p{IsLatin}", props["sku"]["pattern"])
        self.assertIn("description", props["name"])
        self.assertIn("description", self.d["paths"]["/v1/{tenantId}/widgets"]["post"])
        formats = {d["format"] for d in dicts_with(self.d, "format")}
        self.assertTrue({"date-time", "date", "uuid", "email", "uri", "url"} <= formats)
        self.assertEqual(props["kind"]["enum"], ["SMALL", "LARGE"])
        self.assertIn("maxLength", props["tags"]["items"])
        self.assertIs(props["id"]["readOnly"], True)
        self.assertIs(self.create["additionalProperties"], False)
        self.assertIs(props["quantity"]["exclusiveMinimum"], True)

    def test_operations(self):
        paths = self.d["paths"]
        names = {p["name"] for p in dicts_with(paths, "in") if "name" in p}
        self.assertTrue({"cursor", "limit", "tenantId"} <= names)
        self.assertIn("oneOf", self.schemas["Shape"])
        self.assertEqual(paths["/health"]["get"]["security"], [])
        self.assertEqual(self.d["security"], [{"bearerAuth": []}])


class DerivedFixtures(unittest.TestCase):
    def test_added_field_is_oas3_plus_exactly_two_additions(self):
        base = doc("oas3.yaml")
        added = doc("oas3-added-field.yaml")
        wc = added["components"]["schemas"]["WidgetCreate"]
        self.assertEqual(list(wc["properties"])[-1], "color")
        self.assertIn("color", wc["required"])
        stripped = copy.deepcopy(added)
        swc = stripped["components"]["schemas"]["WidgetCreate"]
        del swc["properties"]["color"]
        swc["required"].remove("color")
        del stripped["paths"]["/v1/{tenantId}/parts"]["get"]
        self.assertEqual(stripped, base)
        self.assertEqual(added["paths"]["/v1/{tenantId}/parts"]["get"]["operationId"], "listParts")

    def test_min_json_needs_no_yaml_backend(self):
        with mock.patch.object(load, "_pyyaml", return_value=None), mock.patch.object(load, "_ruby_exe", return_value=None):
            d = load.load_doc(SPECS / "oas3-min.json")
        self.assertEqual(d["openapi"], "3.0.0")
        self.assertEqual(set(d["paths"]["/items"]), {"get", "post"})
        self.assertNotIn("security", d)


if __name__ == "__main__":
    unittest.main()
