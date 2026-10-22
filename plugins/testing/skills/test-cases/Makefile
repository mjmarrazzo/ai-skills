PY ?= python3
export PYTHONPATH := scripts

.PHONY: check unit

check: unit

unit:
	$(PY) -m unittest discover -s tests -t . -v
