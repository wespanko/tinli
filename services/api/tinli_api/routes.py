import asyncio
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Literal

import yaml
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from tinli_divergence import (
    DivergenceItem,
    KalshiFees,
    PolymarketFees,
    SizePoint,
    walk_lock,
)
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
from tinli_api.stats import BasisStats, basis_stats
from tinli_api.stream import StreamSource, get_hub
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
    stats: BasisStats


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
    stats = basis_stats([(p.ts, p.raw_basis_cents) for p in points])
    return HistoryResponse(event_key=event_key, hours=hours, points=points, stats=stats)


FOUR_DP = Decimal("0.0001")
DAYS_PER_YEAR = Decimal("365")
MIN_HORIZON_DAYS = Decimal("0.25")  # 6h floor: don't annualize into absurdity
SECONDS_PER_DAY = Decimal("86400")

LOCK_ASSUMPTIONS = [
    "Taker-only: both legs cross the spread; fees charged per price level with "
    "each venue's exact rounding (can only overstate fees, never understate).",
    "Direction is fixed at top-of-book; a direction flip at depth is not modeled.",
    "Both legs are priced from the same book snapshot; leg risk (one side "
    "moving while the other fills) is not modeled.",
    "Annualized return is simple (profit/capital x 365/horizon), horizon = later "
    "venue close time, floored at 6 hours; venues may resolve before close.",
]


class LockReport(BaseModel):
    event_key: str
    question: str
    criteria_verified: bool
    fee_assumed_worst_case: bool
    direction: str | None
    points: list[SizePoint]
    optimal: SizePoint | None
    depth_exhausted: bool
    days_to_resolution: Decimal | None
    annualized_return: Decimal | None = Field(
        default=None,
        description="simple annualized return on capital at the optimal size; "
        "None when there is no profitable size or no close time",
    )
    assumptions: list[str]
    fetched_at: datetime


@router.get("/lock/{event_key}")
def lock(event_key: str) -> LockReport:
    """Depth-walked lock curve for one pair: edge vs size off the FULL books,
    with exact per-level fees, plus capital, horizon and annualized return at
    the profit-maximizing size. Math in tinli_divergence.sizing."""
    pair = next((p for p in load_pairs() if p.event_key == event_key), None)
    if pair is None:
        raise HTTPException(status_code=404, detail=f"unknown event_key: {event_key}")
    source = get_source()
    try:
        k_book = source.orderbook(pair, "kalshi")
        pm_book = source.orderbook(pair, "polymarket")
        markets = source.markets()
    except VenueHTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    pm_fees = PolymarketFees(pair.pm_fee_category)
    curve = walk_lock(k_book, pm_book, KalshiFees(), pm_fees)
    fetched_at = max(k_book.fetched_at, pm_book.fetched_at)

    assumptions = list(LOCK_ASSUMPTIONS)
    if pm_fees.assumed_worst_case:
        assumptions.append(
            "No curated Polymarket fee category for this pair: the WORST-CASE "
            "rate on the published schedule is assumed."
        )
    if not pair.criteria_verified:
        assumptions.append(
            "UNVERIFIED PAIR: resolution criteria have not been human-compared. "
            "The $1 settlement identity may not hold — this curve is a trap "
            "until verified."
        )

    # horizon: the lock pays out when the event resolves; the later venue
    # close is the conservative (longer) bound we can actually observe
    closes = [m.close_ts for m in markets if m.event_key == event_key]
    days: Decimal | None = None
    annualized: Decimal | None = None
    if closes:
        seconds = Decimal(int((max(closes) - fetched_at).total_seconds()))
        days = max(seconds / SECONDS_PER_DAY, MIN_HORIZON_DAYS).quantize(FOUR_DP)
        if curve.optimal is not None and curve.optimal.capital > 0:
            annualized = (
                curve.optimal.total_profit / curve.optimal.capital * DAYS_PER_YEAR / days
            ).quantize(FOUR_DP, rounding=ROUND_FLOOR)  # a return is an edge: floor

    return LockReport(
        event_key=pair.event_key,
        question=pair.question,
        criteria_verified=pair.criteria_verified,
        fee_assumed_worst_case=pm_fees.assumed_worst_case,
        direction=curve.direction,
        points=curve.points,
        optimal=curve.optimal,
        depth_exhausted=curve.depth_exhausted,
        days_to_resolution=days,
        annualized_return=annualized,
        assumptions=assumptions,
        fetched_at=fetched_at,
    )


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


def build_pairs(markets: list[Market]) -> list[PairQuote]:
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


@router.get("/pairs")
def list_pairs() -> list[PairQuote]:
    try:
        markets = get_source().markets()
    except VenueHTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return build_pairs(markets)


class VenueStreamStatus(BaseModel):
    transport: Literal["websocket", "poll"]
    state: Literal["connecting", "live", "degraded"]
    age_s: float | None = Field(description="seconds since this venue's last update; None before the first")


class StreamUpdate(BaseModel):
    """One /v1/stream SSE payload: the same shapes the REST endpoints serve,
    pushed on change instead of polled."""

    ts: datetime
    venues: dict[str, VenueStreamStatus]
    pairs: list[PairQuote]
    divergence: list[DivergenceItem]


def sse_event(update: StreamUpdate) -> str:
    return f"data: {update.model_dump_json()}\n\n"


STREAM_THROTTLE_S = 0.4  # min gap between pushes; PM can tick many times/s
STREAM_HEARTBEAT_S = 15.0


@router.get("/stream")
async def stream() -> StreamingResponse:
    """Server-sent events: push pairs + divergence when venue data changes.

    Live mode only — demo stays socket-free (fixtures do not tick), and the
    UI falls back to 3s REST polling whenever this endpoint is unavailable,
    so nothing breaks when the hub is down."""
    hub = get_hub()
    if hub is None:
        raise HTTPException(
            status_code=503, detail="stream not running (demo mode or TINLI_STREAM=0)"
        )
    source = StreamSource(hub)

    async def gen():
        seen = -1
        while True:
            if hub.version != seen:
                seen = hub.version
                pairs = build_pairs(await asyncio.to_thread(source.markets))
                items = await asyncio.to_thread(compute_all, source)
                update = StreamUpdate(
                    ts=datetime.now(UTC),
                    venues=hub.venue_status(),
                    pairs=pairs,
                    divergence=items,
                )
                yield sse_event(update)
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(STREAM_THROTTLE_S)
            await hub.wait_for_change(STREAM_HEARTBEAT_S)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
