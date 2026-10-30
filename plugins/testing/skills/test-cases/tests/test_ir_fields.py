import copy
import unittest

from test_cases import ir, load
from tests import support


def walk_ref(doc, name, base):
    return ir.walk_schema(doc, {"$ref": f"{base}/{name}"}, f"{base}/{name}")


class Swagger2Walk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with support.in_skill_dir():
            cls.doc = load.load_doc(support.spec_fixture("swagger2.yaml"))
        cls.walk = walk_ref(cls.doc, "Account", "#/definitions")
        cls.by_path = {f.path: f for f in cls.walk.fields}

    def test_field_order(self):
        self.assertEqual(
            [f.path for f in self.walk.fields],
            ["id", "createdAt", "email", "name", "age", "metadata", "tree",
             "tree.label", "tree.children", "tree.children[]"],
        )

    def test_required_beside_allof_survives(self):
        self.assertTrue(self.by_path["email"].required)
        self.assertTrue(self.by_path["name"].required)
        self.assertFalse(self.by_path["age"].required)

    def test_base_pointers_and_flags(self):
        f = self.by_path["id"]
        self.assertTrue(f.read_only)
        self.assertEqual(f.schema_ref, "Base")
        self.assertEqual(f.spec_ref, "#/definitions/Base/properties/id")
        self.assertEqual(self.walk.schema_name, "Account")

    def test_inline_allof_branch_pointer(self):
        self.assertEqual(self.by_path["email"].spec_ref, "#/definitions/Account/allOf/1/properties/email")

    def test_x_nullable(self):
        self.assertTrue(self.by_path["name"].nullable)
        self.assertFalse(self.by_path["age"].nullable)

    def test_boolean_exclusive_minimum(self):
        self.assertEqual(self.by_path["age"].constraints, {"exclusiveMinimum": 18})

    def test_additional_prop_dropped_with_warning(self):
        self.assertNotIn("additionalProp1", [f.name for f in self.walk.fields])
        self.assertTrue(any("additionalProp1" in w for w in self.walk.warnings))

    def test_recursion_truncates(self):
        f = self.by_path["tree.children[]"]
        self.assertTrue(f.truncated)
        self.assertIn("recursion at #/definitions/Node/properties/children/items", self.walk.unsupported)
        self.assertEqual(self.by_path["tree"].schema_ref, "Node")


class Oas3Walk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with support.in_skill_dir():
            cls.doc = load.load_doc(support.spec_fixture("oas3.yaml"))
        cls.walk = walk_ref(cls.doc, "WidgetCreate", "#/components/schemas")
        cls.by_path = {f.path: f for f in cls.walk.fields}

    def test_array_items_fields(self):
        p = self.by_path
        for path in ("tags", "tags[]", "parts", "parts[]", "parts[].id"):
            self.assertIn(path, p)
        self.assertEqual(p["tags[]"].constraints, {"maxLength": 20})
        self.assertEqual(p["tags"].constraints, {"minItems": 1, "maxItems": 5, "uniqueItems": True})
        self.assertTrue(p["parts[].id"].required)
        self.assertEqual(p["parts[]"].schema_ref, "PartRef")

    def test_nested_object(self):
        self.assertEqual(self.by_path["dimensions.width"].constraints, {"minimum": 1})

    def test_numeric_constraints(self):
        q = self.by_path["quantity"]
        self.assertEqual(q.constraints, {"exclusiveMinimum": 0, "maximum": 500})
        self.assertEqual(q.format, "int32")

    def test_root_attributes(self):
        self.assertEqual(self.walk.root_type, "object")
        self.assertIs(self.walk.additional_properties, False)

    def test_constraints_exclude_non_constraint_keys(self):
        for f in self.walk.fields:
            for key in f.constraints:
                self.assertIn(key, ir.CONSTRAINT_KEYS)
                self.assertNotIn(key, ("title", "format"))
                self.assertFalse(key.startswith("x-"))

    def test_description_defaults_to_empty(self):
        self.assertEqual(self.by_path["code"].description, "")
        self.assertTrue(self.by_path["name"].description)

    def test_oneof_root_ref(self):
        w = walk_ref(self.doc, "Shape", "#/components/schemas")
        self.assertEqual(w.fields, ())
        self.assertEqual(w.unsupported, ("oneOf at #/components/schemas/Shape",))


class InlineWalk(unittest.TestCase):
    def test_inline_oneof_root(self):
        w = ir.walk_schema({}, {"oneOf": [{"type": "string"}]}, "#/ptr")
        self.assertEqual(w.fields, ())
        self.assertEqual(w.unsupported, ("oneOf at #/ptr",))

    def test_oneof_property_has_no_children(self):
        schema = {"properties": {"p": {"anyOf": [{"properties": {"x": {"type": "string"}}}]}}}
        w = ir.walk_schema({}, schema, "#/s")
        self.assertEqual([f.path for f in w.fields], ["p"])
        self.assertEqual(w.unsupported, ("anyOf at #/s/properties/p",))

    def test_external_ref(self):
        schema = {"properties": {"o": {"$ref": "other.yaml#/X"}}}
        w = ir.walk_schema({}, schema, "#/s")
        self.assertTrue(w.fields[0].truncated)
        self.assertEqual(w.unsupported, ("external $ref at #/s/properties/o",))
        self.assertTrue(w.warnings)

    def test_depth_cap(self):
        schema = {"type": "object"}
        for _ in range(10):
            schema = {"type": "object", "properties": {"n": schema}}
        w = ir.walk_schema({}, schema, "#/s")
        self.assertEqual(len(w.fields), 9)
        self.assertTrue(w.fields[-1].truncated)
        self.assertFalse(w.fields[-2].truncated)
        self.assertEqual(len(w.unsupported), 1)
        self.assertTrue(w.unsupported[0].startswith("depth cap at "))

    def test_escaped_ref_name(self):
        doc = {"components": {"schemas": {"a/b": {"properties": {"x": {"type": "string"}}}}}}
        w = ir.walk_schema(doc, {"$ref": "#/components/schemas/a~1b"}, "#/body")
        self.assertEqual([f.path for f in w.fields], ["x"])
        self.assertEqual(w.fields[0].spec_ref, "#/components/schemas/a~1b/properties/x")
        self.assertEqual(w.schema_name, "a/b")

    def test_inline_body_pointer(self):
        with support.in_skill_dir():
            doc = load.load_doc(support.spec_fixture("oas3-min.json"))
        base = "#/paths/~1items/post/requestBody/content/application~1json/schema"
        schema = doc["paths"]["/items"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        w = ir.walk_schema(doc, schema, base)
        f = w.fields[0]
        self.assertEqual(f.spec_ref, base + "/properties/name")
        self.assertIsNone(f.schema_ref)
        self.assertTrue(f.required)
        self.assertIsNone(w.schema_name)

    def test_does_not_mutate_input(self):
        schema = {"properties": {"a": {"type": "integer", "minimum": 1, "exclusiveMinimum": True}}}
        before = copy.deepcopy(schema)
        ir.walk_schema({}, schema, "#/s")
        self.assertEqual(schema, before)


if __name__ == "__main__":
    unittest.main()
