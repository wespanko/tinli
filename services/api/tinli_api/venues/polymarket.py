"""Polymarket adapter: Gamma (metadata) + CLOB (books).

Endpoints and response-shape notes: docs/VENUES.md. Verified live 2026-07-05.

Parsing rules pinned by fixtures:
- Gamma's outcomes/outcomePrices/clobTokenIds are JSON-encoded STRINGS —
  they must be json.loads'd a second time.
- CLOB book levels arrive WORST-first; best bid/ask is the last element.
  We re-sort to best-first so nothing downstream can get this wrong.
- A Gamma market is one binary question; clobTokenIds[pm_yes_token] is the
  YES outcome token (pm_yes_token comes from data/event_map.yaml).
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

from tinli_schema import Market, Orderbook, OrderbookLevel

from tinli_api.venues.client import get_json

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def _decode_str_list(raw) -> list:
    return json.loads(raw) if isinstance(raw, str) else list(raw)


def yes_token_id(gamma_market: dict, yes_index: int) -> str:
    return _decode_str_list(gamma_market["clobTokenIds"])[yes_index]


def parse_market(gamma_market: dict, yes_index: int, fetched_at: datetime,
                 book: Orderbook | None = None) -> Market:
    prices = _decode_str_list(gamma_market["outcomePrices"])
    yes_price = Decimal(str(prices[yes_index]))
    condition_id = gamma_market["conditionId"]
    return Market(
        id=f"polymarket:{condition_id}",
        venue="polymarket",
        question=gamma_market["question"],
        yes_price=yes_price,
        no_price=Decimal(str(prices[1 - yes_index])),
        best_bid=book.bids[0].price if book and book.bids else None,
        best_ask=book.asks[0].price if book and book.asks else None,
        # str() first: Gamma serves these as JSON numbers (floats); going
        # through str keeps the printed digits instead of float noise
        volume_24h=Decimal(str(gamma_market.get("volume24hr") or 0)),
        liquidity=Decimal(str(gamma_market.get("liquidityNum") or 0)),
        close_ts=datetime.fromisoformat(gamma_market["endDate"].replace("Z", "+00:00")),
        resolution_url=f"https://polymarket.com/market/{gamma_market.get('slug', '')}",
        fetched_at=fetched_at,
    )


def parse_book(condition_id: str, raw_book: dict, fetched_at: datetime) -> Orderbook:
    def levels(side: str) -> list[OrderbookLevel]:
        return [
            OrderbookLevel(price=Decimal(lvl["price"]), size=Decimal(lvl["size"]))
            for lvl in raw_book.get(side) or []
        ]

    bids = sorted(levels("bids"), key=lambda level: level.price, reverse=True)
    asks = sorted(levels("asks"), key=lambda level: level.price)
    return Orderbook(
        market_id=f"polymarket:{condition_id}",
        venue="polymarket",
        bids=bids,
        asks=asks,
        fetched_at=fetched_at,
    )


def get_gamma_market(condition_id: str) -> dict:
    result = get_json(f"{GAMMA}/markets", params={"condition_ids": condition_id})
    if not result:
        raise LookupError(f"no Gamma market for conditionId {condition_id}")
    return result[0]


def get_orderbook(condition_id: str, token_id: str) -> Orderbook:
    raw = get_json(f"{CLOB}/book", params={"token_id": token_id})
    return parse_book(condition_id, raw, datetime.now(UTC))


def get_market(condition_id: str, yes_index: int) -> Market:
    gamma = get_gamma_market(condition_id)
    book = get_orderbook(condition_id, yes_token_id(gamma, yes_index))
    return parse_market(gamma, yes_index, datetime.now(UTC), book=book)
