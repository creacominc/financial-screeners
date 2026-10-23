.DEFAULT_GOAL := reports
PYTHON := .venv/bin/python

.PHONY: reports test
reports:
	@test -x "$(PYTHON)" || { echo 'Create .venv and install the project first; see README.md Setup.'; exit 1; }
	"$(PYTHON)" scripts/local_reports.py

test:
	"$(PYTHON)" -m pytest
