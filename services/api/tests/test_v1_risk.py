"""M4 endpoint tests — /v1/risk against recorded fixtures (TINLI_DEMO=1)
and the TEST-OWNED example book (fixtures/positions_example.yaml).

data/positions.yaml is the user's editable file: the only assertion tests
may make about it is that it parses."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tinli_api import datasource
from tinli_api.main import app

EXAMPLE_BOOK = Path(__file__).parent / "fixtures" / "positions_example.yaml"


@pytest.fixture(autouse=True)
def demo_mode(monkeypatch):
    monkeypatch.setenv("TINLI_DEMO", "1")
    monkeypatch.setenv("TINLI_POSITIONS", str(EXAMPLE_BOOK))
    datasource.reset_source()
    yield
    datasource.reset_source()


@pytest.fixture
def client():
    return TestClient(app)


def test_risk_report_marks_the_example_book(client):
    r = client.get("/v1/risk")
    assert r.status_code == 200
    report = r.json()
    # the example book references pair-mapped markets, so every leg marks
    assert len(report["positions"]) == 3
    assert report["unmarked_positions"] == 0
    for row in report["positions"]:
        assert row["mark"] is not None
        assert isinstance(row["mark"], str), "Decimals must travel as strings"
    # the USA/Belgium legs share one event; the Fed leg is its own
    assert len(report["by_event"]) == 2


def test_risk_has_both_var_flavors_and_assumptions(client):
    report = client.get("/v1/risk").json()
    assert isinstance(report["var_95_parametric"], str)
    assert isinstance(report["var_95_monte_carlo"], str)
    assert float(report["var_95_parametric"]) <= float(report["max_loss"])
    assert float(report["var_95_monte_carlo"]) <= float(report["max_loss"])
    assert report["mc_seed"] == 7 and report["mc_draws"] == 20000
    assert any("normal approximation" in a for a in report["assumptions"])


def test_kelly_only_where_est_prob_given(client):
    rows = client.get("/v1/risk").json()["positions"]
    with_kelly = [r for r in rows if r["kelly_full"] is not None]
    assert len(with_kelly) == 1
    assert with_kelly[0]["position"]["market_id"] == "kalshi:KXFEDDECISION-26JUL-H0"


def test_unknown_position_is_unmarked_not_dropped(client, tmp_path, monkeypatch):
    book = tmp_path / "positions.yaml"
    book.write_text(
        "positions:\n"
        '  - market_id: "kalshi:DELISTED-MARKET"\n'
        "    side: yes\n"
        '    contracts: "10"\n'
        '    entry_price: "0.5"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("TINLI_POSITIONS", str(book))
    report = client.get("/v1/risk").json()
    assert report["unmarked_positions"] == 1
    assert len(report["positions"]) == 1
    assert report["positions"][0]["mark"] is None
    assert float(report["total_market_value"]) == 0
    assert any("EXCLUDED" in a for a in report["assumptions"])


def test_typoed_positions_file_is_422_not_500(client, tmp_path, monkeypatch):
    book = tmp_path / "positions.yaml"
    book.write_text(
        "positions:\n"
        '  - market_id: "kalshi:KXFEDDECISION-26JUL-H0"\n'
        "    side: yes\n"
        '    contracts: "10"\n'
        '    entry_price: "1.55"\n',  # out of range: hand-edit typo
        encoding="utf-8",
    )
    monkeypatch.setenv("TINLI_POSITIONS", str(book))
    r = client.get("/v1/risk")
    assert r.status_code == 422
    assert "entry_price" in r.json()["detail"]


def test_shipped_positions_file_parses(client, monkeypatch):
    """The ONLY assertion allowed about the user's file: it loads."""
    monkeypatch.delenv("TINLI_POSITIONS", raising=False)
    assert isinstance(datasource.load_positions(), list)


def test_bare_positions_key_is_empty_book_not_error(client, tmp_path, monkeypatch):
    book = tmp_path / "positions.yaml"
    book.write_text("positions:\n", encoding="utf-8")  # user deleted the examples
    monkeypatch.setenv("TINLI_POSITIONS", str(book))
    r = client.get("/v1/risk")
    assert r.status_code == 200
    assert r.json()["positions"] == []


@pytest.mark.parametrize(
    "content",
    [
        '- market_id: "kalshi:X"\n',  # top-level list, not a mapping
        "positions: 5\n",  # positions not a list
        "positions:\n  - just-a-string\n",  # entry not a mapping
    ],
)
def test_malformed_shapes_are_422_not_500(client, tmp_path, monkeypatch, content):
    book = tmp_path / "positions.yaml"
    book.write_text(content, encoding="utf-8")
    monkeypatch.setenv("TINLI_POSITIONS", str(book))
    r = client.get("/v1/risk")
    assert r.status_code == 422
    assert "positions.yaml is invalid" in r.json()["detail"]


def test_missing_positions_file_is_an_empty_report(client, tmp_path, monkeypatch):
    monkeypatch.setenv("TINLI_POSITIONS", str(tmp_path / "nope.yaml"))
    report = client.get("/v1/risk").json()
    assert report["positions"] == []
    assert float(report["var_95_parametric"]) == 0
    assert float(report["max_loss"]) == 0
