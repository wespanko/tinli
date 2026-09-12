"""M15 crypto ladders: adapters on recorded fixtures, engine invariants on
the real chain, and the /v1/crypto route in demo mode."""

import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tinli_api import datasource
from tinli_api.venues import deribit, kalshi
from tinli_crypto import compute_ladder
from tinli_crypto.engine import build_surface

NOW = datetime(2026, 9, 12, 21, 0, tzinfo=UTC)


def test_parse_deribit_instrument():
    coin, expiry, strike, kind = deribit.parse_instrument("BTC-13SEP26-77000-C")
    assert coin == "BTC"
    assert expiry == datetime(2026, 9, 13, 8, 0, tzinfo=UTC)
    assert strike == Decimal("77000")
    assert kind == "call"
    assert deribit.parse_instrument("ETH-25DEC26-3000-P")[3] == "put"


def test_parse_deribit_summaries(load_fixture):
    raw = load_fixture("deribit/summary_BTC.json")["result"]
    quotes = deribit.parse_summaries(raw)
    assert len(quotes) == len(raw) > 500
    q = next(x for x in quotes if x.mark_iv is not None and x.bid_coin is not None)
    assert isinstance(q.bid_coin, Decimal)
    assert Decimal("0.01") < q.mark_iv < Decimal("5")  # a FRACTION, not the venue's percent
    assert q.expiry.tzinfo is not None and q.expiry.hour == 8
    # an empty side is None, never 0
    assert all(x.bid_coin is None or x.bid_coin > 0 for x in quotes)


def test_parse_deribit_index(load_fixture):
    idx = deribit.parse_index(load_fixture("deribit/index_BTC.json"))
    assert isinstance(idx, Decimal) and idx > 1000


def test_parse_kalshi_binary_market(load_fixture):
    raw = load_fixture("kalshi/series_KXBTCD.json")["markets"]
    parsed = [b for b in (kalshi.parse_binary_market(m, NOW) for m in raw) if b is not None]
    assert parsed
    b = parsed[0]
    assert b.close_ts.tzinfo is not None and b.close_ts.hour == 21  # 5pm ET
    assert isinstance(b.strike, Decimal)
    # a quoted side always carries a size; an empty side carries neither
    for x in parsed:
        assert (x.bid is None) == (x.bid_size is None)
        assert (x.ask is None) == (x.ask_size is None)


def test_parse_kalshi_binary_market_rejects_ranges():
    raw = {"ticker": "KXBTC-X-B1", "strike_type": "between", "floor_strike": 1, "cap_strike": 2,
           "close_time": "2026-09-13T21:00:00Z", "yes_bid_dollars": "0.1", "yes_ask_dollars": "0.2"}
    assert kalshi.parse_binary_market(raw, NOW) is None


def _ladder(load_fixture, coin="BTC"):
    series = datasource.CRYPTO_SERIES[coin]
    raw = load_fixture(f"kalshi/series_{series}.json")["markets"]
    binaries = [b for b in (kalshi.parse_binary_market(m, NOW) for m in raw) if b is not None]
    options = deribit.parse_summaries(load_fixture(f"deribit/summary_{coin}.json")["result"])
    index = deribit.parse_index(load_fixture(f"deribit/index_{coin}.json"))
    now = max(b.fetched_at for b in binaries)
    return compute_ladder(coin, binaries, options, index, now=now, rf_rate=Decimal("0.04")), index


def test_ladder_invariants_on_real_chain(load_fixture):
    ladder, index = _ladder(load_fixture)
    assert ladder.expiries, "no open expiries in the fixture"
    for exp in ladder.expiries:
        assert exp.hedge_expiry is None or exp.hedge_expiry >= exp.close_ts
        assert exp.hedge_gap_hours is None or exp.hedge_gap_hours >= 0
        strikes = [it.strike for it in exp.items]
        assert strikes == sorted(strikes)
        fvs = [it.fair_value for it in exp.items if it.fair_value is not None]
        # a digital call is monotone decreasing in strike
        assert all(a >= b for a, b in zip(fvs, fvs[1:]))
        assert all(Decimal(0) <= fv <= Decimal(1) for fv in fvs)
        for it in exp.items:
            if it.hedge_bid is not None and it.hedge_ask is not None:
                assert it.hedge_ask >= it.hedge_bid
            # no quote, no claimed edge
            if it.kalshi.bid is None and it.kalshi.ask is None:
                assert it.model_edge is None and it.hedge_edge is None
            # the hedge edge is a locked profit: never above the unhedged view
            if it.hedge_edge is not None and it.model_edge is not None:
                assert it.hedge_edge <= it.model_edge + Decimal("0.05")  # fees + bound slack


def test_surface_atm_iv_is_sane(load_fixture):
    options = deribit.parse_summaries(load_fixture("deribit/summary_BTC.json")["result"])
    index = deribit.parse_index(load_fixture("deribit/index_BTC.json"))
    surface = build_surface(options, index, NOW)
    assert surface.slices
    iv = surface.iv_at(float(index), surface.slices[0].t_years)
    assert 0.05 < iv < 3.0


@pytest.fixture
def demo_client(monkeypatch):
    monkeypatch.setenv("TINLI_DEMO", "1")
    datasource.reset_source()
    from tinli_api.main import app

    with TestClient(app) as c:
        yield c
    datasource.reset_source()


def test_crypto_route_demo(demo_client):
    for coin in ("BTC", "ETH"):
        r = demo_client.get(f"/v1/crypto/{coin}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["coin"] == coin
        assert body["assumptions"]
        assert body["expiries"]
        item = body["expiries"][0]["items"][0]
        for key in ("fair_value", "hedge_bid", "hedge_ask", "hedge_edge", "max_size", "iv"):
            assert key in item
    assert demo_client.get("/v1/crypto/DOGE").status_code == 422
