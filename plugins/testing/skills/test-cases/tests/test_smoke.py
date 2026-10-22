import json
import os
import unittest

import test_cases
from tests import support


class SmokeTest(unittest.TestCase):
    def test_engine_version(self):
        self.assertEqual(test_cases.ENGINE, "test-cases/0.1.0")

    def test_repo_root_has_marketplace(self):
        self.assertTrue((support.REPO_ROOT / ".claude-plugin/marketplace.json").is_file())

    def test_in_skill_dir_restores_cwd_on_error(self):
        prev = os.getcwd()
        with self.assertRaises(RuntimeError):
            with support.in_skill_dir():
                self.assertEqual(os.path.realpath(os.getcwd()), os.path.realpath(support.SKILL_DIR))
                raise RuntimeError("boom")
        self.assertEqual(os.getcwd(), prev)

    def test_plugin_manifest(self):
        path = support.REPO_ROOT / "plugins/testing/.claude-plugin/plugin.json"
        self.assertEqual(json.loads(path.read_text())["name"], "testing")
