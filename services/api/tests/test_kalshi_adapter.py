from datetime import UTC, datetime
from decimal import Decimal

from tinli_api.venues import kalshi

TICKER = "KXWCADVANCE-26JUL06USABEL-USA"
NOW = datetime(2026, 7, 6, tzinfo=UTC)


def test_parse_market(load_fixture):
    raw = load_fixture(f"kalshi/market_{TICKER}.json")["market"]
    m = kalshi.parse_market(raw, NOW)
    assert m.id == f"kalshi:{TICKER}"
    assert m.venue == "kalshi"
    assert m.question == "USA vs Belgium: To Advance"
    assert isinstance(m.yes_price, Decimal)
    assert m.best_bid == Decimal("0.5200")
    assert m.best_ask == Decimal("0.5300")
    assert m.best_bid < m.best_ask
    assert m.no_price == 1 - m.yes_price
    assert m.liquidity is None  # venue field is deprecated, never mapped
    assert m.close_ts.tzinfo is not None


def test_parse_market_empty_quotes_become_none():
    raw = {
        "ticker": "KXTEST",
        "title": "t",
        "last_price_dollars": "0.5000",
        "yes_bid_dollars": "0.0000",  # no bids resting
        "yes_ask_dollars": "1.0000",  # no asks resting
        "volume_24h_fp": "0.00",
        "close_time": "2026-12-31T00:00:00Z",
    }
    m = kalshi.parse_market(raw, NOW)
    assert m.best_bid is None
    assert m.best_ask is None


def test_parse_orderbook_derives_asks_and_sorts_best_first(load_fixture):
    raw = load_fixture(f"kalshi/orderbook_{TICKER}.json")
    ob = kalshi.parse_orderbook(TICKER, raw, NOW)
    assert ob.bids and ob.asks
    # best-first: bids descending, asks ascending
    bid_prices = [level.price for level in ob.bids]
    ask_prices = [level.price for level in ob.asks]
    assert bid_prices == sorted(bid_prices, reverse=True)
    assert ask_prices == sorted(ask_prices)
    assert ob.bids[0].price < ob.asks[0].price  # book not crossed
    # derived asks: every ask price must be 1 - some raw NO bid
    raw_no_prices = {Decimal(p) for p, _ in raw["orderbook_fp"]["no_dollars"]}
    assert all((1 - level.price) in raw_no_prices for level in ob.asks)
    # fixture arrives ascending (worst-first) — the resort is load-bearing
    raw_yes = [Decimal(p) for p, _ in raw["orderbook_fp"]["yes_dollars"]]
    assert raw_yes == sorted(raw_yes), "venue changed book ordering; revisit VENUES.md"


def test_parse_orderbook_empty():
    ob = kalshi.parse_orderbook("KXTEST", {"orderbook_fp": {"yes_dollars": [], "no_dollars": []}}, NOW)
    assert ob.bids == [] and ob.asks == []
