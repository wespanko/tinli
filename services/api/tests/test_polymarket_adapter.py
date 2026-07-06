from datetime import UTC, datetime
from decimal import Decimal

from tinli_api.venues import polymarket

CID = "0x83d646ac5646bf847f2dc0ce9c18c4d8909bbb7b050b31075afb9b67d3802b33"  # USA/BEL advance
NOW = datetime(2026, 7, 6, tzinfo=UTC)


def test_yes_token_id_double_decodes_json_string(load_fixture):
    gamma = load_fixture(f"polymarket/gamma_{CID}.json")
    assert isinstance(gamma["clobTokenIds"], str), "fixture should preserve the raw JSON-string"
    token = polymarket.yes_token_id(gamma, 0)
    assert isinstance(token, str) and token.isdigit()


def test_parse_market(load_fixture):
    gamma = load_fixture(f"polymarket/gamma_{CID}.json")
    m = polymarket.parse_market(gamma, 0, NOW)
    assert m.id == f"polymarket:{CID}"
    assert m.venue == "polymarket"
    assert "Belgium" in m.question
    assert isinstance(m.yes_price, Decimal)
    # outcomes are ["United States", "Belgium"]; token 0 = USA advances
    assert m.yes_price + m.no_price == Decimal("1")
    assert m.liquidity is not None and m.liquidity > 0
    assert m.close_ts.tzinfo is not None
    assert m.best_bid is None  # no book passed


def test_parse_book_resorts_worst_first_feed(load_fixture):
    raw = load_fixture(f"polymarket/book_{CID}.json")
    ob = polymarket.parse_book(CID, raw, NOW)
    assert ob.bids and ob.asks
    bid_prices = [level.price for level in ob.bids]
    ask_prices = [level.price for level in ob.asks]
    assert bid_prices == sorted(bid_prices, reverse=True)
    assert ask_prices == sorted(ask_prices)
    assert ob.bids[0].price < ob.asks[0].price
    # the raw feed is worst-first (VENUES.md); pin that so a venue change screams
    raw_bids = [Decimal(l["price"]) for l in raw["bids"]]
    assert raw_bids[-1] == max(raw_bids), "venue changed book ordering; revisit VENUES.md"


def test_parse_market_with_book_fills_top_of_book(load_fixture):
    gamma = load_fixture(f"polymarket/gamma_{CID}.json")
    raw_book = load_fixture(f"polymarket/book_{CID}.json")
    book = polymarket.parse_book(CID, raw_book, NOW)
    m = polymarket.parse_market(gamma, 0, NOW, book=book)
    assert m.best_bid == book.bids[0].price
    assert m.best_ask == book.asks[0].price
    assert m.best_bid < m.best_ask
