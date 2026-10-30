import copy
import hashlib
import json
import unittest

from test_cases import ir, load
from tests import support


def build(name):
    with support.in_skill_dir():
        doc = load.load_doc(support.spec_fixture(name))
    return doc, ir.build_ir(doc, name, "sha")


def by_id(spec):
    return {o.operation_id: o for o in spec.operations}


def tail(method, path):
    return "_" + hashlib.sha1(f"{method} {path}".encode()).hexdigest()[:6]


def inline(paths, **extra):
    return ir.build_ir({"openapi": "3.0.0", "info": {"title": "t"}, "paths": paths, **extra}, "inline", "sha")


class Swagger2Ops(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc, cls.spec = build("swagger2.yaml")
        cls.ops = {(o.method, o.path): o for o in cls.spec.operations}

    def test_order_and_skip_warning(self):
        self.assertEqual(
            [(o.method, o.path) for o in self.spec.operations],
            [("POST", "/accounts"), ("GET", "/accounts/{accountId}"),
             ("GET", "/accounts/{accountId}/notes"), ("POST", "/accounts/{accountId}/avatar")],
        )
        self.assertIn("skipped x-amazon-apigateway-any-method at /proxy", self.spec.warnings)

    def test_synthesized_id(self):
        op = self.ops[("POST", "/accounts")]
        self.assertEqual(op.operation_id, "postAccounts")
        self.assertTrue(op.op_id_synthesized)

    def test_duplicate_ids_suffix_every_member(self):
        a = self.ops[("GET", "/accounts/{accountId}")]
        b = self.ops[("GET", "/accounts/{accountId}/notes")]
        self.assertEqual(a.operation_id, "getAccount" + tail("GET", "/accounts/{accountId}"))
        self.assertEqual(b.operation_id, "getAccount" + tail("GET", "/accounts/{accountId}/notes"))
        self.assertTrue(any("duplicate operationId getAccount" in w for w in self.spec.warnings))

    def test_suffix_ignores_document_order(self):
        doc = copy.deepcopy(self.doc)
        paths = doc["paths"]
        doc["paths"] = {k: paths[k] for k in
                        ["/accounts/{accountId}/notes", "/accounts/{accountId}", "/accounts"]}
        ids = by_id(ir.build_ir(doc, "x", "sha"))
        self.assertIn("getAccount" + tail("GET", "/accounts/{accountId}"), ids)
        self.assertIn("getAccount" + tail("GET", "/accounts/{accountId}/notes"), ids)

    def test_server_path(self):
        self.assertEqual(self.spec.server_path, "/api")

    def test_body_and_fields(self):
        body = self.ops[("POST", "/accounts")].body
        self.assertEqual(body.media, "application/json")
        self.assertEqual(body.schema_name, "Account")
        self.assertEqual(
            [f.path for f in body.fields],
            ["id", "createdAt", "email", "name", "age", "metadata", "tree",
             "tree.label", "tree.children", "tree.children[]"],
        )

    def test_form_body(self):
        body = self.ops[("POST", "/accounts/{accountId}/avatar")].body
        self.assertEqual(body.media, "multipart/form-data")
        self.assertEqual([f.path for f in body.fields], ["caption", "file"])
        caption = body.fields[0]
        self.assertTrue(caption.required)
        self.assertEqual(caption.constraints, {"maxLength": 100})

    def test_authorization_header_becomes_security_flag(self):
        for op in self.spec.operations:
            self.assertNotIn("authorization", [p.name.lower() for p in op.params])
            self.assertTrue(op.security.secured)
            self.assertTrue(op.security.header_param)

    def test_path_level_param_merges(self):
        op = self.ops[("GET", "/accounts/{accountId}")]
        self.assertEqual([(p.name, p.location) for p in op.params], [("accountId", "path")])
        self.assertEqual(op.params[0].spec_ref, "#/paths/~1accounts~1{accountId}/parameters/0")
        self.assertEqual(op.params[0].field.format, "uuid")

    def test_response_statuses_are_strings(self):
        op = self.ops[("POST", "/accounts")]
        self.assertEqual([r.status for r in op.responses], ["200", "400"])
        self.assertEqual(op.responses[0].schema_name, "Account")
        self.assertEqual(op.responses[0].content_types, ("application/json",))


class Oas3Ops(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc, cls.spec = build("oas3.yaml")
        cls.ids = by_id(cls.spec)

    def test_server_path_keeps_template(self):
        self.assertEqual(self.spec.server_path, "/{stage}/widgets-svc")

    def test_security(self):
        op = self.ids["getWidget"]
        self.assertTrue(op.security.secured)
        self.assertEqual(op.security.schemes, ("bearerAuth",))
        health = self.ids["health"].security
        self.assertFalse(health.secured)
        self.assertFalse(health.optional)

    def test_unsupported_oneof(self):
        self.assertTrue(any(u.startswith("oneOf at") for u in self.ids["createShape"].unsupported))

    def test_param_constraints(self):
        limit = next(p for p in self.ids["listWidgets"].params if p.name == "limit")
        self.assertEqual(limit.field.constraints, {"minimum": 1, "maximum": 100})
        self.assertEqual(limit.location, "query")

    def test_path_level_params_come_first(self):
        self.assertEqual([p.name for p in self.ids["listWidgets"].params], ["tenantId", "cursor", "limit"])

    def test_json_roundtrip_is_stable(self):
        first = json.dumps(ir.to_dict(self.spec))
        second = json.dumps(ir.to_dict(ir.build_ir(self.doc, "oas3.yaml", "sha")))
        self.assertEqual(first, second)


class MinimalSpec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc, cls.spec = build("oas3-min.json")

    def test_create_item(self):
        op = by_id(self.spec)["createItem"]
        self.assertIsNone(self.spec.server_path)
        self.assertEqual(op.spec_ref, "#/paths/~1items/post")
        self.assertFalse(op.security.secured)
        self.assertEqual(
            op.body.fields[0].spec_ref,
            "#/paths/~1items/post/requestBody/content/application~1json/schema/properties/name",
        )
        self.assertIsNone(op.responses[0].schema_name)
        self.assertEqual(op.responses[0].status, "201")


class InlineDocs(unittest.TestCase):
    def test_op_param_overrides_path_param(self):
        path_level = {"name": "id", "in": "query", "schema": {"type": "string", "maxLength": 5}}
        op_level = {"name": "id", "in": "query", "schema": {"type": "string", "maxLength": 9}}
        spec = inline({"/x": {"parameters": [path_level], "get": {"operationId": "g", "parameters": [op_level]}}})
        params = spec.operations[0].params
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0].field.constraints, {"maxLength": 9})
        self.assertEqual(params[0].spec_ref, "#/paths/~1x/get/parameters/0")

    def test_empty_security_requirement_is_optional(self):
        spec = inline({"/x": {"get": {"operationId": "g", "security": [{}]}}},
                      security=[{"k": []}])
        sec = spec.operations[0].security
        self.assertTrue(sec.optional)
        self.assertFalse(sec.secured)

    def test_response_picks_xml_when_no_json(self):
        schema = {"$ref": "#/components/schemas/Pet"}
        resp = {"200": {"description": "ok", "content": {
            "text/plain": {"schema": {"type": "string"}}, "application/xml": {"schema": schema}}}}
        spec = inline({"/x": {"get": {"operationId": "g", "responses": resp}}},
                      components={"schemas": {"Pet": {"type": "object"}}})
        r = spec.operations[0].responses[0]
        self.assertEqual(r.schema_name, "Pet")
        self.assertEqual(r.content_types, ("text/plain", "application/xml"))

    def test_integer_response_keys_stringified(self):
        spec = inline({"/x": {"get": {"operationId": "g", "responses": {200: {"description": "ok"}}}}})
        self.assertEqual(spec.operations[0].responses[0].status, "200")

    def test_no_paths(self):
        spec = inline({})
        self.assertEqual(spec.operations, ())
        self.assertIn("no paths", spec.warnings)

    def test_array_body_is_unsupported(self):
        body = {"content": {"application/json": {"schema": {"type": "array", "items": {"type": "string"}}}}}
        spec = inline({"/x": {"post": {"operationId": "p", "requestBody": body}}})
        op = spec.operations[0]
        self.assertEqual(op.body.fields, ())
        self.assertEqual(op.body.root_type, "array")
        self.assertEqual(
            op.unsupported,
            ("array body at #/paths/~1x/post/requestBody/content/application~1json/schema",),
        )

    def test_multiple_content_types_prefer_json(self):
        content = {"text/plain": {"schema": {"type": "string"}},
                   "application/json": {"schema": {"type": "object"}}}
        spec = inline({"/x": {"post": {"operationId": "p", "requestBody": {"content": content}}}})
        body = spec.operations[0].body
        self.assertEqual(body.media, "application/json")
        self.assertEqual(body.content_types, ("text/plain", "application/json"))

    def test_resolves_parameter_and_request_body_refs(self):
        doc = {
            "openapi": "3.0.0", "info": {"title": "t"},
            "paths": {"/x": {"post": {
                "operationId": "p",
                "parameters": [{"$ref": "#/components/parameters/Q"}],
                "requestBody": {"$ref": "#/components/requestBodies/B"},
            }}},
            "components": {
                "parameters": {"Q": {"name": "q", "in": "query", "schema": {"type": "string"}}},
                "requestBodies": {"B": {"required": True, "content": {
                    "application/json": {"schema": {"type": "object", "properties": {"a": {"type": "string"}}}}}}},
            },
        }
        op = ir.build_ir(doc, "x", "sha").operations[0]
        self.assertEqual(op.params[0].spec_ref, "#/components/parameters/Q")
        self.assertTrue(op.body.required)
        self.assertEqual(op.body.spec_ref, "#/components/requestBodies/B")

    def test_id_sanitized(self):
        spec = inline({"/x": {"get": {"operationId": "get.my-thing"}}})
        self.assertEqual(spec.operations[0].operation_id, "get_my_thing")
        self.assertFalse(spec.operations[0].op_id_synthesized)

    def test_synthesized_by_id_suffix(self):
        spec = inline({"/widget-parts/{id}": {"get": {}}})
        self.assertEqual(spec.operations[0].operation_id, "getWidgetPartsById")


if __name__ == "__main__":
    unittest.main()
