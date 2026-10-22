import json
import os
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path

from test_cases import ir, load

from . import support

LIST_PATH = Path(os.environ.get("TEST_CASES_CORPUS") or support.REPO_ROOT / ".claude-plans/test-cases/research/specs.txt")

KNOWN_DIVERGENCES: dict[str, str] = {
    "rep-platform-authorizer/docs/api.yaml": (
        "Ruby 2.6 libyaml rejects a plain scalar containing ':' inside a flow sequence ([a:b]); PyYAML accepts it"
    ),
}


@contextmanager
def backend(name):
    prev = os.environ.get("TEST_CASES_YAML_BACKEND")
    os.environ["TEST_CASES_YAML_BACKEND"] = name
    try:
        yield
    finally:
        if prev is None:
            del os.environ["TEST_CASES_YAML_BACKEND"]
        else:
            os.environ["TEST_CASES_YAML_BACKEND"] = prev


def _distinct_specs():
    seen = {}
    for line in LIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not Path(line).is_file():
            continue
        seen.setdefault(load.sha256_file(line), line)
    return list(seen.items())


def _survey_ops():
    p = LIST_PATH.parent / "survey.json"
    if not p.is_file():
        return {}
    return {e["path"]: e for e in json.loads(p.read_text(encoding="utf-8"))}


class CorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not LIST_PATH.is_file():
            raise unittest.SkipTest(f"corpus list not found: {LIST_PATH}")
        cls.specs = _distinct_specs()
        if not cls.specs:
            raise unittest.SkipTest("no corpus spec files exist")
        cls.survey = _survey_ops()

    def test_corpus(self):
        has_ruby = load._ruby_exe() is not None
        has_pyyaml = load._pyyaml() is not None
        exercised = 0
        for digest, path in self.specs:
            with self.subTest(spec=path):
                with backend("pyyaml" if has_pyyaml else "ruby"):
                    doc = load.load_doc(path)
                spec = ir.build_ir(doc, path, digest)
                py_dict = ir.to_dict(spec)

                if has_ruby and has_pyyaml and not any(path.endswith(k) for k in KNOWN_DIVERGENCES):
                    with backend("ruby"):
                        rb_doc = load.load_doc(path)
                    rb_dict = ir.to_dict(ir.build_ir(rb_doc, path, digest))
                    self.assertEqual(py_dict, rb_dict)

                entry = self.survey.get(path)
                if entry is not None:
                    expected = entry["ops"] - entry["methods"].get("x-amazon-apigateway-any-method", 0)
                    self.assertEqual(len(spec.operations), expected)
                exercised += 1
        self.assertEqual(exercised, len(self.specs))
        print(f"corpus: {len(self.specs)} distinct specs", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
