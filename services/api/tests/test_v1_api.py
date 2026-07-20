"""M2 endpoint tests — run entirely against recorded fixtures (TINLI_DEMO=1).

Counts and dates derive from data/event_map.yaml and the fixture manifest —
the pair map is re-curated as markets resolve, and hardcoded totals would
rot on every refresh.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tinli_api import datasource
from tinli_api.main import app

FIXTURES = Path(__file__).parent / "fixtures"


def n_pairs() -> int:
    return len(datasource.load_pairs())


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
    assert len(markets) == 2 * n_pairs()
    assert {m["venue"] for m in markets} == {"kalshi", "polymarket"}
    assert all(m["event_key"] for m in markets)


def test_markets_prices_are_strings_not_floats(client):
    m = client.get("/v1/markets").json()[0]
    # Decimal must serialize as a JSON string to survive the trip to TS intact
    assert isinstance(m["yes_price"], str)


def test_markets_venue_filter(client):
    markets = client.get("/v1/markets", params={"venue": "kalshi"}).json()
    assert len(markets) == n_pairs()
    assert all(m["venue"] == "kalshi" for m in markets)


def test_markets_event_key_filter(client):
    markets = client.get("/v1/markets", params={"event_key": "fed-jul26-no-change"}).json()
    assert len(markets) == 2
    assert {m["venue"] for m in markets} == {"kalshi", "polymarket"}


def test_markets_bad_venue_rejected(client):
    assert client.get("/v1/markets", params={"venue": "predictit"}).status_code == 422


def test_orderbook_kalshi(client):
    r = client.get("/v1/markets/kalshi:KXFEDDECISION-26JUL-H0/orderbook")
    assert r.status_code == 200
    book = r.json()
    assert book["venue"] == "kalshi"
    assert book["bids"] and book["asks"]
    prices = [float(level["price"]) for level in book["bids"]]
    assert prices == sorted(prices, reverse=True)


def test_orderbook_polymarket(client):
    cid = "0x8bf1c1536ecb1c08fe13c6b71e8ab1f58bf3461c4cb79f5f1679f869a06aef86"
    r = client.get(f"/v1/markets/polymarket:{cid}/orderbook")
    assert r.status_code == 200
    assert r.json()["venue"] == "polymarket"


def test_orderbook_unknown_market_404(client):
    assert client.get("/v1/markets/kalshi:NOPE/orderbook").status_code == 404


def test_pairs(client):
    r = client.get("/v1/pairs")
    assert r.status_code == 200
    pairs = r.json()
    assert len(pairs) == n_pairs()
    for p in pairs:
        assert p["kalshi"] is not None, f"{p['event_key']} missing kalshi quote"
        assert p["polymarket"] is not None, f"{p['event_key']} missing polymarket quote"
    trap = next(p for p in pairs if p["event_key"] == "wc26-best-host-usa")
    assert trap["criteria_verified"] is False
    assert "tie" in trap["notes"].lower()


def test_demo_fetched_at_is_recording_time_not_now(client):
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    recorded_date = manifest["recorded_at"][:10]
    m = client.get("/v1/markets").json()[0]
    assert m["fetched_at"].startswith(recorded_date), (
        "fixture data must not masquerade as fresh"
    )


def test_divergence_endpoint(client):
    r = client.get("/v1/divergence")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == n_pairs()
    # unverified pairs must be last regardless of edge size
    verified_flags = [i["criteria_verified"] for i in items]
    first_unverified = verified_flags.index(False)
    assert all(not v for v in verified_flags[first_unverified:])
    # items with edges are sorted by |fee_adjusted_edge| descending
    edges = [
        abs(float(i["fee_adjusted_edge"]))
        for i in items
        if i["fee_adjusted_edge"] and i["criteria_verified"]
    ]
    assert edges == sorted(edges, reverse=True)
    # decimals travel as strings; sign convention field present
    with_edge = next(i for i in items if i["fee_adjusted_edge"])
    assert isinstance(with_edge["fee_adjusted_edge"], str)
    assert with_edge["direction"] in (
        "buy_yes_kalshi_no_polymarket",
        "buy_yes_polymarket_no_kalshi",
    )


def test_history_includes_basis_stats(client):
    r = client.get("/v1/history/fed-jul26-no-change")
    assert r.status_code == 200
    h = r.json()
    # stats always ship with the window; n counts only computable-basis rows,
    # so this holds for an empty window (n=0, everything None) too
    n_obs = sum(1 for p in h["points"] if p["raw_basis_cents"] is not None)
    assert h["stats"]["n"] == n_obs
    if h["stats"]["mean_cents"] is not None:
        assert isinstance(h["stats"]["mean_cents"], str)


def test_lock_unknown_event_key_404(client):
    assert client.get("/v1/lock/nope-not-a-pair").status_code == 404


def test_lock_report_shape_and_conservatism(client):
    r = client.get("/v1/lock/fed-jul26-no-change")
    assert r.status_code == 200
    lock = r.json()
    assert lock["event_key"] == "fed-jul26-no-change"
    # assumptions ship IN the payload, always — at least the 4 base ones
    assert len(lock["assumptions"]) >= 4
    assert lock["direction"] in (
        None,
        "buy_yes_kalshi_no_polymarket",
        "buy_yes_polymarket_no_kalshi",
    )
    for pt in lock["points"]:
        # decimals travel as strings, and profit + capital must reconcile
        # conservatively: profit floored, capital ceilinged, so
        # capital + profit <= size (never >)
        assert isinstance(pt["capital"], str)
        assert float(pt["capital"]) + float(pt["total_profit"]) <= float(pt["size"]) + 1e-9
    sizes = [float(pt["size"]) for pt in lock["points"]]
    assert sizes == sorted(sizes)
    if lock["optimal"] is not None:
        assert float(lock["optimal"]["total_profit"]) > 0
        profits = [float(pt["total_profit"]) for pt in lock["points"]]
        assert float(lock["optimal"]["total_profit"]) == max(profits)
    # horizon floored at 6h -> annualized return only quoted with a horizon
    if lock["annualized_return"] is not None:
        assert lock["days_to_resolution"] is not None
        assert float(lock["days_to_resolution"]) >= 0.25


def test_lock_unverified_pair_carries_trap_warning(client):
    lock = client.get("/v1/lock/wc26-best-host-usa").json()
    assert lock["criteria_verified"] is False
    assert any("UNVERIFIED" in a for a in lock["assumptions"])
