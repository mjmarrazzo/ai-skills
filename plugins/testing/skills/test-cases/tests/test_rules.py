import re
import unittest

from test_cases import ir, rules

OPS = {
    "strlen", "num", "literal", "remove", "null", "type_wrong", "enum_each", "enum_variant",
    "format_invalid", "pattern_probe", "pattern_llm", "items", "items_dup", "items_empty",
    "body_mode", "valid_sample", "overflow", "multiple_off",
}
ROW = {r.id: r for r in rules.RULES}


def field(type="string", name="f", required=False, nullable=False, read_only=False, fmt=None, **constraints):
    return ir.Field(
        path=name, name=name, type=type, format=fmt, required=required, nullable=nullable,
        read_only=read_only, write_only=False, constraints=constraints, schema_ref=None,
        spec_ref="#/x", description="", truncated=False,
    )


def run(rule_id, f):
    return rules.expand(ROW[rule_id], f)


def values(rule_id, f):
    return [v.value for v in run(rule_id, f)]


class TableIntegrityTest(unittest.TestCase):
    def test_row_ids_unique(self):
        ids = [r.id for r in rules.RULES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_kinds_and_techniques(self):
        for r in rules.RULES:
            self.assertIn(r.kind, rules.KINDS, r.id)
            self.assertNotIn(r.kind, rules.RESERVED_KINDS, r.id)
            self.assertIn(r.technique, rules.TECHNIQUES, r.id)

    def test_guards_and_ops_known(self):
        for r in rules.RULES:
            self.assertTrue(r.guard is None or r.guard in rules.GUARDS, r.id)
            self.assertIn(r.value[0], OPS, r.id)
            self.assertIn(r.keyword, rules.TRIGGERS, r.id)

    def test_kind_count(self):
        self.assertEqual(len(rules.KINDS), 43)
        self.assertTrue(set(rules.RESERVED_KINDS) <= set(rules.KINDS))

    def test_rule_ids_cover_rows_and_variants(self):
        self.assertTrue({r.id for r in rules.RULES} <= rules.RULE_IDS)
        self.assertIn("format.no_tz", rules.RULE_IDS)
        self.assertIn("type.wrong", rules.RULE_IDS)
        self.assertIn("mass_assignment.role", rules.RULE_IDS)
        self.assertIn("happy.min", rules.RULE_IDS)

    def test_required_empty_precedes_min_length_minus1(self):
        ids = [r.id for r in rules.RULES]
        self.assertLess(ids.index("required.empty"), ids.index("minLength.minus1"))

    def test_rules_hold_no_callables(self):
        for r in rules.RULES:
            self.assertFalse(callable(r.guard))
            self.assertFalse(any(callable(x) for x in r.value))


class StringLengthTest(unittest.TestCase):
    def test_max_length_neighbours(self):
        f = field(maxLength=50)
        self.assertEqual(values("maxLength.plus1", f), ["<<str:51>>"])
        self.assertEqual(values("maxLength.minus1", f), ["<<str:49>>"])
        self.assertEqual(values("maxLength.max", f), ["<<str:50>>"])

    def test_min_length_zero_is_empty_string(self):
        self.assertEqual(values("minLength.min", field(minLength=0)), [""])

    def test_valid_neighbour_outside_own_range_is_skipped(self):
        f = field(minLength=5, maxLength=5)
        self.assertEqual(run("minLength.plus1", f), [])
        self.assertEqual(run("maxLength.minus1", f), [])
        self.assertEqual(values("minLength.min", f), ["<<str:5>>"])

    def test_negative_length_skipped(self):
        self.assertEqual(run("maxLength.minus1", field(maxLength=0)), [])

    def test_min_length_minus1_guard(self):
        self.assertEqual(run("minLength.minus1", field(minLength=0)), [])
        self.assertEqual(values("minLength.minus1", field(minLength=3)), ["<<str:2>>"])

    def test_invalid_neighbour_not_range_filtered(self):
        self.assertEqual(values("maxLength.plus1", field(minLength=1, maxLength=2)), ["<<str:3>>"])


class NumberTest(unittest.TestCase):
    def test_step_is_multiple_of_exact(self):
        f = field("number", minimum=0, multipleOf=0.01)
        self.assertEqual(values("minimum.plus1", f), [0.01])
        self.assertEqual(values("minimum.minus1", f), [-0.01])

    def test_integer_yields_int(self):
        f = field("integer", minimum=1, maximum=10)
        for rid in ("minimum.min", "minimum.plus1", "minimum.minus1", "maximum.max", "maximum.minus1", "maximum.plus1"):
            for v in run(rid, f):
                self.assertIs(type(v.value), int, rid)
        self.assertEqual(values("maximum.plus1", f), [11])

    def test_exclusive_minimum(self):
        f = field("integer", exclusiveMinimum=0)
        self.assertEqual(values("exclusiveMinimum.plus1", f), [1])
        self.assertEqual(values("exclusiveMinimum.at", f), [0])

    def test_valid_neighbour_beyond_other_bound_skipped(self):
        f = field("integer", minimum=1, maximum=1)
        self.assertEqual(run("minimum.plus1", f), [])
        self.assertEqual(run("maximum.minus1", f), [])

    def test_multiple_of_variants(self):
        self.assertEqual(values("multipleOf.k1", field("integer", multipleOf=5)), [5])
        self.assertEqual(values("multipleOf.k2", field("integer", multipleOf=5)), [10])

    def test_multiple_off(self):
        self.assertEqual(values("multipleOf.off", field("integer", multipleOf=5)), [6])
        self.assertEqual(values("multipleOf.off", field("number", multipleOf=0.5)), [0.25])
        self.assertEqual(run("multipleOf.off", field("integer", multipleOf=1)), [])

    def test_type_wrong_integer(self):
        vs = run("type.wrong", field("integer"))
        self.assertEqual([v.slug for v in vs], ["string", "float", "bool"])
        self.assertEqual([v.value for v in vs], ["1", 1.5, True])
        self.assertEqual({v.rule_id for v in vs}, {"type.wrong"})

    def test_overflow(self):
        self.assertEqual(values("type.overflow", field("integer", fmt="int32")), [2147483648])
        self.assertEqual(values("type.overflow", field("integer", fmt="int64")), [9223372036854775808])
        self.assertEqual(run("type.overflow", field("integer")), [])


class EnumFormatTest(unittest.TestCase):
    def test_numeric_enum(self):
        f = field("integer", enum=[1, 3])
        self.assertEqual(values("enum.not_in_set", f), [4])
        for rid in ("enum.case_changed", "enum.trailing_space", "enum.empty"):
            self.assertEqual(run(rid, f), [], rid)

    def test_string_enum_variants(self):
        f = field(enum=["SMALL"])
        self.assertEqual(values("enum.case_changed", f), ["small"])
        self.assertEqual(values("enum.trailing_space", f), ["SMALL "])
        self.assertEqual(values("enum.empty", f), [""])
        self.assertEqual(values("enum.not_in_set", f), ["NOT_IN_ENUM_VALUE"])

    def test_not_in_set_avoids_collision(self):
        self.assertEqual(values("enum.not_in_set", field(enum=["NOT_IN_ENUM_VALUE"])), ["NOT_IN_ENUM_VALUE_X"])

    def test_case_changed_skips_values_in_set(self):
        self.assertEqual(run("enum.case_changed", field(enum=["a", "A"])), [])
        self.assertEqual(run("enum.case_changed", field(enum=["123"])), [])

    def test_empty_blocked_when_empty_in_enum(self):
        self.assertEqual(run("enum.empty", field(enum=["", "a"])), [])

    def test_enum_each(self):
        vs = run("enum.each", field(enum=["A", "B"]))
        self.assertEqual([(v.rule_id, v.value, v.slug) for v in vs], [("enum.each", "A", "A"), ("enum.each", "B", "B")])

    def test_uuid_variants(self):
        vs = {v.rule_id: v.value for v in run("format", field(fmt="uuid"))}
        self.assertEqual(
            {k: len(v) for k, v in vs.items()},
            {"format.short": 35, "format.long": 37, "format.non_hex": 36, "format.no_hyphens": 32},
        )

    def test_uri_row_is_security_tagged_and_plain_row_blocked(self):
        f = field(fmt="uri")
        self.assertEqual(run("format", f), [])
        vs = run("format.uri", f)
        self.assertIn("format.internal_ip", [v.rule_id for v in vs])
        self.assertEqual(ROW["format.uri"].technique, "owasp-api7")
        self.assertIn("security", ROW["format.uri"].tags)
        self.assertNotIn("security", ROW["format"].tags)

    def test_url_uses_uri_row(self):
        self.assertTrue(run("format.uri", field(fmt="url")))
        self.assertEqual(run("format", field(fmt="url")), [])

    def test_format_p3(self):
        self.assertEqual(rules.FORMAT_P3, {"format.no_hyphens"})


class PatternTest(unittest.TestCase):
    def test_anchored_probes(self):
        f = field(pattern="^[A-Z]+$", example="ABC")
        self.assertEqual(values("pattern.empty", f), [""])
        self.assertEqual(len(values("pattern.out_of_class", f)), 1)
        self.assertEqual(values("pattern.lead_space", f), [" ABC"])
        self.assertEqual(values("pattern.trail_space", f), ["ABC "])

    def test_composite_when_no_usable_example(self):
        f = field(pattern="^[A-Z]+$", example="abc")
        self.assertEqual(values("pattern.lead_space", f), [" <<pattern-sample>>"])
        self.assertEqual(values("pattern.trail_space", f), ["<<pattern-sample>> "])

    def test_unanchored_has_no_space_rows_and_probes_fail_search(self):
        f = field(pattern="[A-Z]{3}")
        self.assertEqual(run("pattern.lead_space", f), [])
        self.assertEqual(run("pattern.trail_space", f), [])
        rx = re.compile(f.constraints["pattern"])
        for rid in ("pattern.empty", "pattern.out_of_class"):
            for v in run(rid, f):
                self.assertIsNone(rx.search(v.value))
                self.assertIsNone(rx.fullmatch(v.value))

    def test_out_of_class_length_follows_min_length(self):
        v = run("pattern.out_of_class", field(pattern="^[A-Z]+$", minLength=4))[0].value
        self.assertEqual(len(v), 4)
        v = run("pattern.out_of_class", field(pattern="^[A-Z]+$", minLength=500))[0].value
        self.assertEqual(len(v), 64)

    def test_empty_omitted_when_pattern_matches_empty(self):
        self.assertEqual(run("pattern.empty", field(pattern="^[a-z]*$")), [])

    def test_no_qualifying_out_of_class_probe(self):
        self.assertEqual(run("pattern.out_of_class", field(pattern=".")), [])

    def test_uncompilable_goes_to_llm(self):
        f = field(pattern=r"^\P{Alnum}+$")
        self.assertEqual(values("pattern.llm", f), ["<<pattern-negative>>"])
        self.assertEqual(run("pattern.empty", f), [])
        self.assertEqual(run("pattern.llm", field(pattern="^a$")), [])

    def test_compile_pattern(self):
        self.assertEqual(rules.compile_pattern(r"^\p{Alnum}+$").pattern, "^[A-Za-z0-9]+$")
        self.assertEqual(rules.compile_pattern(r"[\p{Alnum}_]+").pattern, "[A-Za-z0-9_]+")
        self.assertIsNone(rules.compile_pattern(r"\P{Alnum}"))
        self.assertIsNone(rules.compile_pattern(r"\p{Greek}"))
        self.assertIsNone(rules.compile_pattern("a" * 1001))
        self.assertIsNone(rules.compile_pattern("(unclosed"))
        self.assertIsNotNone(rules.compile_pattern(r"\\p{x}"))

    def test_anchored_guard(self):
        guard = rules.GUARDS["anchored"]
        self.assertFalse(guard(field(pattern="^abc")))
        self.assertTrue(guard(field(pattern="^abc$")))


class ArrayAndMiscTest(unittest.TestCase):
    def test_min_items(self):
        f = field("array", minItems=1)
        self.assertEqual(values("minItems.minus1", f), [[]])
        self.assertEqual(values("items.empty", f), [[]])
        self.assertEqual(values("minItems.min", f), ["<<items:1>>"])
        self.assertEqual(run("minItems.minus1", field("array", minItems=0)), [])
        self.assertEqual(run("items.empty", field("array", minItems=0)), [])

    def test_max_items(self):
        f = field("array", maxItems=5)
        self.assertEqual(values("maxItems.plus1", f), ["<<items:6>>"])
        self.assertEqual(values("maxItems.max", f), ["<<items:5>>"])

    def test_unique_items_only_when_true(self):
        self.assertEqual(values("uniqueItems.dup", field("array", uniqueItems=True)), ["<<items:dup>>"])
        self.assertEqual(run("uniqueItems.dup", field("array", uniqueItems=False)), [])

    def test_additional_properties(self):
        f = field("object", additionalProperties=False)
        self.assertEqual(values("additionalProperties.unknown", f), [{"__unexpected_field__": "x"}])

    def test_required_rows(self):
        f = field(required=True)
        self.assertIs(values("required.missing", f)[0], rules.REMOVE)
        self.assertEqual(values("required.null", f), [None])
        self.assertEqual(values("required.empty", f), [""])
        self.assertEqual(run("required.missing", field()), [])
        self.assertEqual(run("required.empty", field("integer", required=True)), [])

    def test_type_null_guard(self):
        self.assertEqual(values("type.null", field("integer")), [None])
        self.assertEqual(run("type.null", field("integer", nullable=True)), [])
        self.assertEqual(values("nullable.null", field(nullable=True)), [None])

    def test_read_only_valid_sample(self):
        self.assertEqual(values("readOnly.sent", field(fmt="uuid", read_only=True)), ["00000000-0000-4000-8000-000000000000"])
        self.assertEqual(values("readOnly.sent", field(read_only=True, example="x")), ["x"])
        self.assertEqual(values("readOnly.sent", field(read_only=True, minLength=3)), ["<<str:3>>"])
        self.assertEqual(values("readOnly.sent", field("integer", read_only=True, minimum=5)), [5])
        self.assertEqual(values("readOnly.sent", field("boolean", read_only=True)), [True])
        self.assertEqual(values("readOnly.sent", field("array", read_only=True)), [[]])

    def test_truncated_triggers_nothing(self):
        base = field(required=True, maxLength=3)
        f = ir.Field(**{s: getattr(base, s) for s in ir.Field.__slots__ if s != "truncated"}, truncated=True)
        for r in rules.RULES:
            self.assertEqual(rules.expand(r, f), [], r.id)

    def test_expand_does_not_mutate_field(self):
        f = field(enum=["a"], maxLength=3)
        before = dict(f.constraints)
        for r in rules.RULES:
            rules.expand(r, f)
        self.assertEqual(f.constraints, before)


if __name__ == "__main__":
    unittest.main()
