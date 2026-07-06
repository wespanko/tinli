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


def test_gamma_batch_refetches_resolved_markets_with_closed_flag(monkeypatch):
    """Gamma omits resolved markets from plain condition_ids queries (found
    live 2026-07-06 when the Wimbledon R16 markets settled). The batch fetch
    must re-query missing ids with closed=true instead of dropping the pair."""
    open_cid, resolved_cid = "0xaaa", "0xbbb"
    calls = []

    def fake_get_json(url, params=None):
        calls.append(params)
        params = params or []
        closed = ("closed", "true") in params
        if closed:
            return [{"conditionId": resolved_cid}]
        return [{"conditionId": open_cid}]  # Gamma silently hides 0xbbb

    monkeypatch.setattr(polymarket, "get_json", fake_get_json)
    result = polymarket.get_gamma_markets([open_cid, resolved_cid])
    assert set(result) == {open_cid, resolved_cid}
    assert len(calls) == 2
    # the follow-up must ask only for the missing id, with closed=true
    assert ("condition_ids", resolved_cid) in calls[1]
    assert ("condition_ids", open_cid) not in calls[1]
    assert ("closed", "true") in calls[1]


def test_gamma_batch_skips_followup_when_nothing_missing(monkeypatch):
    calls = []

    def fake_get_json(url, params=None):
        calls.append(params)
        return [{"conditionId": "0xaaa"}]

    monkeypatch.setattr(polymarket, "get_json", fake_get_json)
    result = polymarket.get_gamma_markets(["0xaaa"])
    assert set(result) == {"0xaaa"}
    assert len(calls) == 1, "no resolved markets -> no second request"


def test_gamma_single_falls_back_to_closed_then_raises(monkeypatch):
    def fake_get_json(url, params=None):
        return []

    monkeypatch.setattr(polymarket, "get_json", fake_get_json)
    import pytest as _pytest

    with _pytest.raises(LookupError):
        polymarket.get_gamma_market("0xdead")
