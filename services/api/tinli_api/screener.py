"""Shared divergence computation — used by /v1/divergence and the snapshot job."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from tinli_divergence import DivergenceItem, compute_pair, sort_items
from tinli_schema import Orderbook, PairMapping

from tinli_api.datasource import DataSource, load_pairs

# Annual risk-free rate for the carry-adjusted edge. A silent guess would
# violate doctrine — the value travels in every DivergenceItem payload
# (rf_rate) and is overridable per instance.
RF_RATE_ENV = "TINLI_RF_RATE"
DEFAULT_RF_RATE = "0.04"

SECONDS_PER_DAY = Decimal("86400")


def rf_rate() -> Decimal:
    raw = os.environ.get(RF_RATE_ENV, DEFAULT_RF_RATE)
    try:
        rate = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{RF_RATE_ENV} is not a decimal rate: {raw!r}") from exc
    if rate < 0 or rate > 1:
        raise ValueError(f"{RF_RATE_ENV} must be an annual rate in [0, 1], got {raw!r}")
    return rate


def _close_by_key(source: DataSource) -> dict[str, datetime]:
    """event_key -> later venue close (the lock's conservative payout bound,
    same rule as /v1/lock). A venue feed failure degrades to no horizons —
    carry fields go None, the screener itself must never crash over it."""
    closes: dict[str, datetime] = {}
    try:
        markets = source.markets()
    except Exception:
        return closes
    for m in markets:
        if m.event_key is None or m.close_ts is None:
            continue
        held = closes.get(m.event_key)
        if held is None or m.close_ts > held:
            closes[m.event_key] = m.close_ts
    return closes


def compute_all(source: DataSource) -> list[DivergenceItem]:
    """One DivergenceItem per mapped pair, sorted; a failing leg yields an
    empty book (null edges), never a crash — a resolved/delisted market must
    not take down the screener or the recorder."""
    closes = _close_by_key(source)
    rate = rf_rate()

    def one(pair: PairMapping) -> DivergenceItem:
        try:
            k_book = source.orderbook(pair, "kalshi")
            pm_book = source.orderbook(pair, "polymarket")
        except Exception:
            empty = {"bids": [], "asks": [], "fetched_at": datetime.now(UTC)}
            k_book = Orderbook(market_id=f"kalshi:{pair.kalshi_ticker}", venue="kalshi", **empty)
            pm_book = Orderbook(
                market_id=f"polymarket:{pair.pm_condition_id}", venue="polymarket", **empty
            )
        fetched_at = max(k_book.fetched_at, pm_book.fetched_at)
        horizon: Decimal | None = None
        close = closes.get(pair.event_key)
        if close is not None:
            seconds = Decimal(int((close - fetched_at).total_seconds()))
            horizon = seconds / SECONDS_PER_DAY  # engine floors at 6h
        return compute_pair(
            pair, k_book, pm_book, fetched_at=fetched_at, horizon_days=horizon, rf_rate=rate
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        items = list(pool.map(one, load_pairs()))
    return sort_items(items)
