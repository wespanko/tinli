# Tinli — make setup | dev | demo | test | snapshot
# Works from Git Bash (sh) and cmd/PowerShell (ezwinports make).

ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python.exe
else
PY := .venv/bin/python
endif

.PHONY: setup dev demo test snapshot types

setup:
	python -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements-dev.txt
	cd apps/terminal && npm install --no-fund --no-audit

dev:
	$(PY) scripts/dev.py

demo:
	$(PY) scripts/dev.py --demo

test:
	$(PY) -m pytest
	cd apps/terminal && npx tsc --noEmit

# one snapshot; for continuous recording: .venv/Scripts/python scripts/snapshot.py --loop 30
snapshot:
	$(PY) scripts/snapshot.py

# regenerate apps/terminal/src/types.gen.ts from the pydantic models
types:
	$(PY) scripts/gen_types.py
