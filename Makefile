# Tinli — make setup | dev | demo | test | snapshot
# Works from Git Bash (sh) and cmd/PowerShell (ezwinports make).

ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python.exe
else
PY := .venv/bin/python
endif

.PHONY: setup dev demo test snapshot types fixtures curate

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

# re-record demo fixtures for every pair in data/event_map.yaml
fixtures:
	$(PY) scripts/record_fixtures.py

# print candidate Kalshi<->Polymarket pairs for HUMAN curation of the map
curate:
	$(PY) scripts/curate.py
