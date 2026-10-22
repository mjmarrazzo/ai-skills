import os
from contextlib import contextmanager
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parents[3]
FIXTURES = SKILL_DIR / "tests" / "fixtures"
GOLDEN = SKILL_DIR / "tests" / "golden"


def spec_fixture(name):
    return str((FIXTURES / "specs" / name).relative_to(SKILL_DIR))


@contextmanager
def in_skill_dir():
    prev = os.getcwd()
    os.chdir(SKILL_DIR)
    try:
        yield
    finally:
        os.chdir(prev)
