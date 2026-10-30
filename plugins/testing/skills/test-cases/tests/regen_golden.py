import shutil

from test_cases import cli

from . import support

GOLDEN_SETS = {
    "swagger2": ("tests/fixtures/specs/swagger2.yaml", None),
    "oas3": ("tests/fixtures/specs/oas3.yaml", None),
    "oas3-min": ("tests/fixtures/specs/oas3-min.json", None),
    "oas3-msp": ("tests/fixtures/specs/oas3.yaml", "profiles/msp.yaml"),
}


def generate(name, spec, profile_path, out):
    argv = ["derive", spec, *(["--profile", profile_path] if profile_path else []), "-o", out]
    rc = cli.main(argv)
    assert rc == 0, f"derive failed for {name}: {rc}"
    rc = cli.main(["render", "--cases", out])
    assert rc == 0, f"render failed for {name}: {rc}"


def main():
    with support.in_skill_dir():
        for name, (spec, profile_path) in GOLDEN_SETS.items():
            out = f"tests/golden/{name}"
            shutil.rmtree(out, ignore_errors=True)
            generate(name, spec, profile_path, out)


if __name__ == "__main__":
    main()
