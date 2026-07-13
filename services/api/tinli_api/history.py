"""Parquet history: append-only snapshot files, Decimal-preserving at rest.

Parquet cannot append, so each flush writes a NEW file under the recording
day's directory — data/history/YYYY-MM-DD/HHMMSS_ffffff.parquet — and readers
concatenate the day range. The snapshot job buffers ticks and flushes in
batches so a day stays at hundreds of small files, not thousands.

Prices, sizes and edges are decimal128 columns (never float64): what the
engine computed is exactly what a later backtest reads back. Edges are
quantized to 1e-6 with ROUND_FLOOR before storage — same philosophy as the
divergence engine, storage may understate an edge but never invent one.
"""

import os
from datetime import UTC, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from tinli_divergence import DivergenceItem

from tinli_api.datasource import REPO_ROOT

PRICE = pa.decimal128(9, 6)  # 0-1 dollar prices
CENTS = pa.decimal128(18, 6)  # basis/edges (cents or dollars)
SIZE = pa.decimal128(20, 6)  # contracts/shares

SCHEMA = pa.schema(
    [
        ("ts", pa.timestamp("us", tz="UTC")),
        ("event_key", pa.string()),
        ("k_bid", PRICE),
        ("k_ask", PRICE),
        ("k_bid_size", SIZE),
        ("k_ask_size", SIZE),
        ("p_bid", PRICE),
        ("p_ask", PRICE),
        ("p_bid_size", SIZE),
        ("p_ask_size", SIZE),
        ("raw_basis_cents", CENTS),
        ("fee_adjusted_edge", CENTS),
        ("edge_at_size", CENTS),
        ("max_lock_size", SIZE),
    ]
)

SIX_DP = Decimal("0.000001")
MAX_POINTS = 500  # reader downsamples past this — UI charts need no more


def history_dir() -> Path:
    return Path(os.environ.get("TINLI_HISTORY_DIR", str(REPO_ROOT / "data" / "history")))


def _q(v: Decimal | None) -> Decimal | None:
    """Quantize toward -inf: storage never rounds an edge into existence."""
    return None if v is None else v.quantize(SIX_DP, rounding=ROUND_FLOOR)


def rows_from_items(items: list[DivergenceItem], ts: datetime) -> list[dict]:
    return [
        {
            "ts": ts,
            "event_key": it.event_key,
            "k_bid": it.kalshi.bid,
            "k_ask": it.kalshi.ask,
            "k_bid_size": it.kalshi.bid_size,
            "k_ask_size": it.kalshi.ask_size,
            "p_bid": it.polymarket.bid,
            "p_ask": it.polymarket.ask,
            "p_bid_size": it.polymarket.bid_size,
            "p_ask_size": it.polymarket.ask_size,
            "raw_basis_cents": _q(it.raw_basis_cents),
            "fee_adjusted_edge": _q(it.fee_adjusted_edge),
            "edge_at_size": _q(it.edge_at_size),
            "max_lock_size": it.max_lock_size,
        }
        for it in items
    ]


def write_rows(rows: list[dict]) -> Path | None:
    """Flush a batch to one new parquet file, named for its LAST timestamp."""
    if not rows:
        return None
    last_ts: datetime = rows[-1]["ts"]
    day_dir = history_dir() / f"{last_ts:%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{last_ts:%H%M%S_%f}.parquet"
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    pq.write_table(table, path)
    return path


def read_history(event_key: str, hours: int, now: datetime | None = None) -> list[dict]:
    """All rows for one pair within the window, ts-ascending, downsampled to
    MAX_POINTS by even stride (always keeping the newest row)."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=hours)
    rows: list[dict] = []
    day = cutoff.date()
    while day <= now.date():
        day_dir = history_dir() / day.isoformat()
        if day_dir.is_dir():
            for f in sorted(day_dir.glob("*.parquet")):
                for row in pq.read_table(f).to_pylist():
                    if row["event_key"] == event_key and cutoff <= row["ts"] <= now:
                        rows.append(row)
        day += timedelta(days=1)
    rows.sort(key=lambda r: r["ts"])
    return _downsample(rows, MAX_POINTS)


def _downsample(rows: list[dict], cap: int) -> list[dict]:
    if len(rows) <= cap:
        return rows
    stride = -(-len(rows) // cap)  # ceil
    kept = rows[::stride]
    if kept[-1] is not rows[-1]:
        kept.append(rows[-1])  # the newest point must survive
    return kept
