import os
import tempfile
import unittest

from test_cases import load, yamlfmt


def _roundtrip(obj):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "x.yaml")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(yamlfmt.dump(obj))
        return load.load_doc(p)


class LayoutTest(unittest.TestCase):
    def test_nested_sample_exact(self):
        obj = {
            "id": "w-1",
            "tags": ["a", "b"],
            "items": [
                {"name": "x", "num": 1, "deep": {"k": True}},
                {"name": "y", "num": None},
            ],
            "matrix": [[1, 2], []],
            "meta": {},
        }
        expected = (
            'id: "w-1"\n'
            "tags:\n"
            '  - "a"\n'
            '  - "b"\n'
            "items:\n"
            '  - name: "x"\n'
            "    num: 1\n"
            "    deep:\n"
            "      k: true\n"
            '  - name: "y"\n'
            "    num: null\n"
            "matrix:\n"
            "  -\n"
            "    - 1\n"
            "    - 2\n"
            "  - []\n"
            "meta: {}\n"
        )
        self.assertEqual(yamlfmt.dump(obj), expected)

    def test_insertion_order_preserved(self):
        self.assertEqual(yamlfmt.dump({"z": 1, "a": 2, "m": 3}), "z: 1\na: 2\nm: 3\n")

    def test_empty_containers_inline(self):
        self.assertEqual(yamlfmt.dump({"a": {}, "b": []}), "a: {}\nb: []\n")

    def test_single_trailing_newline(self):
        self.assertTrue(yamlfmt.dump({"a": [1]}).endswith("1\n"))
        self.assertFalse(yamlfmt.dump({"a": [1]}).endswith("\n\n"))


class KeyTest(unittest.TestCase):
    def test_quoting(self):
        out = yamlfmt.dump({"yes": 1, "null": 2, "200": 3, "POST /x": 4, "a.b": 5, "abc_1": 6})
        self.assertEqual(
            out,
            '"yes": 1\n"null": 2\n"200": 3\n"POST /x": 4\n"a.b": 5\nabc_1: 6\n',
        )

    def test_all_yaml11_words_quoted(self):
        for w in "y Y yes Yes YES n N no No NO true True TRUE false False FALSE on On ON off Off OFF null Null NULL".split():
            self.assertTrue(yamlfmt.dump({w: 1}).startswith('"'), w)


class ScalarTest(unittest.TestCase):
    def test_ambiguous_strings_quoted(self):
        self.assertEqual(yamlfmt.dump({"a": "true", "b": "123"}), 'a: "true"\nb: "123"\n')

    def test_floats(self):
        self.assertEqual(yamlfmt.dump([1e-05]), "- 1.0e-05\n")
        self.assertEqual(yamlfmt.dump([1.5]), "- 1.5\n")
        self.assertEqual(yamlfmt.dump([1e16]), "- 1.0e+16\n")
        self.assertEqual(yamlfmt.dump([1.5e-07]), "- 1.5e-07\n")

    def test_non_finite_floats_raise(self):
        for v in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                yamlfmt.dump({"a": v})

    def test_bool_is_not_int(self):
        self.assertEqual(yamlfmt.dump({"a": True, "b": False}), "a: true\nb: false\n")

    def test_control_chars_escaped(self):
        out = yamlfmt.dump({"a": "\u0085 \x7f\x1b"})
        self.assertEqual(out, 'a: "\\u0085\\u2028\\u007f\\u001b"\n')

    def test_printable_non_ascii_raw(self):
        out = yamlfmt.dump({"a": "é\U0001F600"})
        self.assertEqual(out, 'a: "é\U0001F600"\n')

    def test_surrogate_and_bom_escaped(self):
        out = yamlfmt.dump({"a": "﻿￾￿\ud800"})
        self.assertEqual(out, 'a: "\\ufeff\\ufffe\\uffff\\ud800"\n')


class RoundTripTest(unittest.TestCase):
    def test_tricky_corpus(self):
        obj = {
            "uni": "é \U0001F600 日本",
            "ctl": "a\tb\nc\r\u0085  \x00\x1b\x7f",
            "empties": {"d": {}, "l": [], "n": [{}, []]},
            "floats": [1.5, 1e-05, 1e16, -0.0, 3.0],
            "ints": [0, -1, 10**20],
            "quoted": {"yes": "yes", "200": "200", "POST /x": "~", "a.b": "null"},
            "nested": [[1, [2, 3]], [], [{"k": [None, True]}]],
            "special": [": x", "- y", "#c", "'q'", '"d"', "", " lead", "trail "],
        }
        self.assertEqual(_roundtrip(obj), obj)


if __name__ == "__main__":
    unittest.main()
