from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tinli_schema import Market, Orderbook, OrderbookLevel, PairMapping


def test_market_prices_are_decimal():
    m = Market(
        id="kalshi:KXTEST-26",
        venue="kalshi",
        question="Test?",
        yes_price="0.0475",
        no_price="0.9525",
        best_bid="0.047",
        best_ask="0.048",
        volume_24h="1000.00",
        close_ts=datetime(2026, 12, 31, tzinfo=UTC),
        resolution_url="https://kalshi.com/markets/KXTEST-26",
        fetched_at=datetime.now(UTC),
    )
    assert m.yes_price == Decimal("0.0475")
    assert isinstance(m.yes_price, Decimal)
    # deci-cent precision must survive — this is why float is banned
    assert str(m.yes_price) == "0.0475"


def test_venue_is_constrained():
    with pytest.raises(ValidationError):
        Market(
            id="x:1",
            venue="predictit",
            question="?",
            yes_price="0.5",
            no_price="0.5",
            best_bid=None,
            best_ask=None,
            volume_24h="0",
            close_ts=datetime.now(UTC),
            resolution_url="",
            fetched_at=datetime.now(UTC),
        )


def test_orderbook_levels():
    ob = Orderbook(
        market_id="polymarket:0xabc",
        venue="polymarket",
        bids=[OrderbookLevel(price="0.47", size="100")],
        asks=[OrderbookLevel(price="0.48", size="50")],
        fetched_at=datetime.now(UTC),
    )
    assert ob.bids[0].price == Decimal("0.47")


def test_pair_mapping_defaults_unverified():
    p = PairMapping(
        event_key="test-pair",
        question="?",
        kalshi_ticker="KXTEST",
        pm_condition_id="0xabc",
        pm_yes_token=0,
    )
    assert p.criteria_verified is False


def test_pair_mapping_token_index_bounded():
    with pytest.raises(ValidationError):
        PairMapping(
            event_key="k",
            question="?",
            kalshi_ticker="T",
            pm_condition_id="0x",
            pm_yes_token=2,
        )
