import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_cases import load

HAS_RUBY = shutil.which("ruby") is not None

PARITY_DOC = """\
base: &base
  n: 1.5
  d: 2024-01-02
  t: 2024-01-02T03:04:05Z
ref: *base
200: ok
yes: flag
~: nothing
sym: :sym
"""


def _write(d, name, text):
    p = Path(d) / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def _load(path, backend):
    with mock.patch.dict(os.environ, {"TEST_CASES_YAML_BACKEND": backend}):
        return load.load_doc(path)


class LoadDocTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def test_json_loads_unchanged(self):
        p = _write(self.d, "a.json", json.dumps({"a": [1, {"b": None}]}))
        self.assertEqual(load.load_doc(p), {"a": [1, {"b": None}]})

    def test_int_key_becomes_string(self):
        p = _write(self.d, "a.yaml", "200:\n  x: 1\n")
        self.assertEqual(_load(p, "pyyaml"), {"200": {"x": 1}})

    def test_bool_and_null_keys(self):
        p = _write(self.d, "a.yaml", "yes: 1\n~: 2\n")
        self.assertEqual(_load(p, "pyyaml"), {"true": 1, "null": 2})

    def test_date_scalar(self):
        p = _write(self.d, "a.yaml", "d: 2024-01-02\n")
        self.assertEqual(_load(p, "pyyaml"), {"d": "2024-01-02"})

    def test_datetime_utc(self):
        p = _write(self.d, "a.yaml", "t: 2024-01-02T03:04:05Z\n")
        self.assertEqual(_load(p, "pyyaml"), {"t": "2024-01-02T03:04:05Z"})

    def test_naive_datetime_with_micros(self):
        p = _write(self.d, "a.yaml", "t: 2024-01-02 03:04:05.5\n")
        self.assertEqual(_load(p, "pyyaml"), {"t": "2024-01-02T03:04:05.500000Z"})

    def test_symbol_scalar_pyyaml(self):
        p = _write(self.d, "a.yaml", "s: :sym\n")
        self.assertEqual(_load(p, "pyyaml"), {"s": ":sym"})

    @unittest.skipUnless(HAS_RUBY, "ruby not installed")
    def test_symbol_scalar_ruby(self):
        p = _write(self.d, "a.yaml", "s: :sym\n")
        self.assertEqual(_load(p, "ruby"), {"s": ":sym"})

    @unittest.skipUnless(HAS_RUBY, "ruby not installed")
    def test_ruby_matches_pyyaml(self):
        p = _write(self.d, "a.yaml", PARITY_DOC)
        self.assertEqual(_load(p, "ruby"), _load(p, "pyyaml"))

    @unittest.skipUnless(HAS_RUBY, "ruby not installed")
    def test_auto_falls_back_to_ruby(self):
        p = _write(self.d, "a.yaml", "a: 1\n")
        with mock.patch.object(load, "_pyyaml", return_value=None):
            self.assertEqual(_load(p, "auto"), {"a": 1})

    def test_no_backend(self):
        p = _write(self.d, "a.yaml", "a: 1\n")
        with mock.patch.object(load, "_pyyaml", return_value=None), \
                mock.patch.object(load, "_ruby_exe", return_value=None):
            with self.assertRaises(load.LoadError) as cm:
                _load(p, "auto")
        self.assertIn("no YAML backend", str(cm.exception))

    @unittest.skipUnless(HAS_RUBY, "ruby not installed")
    def test_malformed_yaml_under_ruby(self):
        p = _write(self.d, "a.yaml", "a: [unclosed\n")
        with self.assertRaises(load.LoadError) as cm:
            _load(p, "ruby")
        prefix = f"{p}: ruby YAML parse failed:"
        self.assertTrue(str(cm.exception).startswith(prefix))
        self.assertTrue(str(cm.exception)[len(prefix):].strip())

    def test_missing_file(self):
        with self.assertRaises(load.LoadError) as cm:
            load.load_doc(os.path.join(self.d, "nope.yaml"))
        self.assertIn("not found", str(cm.exception))

    def test_top_level_list(self):
        p = _write(self.d, "a.yaml", "- 1\n- 2\n")
        with self.assertRaises(load.LoadError):
            _load(p, "pyyaml")

    def test_bogus_backend(self):
        p = _write(self.d, "a.yaml", "a: 1\n")
        with self.assertRaises(load.LoadError):
            _load(p, "bogus")

    def test_sha256_file(self):
        p = _write(self.d, "a.bin", "hello")
        self.assertEqual(load.sha256_file(p), hashlib.sha256(b"hello").hexdigest())

    def test_load_profile_none(self):
        self.assertIsNone(load.load_profile(None))


if __name__ == "__main__":
    unittest.main()
