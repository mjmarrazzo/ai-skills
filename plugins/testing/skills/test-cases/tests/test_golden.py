import tempfile
import unittest
from pathlib import Path

from . import support
from .regen_golden import GOLDEN_SETS, generate

HINT = "run: UPDATE=1 make golden"


def _tree(root):
    root = Path(root)
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


class GoldenTest(unittest.TestCase):
    def test_goldens_match(self):
        for name, (spec, profile_path) in GOLDEN_SETS.items():
            with self.subTest(set=name), tempfile.TemporaryDirectory() as tmp:
                with support.in_skill_dir():
                    generate(name, spec, profile_path, tmp)
                    expected_dir = support.GOLDEN / name
                    self.assertTrue(expected_dir.is_dir(), f"missing tests/golden/{name}; {HINT}")
                    want, got = _tree(expected_dir), _tree(tmp)
                self.assertEqual(sorted(want), sorted(got), f"file set differs; {HINT}")
                for rel in want:
                    self.assertEqual(want[rel], got[rel], f"{name}/{rel} differs; {HINT}")


if __name__ == "__main__":
    unittest.main()
