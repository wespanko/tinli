import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(rel: str):
        return json.loads((FIXTURES / rel).read_text(encoding="utf-8"))

    return _load
