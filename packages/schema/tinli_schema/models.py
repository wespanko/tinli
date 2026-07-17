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
    icon_url: str | None = Field(
        default=None, description="venue-hosted event image; Polymarket only in v0"
    )
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


class Position(BaseModel):
    """One user-entered holding, marked to market by venue-qualified id.

    v0 has no venue auth (BYOK comes later): positions are self-reported in
    data/positions.yaml. `entry_price` is what the user paid per contract for
    `side`, on the same 0-1 dollar scale as every other price in Tinli.
    """

    market_id: str = Field(description="venue-qualified id matching Market.id")
    side: Literal["yes", "no"]
    contracts: Decimal = Field(gt=0)
    entry_price: Decimal = Field(ge=0, le=1, description="price paid per contract for `side`")
    est_prob: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
        description="user's OWN estimate of the YES probability. Enables Kelly "
        "sizing; never inferred from market prices — Kelly on the market's own "
        "mid is zero edge by construction.",
    )
    notes: str = ""


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
    pm_fee_category: (
        Literal[
            "crypto",
            "sports",
            "finance",
            "politics",
            "mentions",
            "tech",
            "economics",
            "culture",
            "weather",
            "geopolitical",
            "other",
        ]
        | None
    ) = Field(
        default=None,
        description="Polymarket taker-fee category, curated per pair like the "
        "mapping itself. None -> fee model assumes the worst-case rate and "
        "flags the result.",
    )
    notes: str = ""
