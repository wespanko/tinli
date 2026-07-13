"""M4 endpoint tests — /v1/risk against recorded fixtures (TINLI_DEMO=1)
and the checked-in example book in data/positions.yaml."""

import pytest
from fastapi.testclient import TestClient

from tinli_api import datasource
from tinli_api.main import app


@pytest.fixture(autouse=True)
def demo_mode(monkeypatch):
    monkeypatch.setenv("TINLI_DEMO", "1")
    monkeypatch.delenv("TINLI_POSITIONS", raising=False)
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


def test_missing_positions_file_is_an_empty_report(client, tmp_path, monkeypatch):
    monkeypatch.setenv("TINLI_POSITIONS", str(tmp_path / "nope.yaml"))
    report = client.get("/v1/risk").json()
    assert report["positions"] == []
    assert float(report["var_95_parametric"]) == 0
    assert float(report["max_loss"]) == 0
