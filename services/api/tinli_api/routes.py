from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tinli_schema import Market, Orderbook

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
