"""Kalshi Trade API v2 adapter.

Endpoints, auth (none for market data), and response-shape notes:
docs/VENUES.md. Verified live 2026-07-05.

Parsing rules pinned by fixtures:
- All prices are decimal dollar strings ("0.0475") -> Decimal, never float.
- A yes_bid of 0 / yes_ask of 1 means "no order", not a price -> None.
- Orderbook returns BIDS ONLY on both sides; the YES ask book is derived
  from NO bids: a NO bid of size s at price p is a YES ask of size s at 1-p.
"""

from datetime import UTC, datetime
from decimal import Decimal

from tinli_schema import Market, Orderbook, OrderbookLevel

from tinli_api.venues.client import get_json

BASE = "https://api.elections.kalshi.com/trade-api/v2"

ZERO = Decimal("0")
ONE = Decimal("1")


def _price_or_none(raw: str | None, *, empty: Decimal) -> Decimal | None:
    if raw is None:
        return None
    value = Decimal(raw)
    return None if value == empty else value


# market.status vocabulary differs from the ?status= query param (VENUES.md)
_STATUS = {
    "active": "open",
    "closed": "closed",
    "determined": "settled",
    "finalized": "settled",
    "settled": "settled",
}


def parse_market(raw: dict, fetched_at: datetime) -> Market:
    ticker = raw["ticker"]
    yes_price = Decimal(raw["last_price_dollars"])
    return Market(
        id=f"kalshi:{ticker}",
        venue="kalshi",
        question=raw.get("title") or raw.get("yes_sub_title") or ticker,
        status=_STATUS.get(raw.get("status", ""), "unknown"),
        yes_price=yes_price,
        no_price=ONE - yes_price,
        best_bid=_price_or_none(raw.get("yes_bid_dollars"), empty=ZERO),
        best_ask=_price_or_none(raw.get("yes_ask_dollars"), empty=ONE),
        volume_24h=Decimal(raw.get("volume_24h_fp") or "0"),
        liquidity=None,  # liquidity_dollars is deprecated and always 0 (docs/VENUES.md)
        close_ts=datetime.fromisoformat(raw["close_time"]),
        resolution_url=f"https://kalshi.com/markets/{ticker}",
        fetched_at=fetched_at,
    )


def parse_orderbook(ticker: str, raw: dict, fetched_at: datetime) -> Orderbook:
    book = raw.get("orderbook_fp") or {}
    yes_bids = book.get("yes_dollars") or []
    no_bids = book.get("no_dollars") or []
    bids = [OrderbookLevel(price=Decimal(p), size=Decimal(s)) for p, s in yes_bids]
    asks = [OrderbookLevel(price=ONE - Decimal(p), size=Decimal(s)) for p, s in no_bids]
    # sort defensively; ordering of the raw feed is unconfirmed (docs/VENUES.md TODO)
    bids.sort(key=lambda level: level.price, reverse=True)
    asks.sort(key=lambda level: level.price)
    return Orderbook(
        market_id=f"kalshi:{ticker}",
        venue="kalshi",
        bids=bids,
        asks=asks,
        fetched_at=fetched_at,
    )


def get_market(ticker: str) -> Market:
    raw = get_json(f"{BASE}/markets/{ticker}")
    return parse_market(raw["market"], datetime.now(UTC))


def get_markets(tickers: list[str]) -> list[Market]:
    """One batched request for up to 1000 tickers."""
    raw = get_json(f"{BASE}/markets", params={"tickers": ",".join(tickers), "limit": 1000})
    now = datetime.now(UTC)
    return [parse_market(m, now) for m in raw.get("markets", [])]


def get_orderbook(ticker: str, depth: int = 20) -> Orderbook:
    raw = get_json(f"{BASE}/markets/{ticker}/orderbook", params={"depth": depth})
    return parse_orderbook(ticker, raw, datetime.now(UTC))


# -- BYOK (M9): authenticated, READ-ONLY portfolio access ---------------------
# Response shape from docs.kalshi.com/api-reference/portfolio/get-positions.md
# (read 2026-07-20): market_positions[] with position_fp (signed fixed-point
# contracts, + = YES / - = NO), *_dollars fixed-point strings, cursor
# pagination. TODO(BYOK-live): shape is doc-derived — pin against a real
# account response the first time a key is available, then record a
# sanitized fixture.


def get_positions(auth) -> list["AccountPosition"]:
    """All non-flat positions in the user's Kalshi account. Requires BYOK
    auth; never called without it. GET only — Tinli never places orders."""
    from tinli_schema import AccountPosition

    path = "/trade-api/v2/portfolio/positions"
    out: list[AccountPosition] = []
    cursor: str | None = None
    while True:
        params = {"limit": "200"}
        if cursor:
            params["cursor"] = cursor
        raw = get_json(f"{BASE}/portfolio/positions", params=params,
                       headers=lambda: auth.headers("GET", path))
        for p in raw.get("market_positions") or []:
            signed = Decimal(p.get("position_fp") or "0")
            if signed == 0:
                continue
            out.append(AccountPosition(
                ticker=p["ticker"],
                side="yes" if signed > 0 else "no",
                contracts=abs(signed),
                cost_basis=Decimal(p.get("market_exposure_dollars") or "0"),
                total_traded=Decimal(p.get("total_traded_dollars") or "0"),
                realized_pnl=Decimal(p.get("realized_pnl_dollars") or "0"),
                fees_paid=Decimal(p.get("fees_paid_dollars") or "0"),
                last_updated=(
                    datetime.fromisoformat(p["last_updated_ts"])
                    if p.get("last_updated_ts") else None
                ),
            ))
        cursor = raw.get("cursor")
        if not cursor:
            return out
