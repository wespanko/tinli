from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tinli_divergence import DivergenceItem, compute_pair, sort_items
from tinli_schema import Market, Orderbook, PairMapping

from tinli_api.datasource import get_source, load_pairs, pair_for_market_id
from tinli_api.venues.client import VenueHTTPError

router = APIRouter(prefix="/v1")


class PairQuote(BaseModel):
    event_key: str
    question: str
    criteria_verified: bool
    notes: str
    kalshi: Market | None
    polymarket: Market | None


@router.get("/markets")
def list_markets(
    venue: Literal["kalshi", "polymarket"] | None = None,
    status: Literal["open", "closed", "settled", "unknown"] | None = None,
    event_key: str | None = None,
) -> list[Market]:
    try:
        markets = get_source().markets()
    except VenueHTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if venue:
        markets = [m for m in markets if m.venue == venue]
    if status:
        markets = [m for m in markets if m.status == status]
    if event_key:
        markets = [m for m in markets if m.event_key == event_key]
    return markets


@router.get("/markets/{market_id}/orderbook")
def get_orderbook(market_id: str) -> Orderbook:
    pair = pair_for_market_id(market_id)
    if pair is None:
        raise HTTPException(status_code=404, detail=f"unknown market id: {market_id}")
    venue = market_id.split(":", 1)[0]
    try:
        return get_source().orderbook(pair, venue)
    except VenueHTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/divergence")
def divergence() -> list[DivergenceItem]:
    """Cross-venue divergence per mapped pair, sorted by |fee_adjusted_edge|
    descending with UNVERIFIED pairs always last.

    Sign convention (authoritative statement in tinli_divergence.engine):
    raw_basis_cents = 100 x (kalshi_yes_mid - polymarket_yes_mid); positive
    means Kalshi prices YES richer than Polymarket. Edges are computed from
    executable top-of-book asks only, never mids or last trades.
    """
    source = get_source()

    def one(pair: PairMapping) -> DivergenceItem:
        try:
            k_book = source.orderbook(pair, "kalshi")
            pm_book = source.orderbook(pair, "polymarket")
        except Exception:
            # a resolved/delisted leg must not take down the screener; an
            # empty book yields null edges for this pair
            empty = {"bids": [], "asks": [], "fetched_at": datetime.now(UTC)}
            k_book = Orderbook(market_id=f"kalshi:{pair.kalshi_ticker}", venue="kalshi", **empty)
            pm_book = Orderbook(
                market_id=f"polymarket:{pair.pm_condition_id}", venue="polymarket", **empty
            )
        return compute_pair(
            pair, k_book, pm_book, fetched_at=max(k_book.fetched_at, pm_book.fetched_at)
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        items = list(pool.map(one, load_pairs()))
    return sort_items(items)


@router.get("/pairs")
def list_pairs() -> list[PairQuote]:
    try:
        markets = get_source().markets()
    except VenueHTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    by_key: dict[tuple[str, str], Market] = {(m.event_key or "", m.venue): m for m in markets}
    return [
        PairQuote(
            event_key=p.event_key,
            question=p.question,
            criteria_verified=p.criteria_verified,
            notes=p.notes,
            kalshi=by_key.get((p.event_key, "kalshi")),
            polymarket=by_key.get((p.event_key, "polymarket")),
        )
        for p in load_pairs()
    ]
