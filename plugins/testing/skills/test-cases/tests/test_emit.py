import os
import tempfile
import unittest
from pathlib import Path

from test_cases import emit


class EmitTest(unittest.TestCase):
    def test_write_text_creates_parents_and_keeps_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a" / "b" / "f.txt"
            emit.write_text(p, "x\r\ny\n")
            self.assertEqual(p.read_bytes(), b"x\r\ny\n")

    def test_no_stray_temp_files(self):
        with tempfile.TemporaryDirectory() as d:
            emit.write_text(Path(d) / "f.txt", "x")
            self.assertEqual(os.listdir(d), ["f.txt"])

    def test_second_write_replaces(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            emit.write_text(p, "one")
            emit.write_text(p, "two")
            self.assertEqual(p.read_text(), "two")

    def test_write_outputs_writes_every_name(self):
        with tempfile.TemporaryDirectory() as d:
            emit.write_outputs(d, {"b.txt": "B", "sub/a.txt": "A"})
            self.assertEqual((Path(d) / "b.txt").read_text(), "B")
            self.assertEqual((Path(d) / "sub" / "a.txt").read_text(), "A")


if __name__ == "__main__":
    unittest.main()
