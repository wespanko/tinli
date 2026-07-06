"""Unified cross-venue market data models.

Every price in Tinli is a Decimal in dollars on the 0–1 probability scale.
Adapters normalize venue quirks at the boundary (see docs/VENUES.md); nothing
downstream of these models may know which venue a number came from.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Venue = Literal["kalshi", "polymarket"]


class Market(BaseModel):
    """One binary market on one venue, normalized to the YES outcome."""

    id: str = Field(description="venue-qualified id: 'kalshi:<ticker>' or 'polymarket:<conditionId>'")
    venue: Venue
    event_key: str | None = Field(
        default=None, description="Tinli pair slug from event_map.yaml; None if unmapped"
    )
    question: str
    status: Literal["open", "closed", "settled", "unknown"] = Field(
        default="unknown", description="normalized from venue-specific vocabularies"
    )
    yes_price: Decimal = Field(description="venue's last/reported YES price, dollars 0-1")
    no_price: Decimal
    best_bid: Decimal | None = Field(description="best executable YES bid; None if book empty")
    best_ask: Decimal | None = Field(description="best executable YES ask; None if book empty")
    volume_24h: Decimal = Field(
        description="venue-native units: Kalshi = contracts, Polymarket = USD. "
        "Comparable within a venue, NOT across venues."
    )
    liquidity: Decimal | None = Field(
        default=None,
        description="venue-reported liquidity (USD). None for Kalshi — its field is "
        "deprecated/always 0; use orderbook depth instead.",
    )
    close_ts: datetime
    resolution_url: str
    fetched_at: datetime


class OrderbookLevel(BaseModel):
    price: Decimal
    size: Decimal = Field(description="contracts/shares at this price")


class Orderbook(BaseModel):
    """YES-side book, both venues normalized to the same shape.

    bids/asks are BEST-FIRST: bids[0] is the highest bid, asks[0] the lowest
    ask. Kalshi asks are derived (YES ask at 1-p for each NO bid at p);
    Polymarket levels arrive worst-first and are re-sorted by the adapter.
    """

    market_id: str
    venue: Venue
    bids: list[OrderbookLevel]
    asks: list[OrderbookLevel]
    fetched_at: datetime


class PairMapping(BaseModel):
    """One curated Kalshi<->Polymarket pair from data/event_map.yaml."""

    event_key: str
    question: str
    kalshi_ticker: str
    pm_condition_id: str
    pm_yes_token: int = Field(ge=0, le=1, description="index into clobTokenIds that is YES")
    criteria_verified: bool = Field(
        default=False,
        description="True only after a human compared both venues' resolution rules. "
        "Divergence on unverified pairs is flagged and sorted last.",
    )
    notes: str = ""
