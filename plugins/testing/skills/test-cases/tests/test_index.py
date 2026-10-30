import tempfile
import unittest
from pathlib import Path

from test_cases import index, load

GLOBS = ["**/src/test/**/*.kt", "**/src/test/**/*.java"]


def _touch(root, rel, text=""):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class FakeIndexer:
    def __init__(self, name, detects):
        self.name = name
        self._detects = detects

    def detect(self, rel_paths):
        return self._detects

    def index(self, sources, ctx):
        return {}


class DiscoverTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def test_default_globs_find_kt_and_java_under_test_only(self):
        _touch(self.root, "a/src/test/kotlin/com/x/FooTest.kt")
        _touch(self.root, "a/src/test/java/com/x/BarTest.java")
        _touch(self.root, "a/src/main/kotlin/com/x/Main.kt")
        self.assertEqual(
            load.discover_tests(self.root, GLOBS, []),
            ["a/src/test/java/com/x/BarTest.java", "a/src/test/kotlin/com/x/FooTest.kt"],
        )

    def test_results_sorted_unique_posix(self):
        _touch(self.root, "src/test/b/Z.kt")
        _touch(self.root, "src/test/a/A.kt")
        out = load.discover_tests(self.root, GLOBS + ["src/test/**/*.kt"], [])
        self.assertEqual(out, ["src/test/a/A.kt", "src/test/b/Z.kt"])
        self.assertNotIn("\\", "".join(out))

    def test_excludes_remove_file(self):
        _touch(self.root, "src/test/a/A.kt")
        _touch(self.root, "src/test/a/LegacyTest.kt")
        out = load.discover_tests(self.root, GLOBS, ["*Legacy*"])
        self.assertEqual(out, ["src/test/a/A.kt"])

    def test_directories_are_skipped(self):
        (Path(self.root) / "src/test/dir.kt").mkdir(parents=True)
        self.assertEqual(load.discover_tests(self.root, GLOBS, []), [])

    def test_missing_root_raises(self):
        with self.assertRaises(load.LoadError):
            load.discover_tests(str(Path(self.root) / "nope"), GLOBS, [])

    def test_file_root_raises(self):
        _touch(self.root, "f.txt")
        with self.assertRaises(load.LoadError):
            load.discover_tests(str(Path(self.root) / "f.txt"), GLOBS, [])

    def test_read_sources_exact_text(self):
        _touch(self.root, "src/test/A.kt", "fun a() {}\né")
        out = load.read_sources(self.root, ["src/test/A.kt"])
        self.assertEqual(out, [index.SourceFile("src/test/A.kt", "fun a() {}\né")])

    def test_read_sources_replaces_bad_bytes(self):
        p = Path(self.root) / "B.kt"
        p.write_bytes(b"ok\xff")
        self.assertEqual(load.read_sources(self.root, ["B.kt"])[0].text, "ok�")


class SelectTests(unittest.TestCase):
    def setUp(self):
        self.a = FakeIndexer("alpha", False)
        self.b = FakeIndexer("beta", True)
        self.reg = {"alpha": self.a, "beta": self.b}

    def test_explicit_name(self):
        self.assertIs(index.select("alpha", [], self.reg), self.a)

    def test_unknown_name_lists_registry(self):
        with self.assertRaises(LookupError) as cm:
            index.select("gamma", [], self.reg)
        self.assertIn("alpha", str(cm.exception))
        self.assertIn("beta", str(cm.exception))

    def test_detection_picks_first_true(self):
        self.reg["gamma"] = FakeIndexer("gamma", True)
        self.assertIs(index.select(None, ["x"], self.reg), self.b)

    def test_nothing_detected(self):
        with self.assertRaisesRegex(LookupError, "no indexer matched"):
            index.select(None, [], {"alpha": self.a})

    def test_default_registry_is_module_indexers(self):
        index.INDEXERS["fake"] = FakeIndexer("fake", True)
        self.addCleanup(index.INDEXERS.pop, "fake")
        self.assertIs(index.select("fake", []), index.INDEXERS["fake"])


if __name__ == "__main__":
    unittest.main()
