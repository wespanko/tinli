"""M2 endpoint tests — run entirely against recorded fixtures (TINLI_DEMO=1)."""

import pytest
from fastapi.testclient import TestClient

from tinli_api import datasource
from tinli_api.main import app


@pytest.fixture(autouse=True)
def demo_mode(monkeypatch):
    monkeypatch.setenv("TINLI_DEMO", "1")
    datasource.reset_source()
    yield
    datasource.reset_source()


@pytest.fixture
def client():
    return TestClient(app)


def test_markets_returns_both_venues_for_every_pair(client):
    r = client.get("/v1/markets")
    assert r.status_code == 200
    markets = r.json()
    assert len(markets) == 2 * 21
    assert {m["venue"] for m in markets} == {"kalshi", "polymarket"}
    assert all(m["event_key"] for m in markets)


def test_markets_prices_are_strings_not_floats(client):
    m = client.get("/v1/markets").json()[0]
    # Decimal must serialize as a JSON string to survive the trip to TS intact
    assert isinstance(m["yes_price"], str)


def test_markets_venue_filter(client):
    markets = client.get("/v1/markets", params={"venue": "kalshi"}).json()
    assert len(markets) == 21
    assert all(m["venue"] == "kalshi" for m in markets)


def test_markets_event_key_filter(client):
    markets = client.get("/v1/markets", params={"event_key": "fed-jul26-no-change"}).json()
    assert len(markets) == 2
    assert {m["venue"] for m in markets} == {"kalshi", "polymarket"}


def test_markets_bad_venue_rejected(client):
    assert client.get("/v1/markets", params={"venue": "predictit"}).status_code == 422


def test_orderbook_kalshi(client):
    r = client.get("/v1/markets/kalshi:KXWCADVANCE-26JUL06USABEL-USA/orderbook")
    assert r.status_code == 200
    book = r.json()
    assert book["venue"] == "kalshi"
    assert book["bids"] and book["asks"]
    prices = [float(level["price"]) for level in book["bids"]]
    assert prices == sorted(prices, reverse=True)


def test_orderbook_polymarket(client):
    cid = "0x83d646ac5646bf847f2dc0ce9c18c4d8909bbb7b050b31075afb9b67d3802b33"
    r = client.get(f"/v1/markets/polymarket:{cid}/orderbook")
    assert r.status_code == 200
    assert r.json()["venue"] == "polymarket"


def test_orderbook_unknown_market_404(client):
    assert client.get("/v1/markets/kalshi:NOPE/orderbook").status_code == 404


def test_pairs(client):
    r = client.get("/v1/pairs")
    assert r.status_code == 200
    pairs = r.json()
    assert len(pairs) == 21
    for p in pairs:
        assert p["kalshi"] is not None, f"{p['event_key']} missing kalshi quote"
        assert p["polymarket"] is not None, f"{p['event_key']} missing polymarket quote"
    trap = next(p for p in pairs if p["event_key"] == "wc26-best-host-usa")
    assert trap["criteria_verified"] is False
    assert "tie" in trap["notes"].lower()


def test_demo_fetched_at_is_recording_time_not_now(client):
    m = client.get("/v1/markets").json()[0]
    assert m["fetched_at"].startswith("2026-07-06"), "fixture data must not masquerade as fresh"
