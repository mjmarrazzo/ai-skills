PY ?= python3
export PYTHONPATH := scripts

.PHONY: check unit check-ruby corpus golden

check: unit check-ruby

unit:
	$(PY) -m unittest discover -s tests -t . -v

check-ruby:
	@if command -v ruby >/dev/null 2>&1; then TEST_CASES_YAML_BACKEND=ruby $(PY) -m unittest tests.test_load tests.test_yamlfmt; else echo "check-ruby: ruby not found, skipped"; fi

corpus:
	$(PY) -m unittest tests.test_corpus -v

golden:
	@test "$(UPDATE)" = "1" || { echo "golden: refusing to rewrite goldens without UPDATE=1"; exit 1; }
	$(PY) -m tests.regen_golden
	git status --short -- tests/golden
	git diff --stat -- tests/golden
