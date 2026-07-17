"""Drift check: the committed generated TS types must match the models.

If this fails, a pydantic model changed without regenerating the UI types —
run `make types` and commit the result. This is the test that makes a
backend field rename break the build instead of silently rendering '—' in
the terminal.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import gen_types  # noqa: E402


def test_generated_ts_types_in_sync():
    committed = gen_types.OUT.read_text(encoding="utf-8")
    assert committed == gen_types.render(), (
        "apps/terminal/src/types.gen.ts is stale — run `make types` and commit"
    )
