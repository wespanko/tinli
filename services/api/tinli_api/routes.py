from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ValidationError

from tinli_divergence import DivergenceItem
from tinli_risk import RiskReport, build_report
from tinli_schema import Market, Orderbook, Position

from tinli_api.datasource import (
    get_source,
    load_pairs,
    load_positions,
    pair_for_market_id,
    readonly,
    save_positions,
)
from tinli_api.history import read_history
from tinli_api.screener import compute_all
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
    return compute_all(get_source())


class HistoryPoint(BaseModel):
    ts: datetime
    k_mid: Decimal | None
    p_mid: Decimal | None
    raw_basis_cents: Decimal | None
    fee_adjusted_edge: Decimal | None
    edge_at_size: Decimal | None


class HistoryResponse(BaseModel):
    event_key: str
    hours: int
    points: list[HistoryPoint]


def _mid(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    if bid is None or ask is None:
        return None
    return (bid + ask) / 2


@router.get("/history/{event_key}")
def history(event_key: str, hours: int = Query(default=24, ge=1, le=168)) -> HistoryResponse:
    """Recorded snapshots for one pair (see tinli_api.history). Empty points
    just means nothing recorded in the window — run `make snapshot`."""
    if not any(p.event_key == event_key for p in load_pairs()):
        raise HTTPException(status_code=404, detail=f"unknown event_key: {event_key}")
    points = [
        HistoryPoint(
            ts=r["ts"],
            k_mid=_mid(r["k_bid"], r["k_ask"]),
            p_mid=_mid(r["p_bid"], r["p_ask"]),
            raw_basis_cents=r["raw_basis_cents"],
            fee_adjusted_edge=r["fee_adjusted_edge"],
            edge_at_size=r["edge_at_size"],
        )
        for r in read_history(event_key, hours)
    ]
    return HistoryResponse(event_key=event_key, hours=hours, points=points)


@router.get("/risk")
def risk() -> RiskReport:
    """Risk report for the self-reported book in data/positions.yaml
    (override with TINLI_POSITIONS), marked against the current feed.

    Assumptions are IN THE PAYLOAD (report.assumptions) — the engine's
    authoritative statement lives in tinli_risk.var's module docstring.
    Positions missing from the feed come back unmarked and excluded from
    aggregates, never silently dropped.
    """
    try:
        positions = load_positions()
    except (ValidationError, yaml.YAMLError, ValueError) as exc:
        # positions.yaml is hand-edited; a typo is the USER'S file, not a
        # server fault — 422 with the pydantic/yaml/shape detail, never a 500
        raise HTTPException(
            status_code=422, detail=f"positions.yaml is invalid: {exc}"
        ) from exc
    try:
        markets = get_source().markets()
    except VenueHTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    by_id = {m.id: m for m in markets}
    marked_at = [m.fetched_at for m in markets if m.id in {p.market_id for p in positions}]
    fetched_at = max(marked_at) if marked_at else datetime.now(UTC)
    return build_report(positions, by_id, fetched_at=fetched_at)


class PositionsUpdate(BaseModel):
    positions: list[Position]


@router.put("/positions")
def put_positions(body: PositionsUpdate) -> PositionsUpdate:
    """Replace the self-reported book. The YAML file stays the single source
    of truth — this endpoint and hand-editing write the same file, atomically.
    Validation happens in the Position model before anything touches disk, so
    a bad payload can never corrupt the book. Read-only instances refuse."""
    if readonly():
        raise HTTPException(
            status_code=403, detail="read-only instance: positions editing is disabled"
        )
    save_positions(body.positions)
    return body


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
