import copy
import unittest
from types import SimpleNamespace

from test_cases import profile


class ResolveTests(unittest.TestCase):
    def test_defaults(self):
        p = profile.resolve(None)
        self.assertEqual(p.name, "generic")
        self.assertEqual(p.error["statuses"]["validation"], 400)
        self.assertEqual(p.tenant["model"], "none")

    def test_nested_override_keeps_siblings(self):
        p = profile.resolve({"error": {"statuses": {"validation": 422}}})
        self.assertEqual(p.error["statuses"]["validation"], 422)
        self.assertEqual(p.error["statuses"]["not_found"], 404)
        self.assertIn("code", p.error["keys"])

    def test_lists_become_tuples_and_replace(self):
        p = profile.resolve({"actors": ["a", "b"], "tests": {"globs": ["x/*.kt"]}})
        self.assertEqual(p.actors, ("a", "b"))
        self.assertEqual(list(p.tests["globs"]), ["x/*.kt"])
        self.assertIn("exclude_classes", p.tests)

    def test_defaults_not_mutated(self):
        before = copy.deepcopy(profile.DEFAULTS)
        profile.resolve({"error": {"statuses": {"validation": 422}}, "actors": ["z"]})
        profile.resolve({"tests": {"globs": []}})
        self.assertEqual(profile.DEFAULTS, before)


class MatchOpTests(unittest.TestCase):
    def test_star_matches_all(self):
        self.assertTrue(profile.match_op("*", "GET", "/x"))
        self.assertTrue(profile.match_op("  * ", "POST", "/y/z"))

    def test_method_constraint(self):
        self.assertTrue(profile.match_op("DELETE *", "DELETE", "/x"))
        self.assertFalse(profile.match_op("DELETE *", "GET", "/x"))

    def test_exact_path(self):
        self.assertTrue(profile.match_op("POST /profiles", "POST", "/profiles"))
        self.assertFalse(profile.match_op("POST /profiles", "POST", "/profiles/1"))
        self.assertFalse(profile.match_op("POST /profiles", "GET", "/profiles"))

    def test_star_crosses_slash(self):
        self.assertTrue(profile.match_op("GET /v1/*/widgets", "GET", "/v1/a/b/widgets"))

    def test_braces_literal(self):
        self.assertTrue(profile.match_op("GET /widgets/{id}", "GET", "/widgets/{id}"))
        self.assertFalse(profile.match_op("GET /widgets/{id}", "GET", "/widgets/1"))

    def test_brackets_literal_any_method(self):
        self.assertTrue(profile.match_op("/a[1]", "PATCH", "/a[1]"))
        self.assertFalse(profile.match_op("/a[1]", "GET", "/a1"))


class ExcludeTests(unittest.TestCase):
    def test_is_excluded(self):
        p = profile.resolve({"exclude": ["GET /health", "/internal/*"]})
        self.assertTrue(profile.is_excluded(p, SimpleNamespace(method="GET", path="/health")))
        self.assertFalse(profile.is_excluded(p, SimpleNamespace(method="POST", path="/health")))
        self.assertFalse(profile.is_excluded(profile.resolve(None), SimpleNamespace(method="GET", path="/health")))


if __name__ == "__main__":
    unittest.main()
