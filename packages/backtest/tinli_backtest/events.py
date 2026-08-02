"""Scheduled-announcement event study: what each venue's book did around a
known release time (first use: the 2026-07-29 FOMC decision).

The honest unit of observation is the snapshot bracket. A reprice is
reported as the pair of consecutive same-venue ticks it happened between,
never as a point in time — the cadence, plus the recorder's clock (NTP)
and fetch latency, bound what one machine can claim. Anything sharper than
the bracket is not attributed.

Money stays Decimal; floats appear only in interval arithmetic.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_FLOOR, Decimal

CENT = Decimal("0.01")


def _venue_mids(rows: list[dict], event_key: str, venue: str) -> list[tuple[datetime, Decimal]]:
    """(ts, mid) for this venue's TWO-SIDED quotes only, ts-ascending.
    Unlike leadlag.build_series, co-observation with the other venue is not
    required — a halt on one venue must not blind us to the other."""
    b, a = ("k_bid", "k_ask") if venue == "kalshi" else ("p_bid", "p_ask")
    out = [
        (r["ts"], (r[b] + r[a]) / 2)
        for r in rows
        if r["event_key"] == event_key and r[b] is not None and r[a] is not None
    ]
    out.sort(key=lambda t: t[0])
    return out


@dataclass(frozen=True)
class VenueEventWindow:
    """A venue's last two-sided quote at/before the event and first after.
    first_after_ts=None means the venue never quoted two-sided again —
    e.g. Kalshi closes its Fed markets at the scheduled announcement."""

    venue: str
    last_ts: datetime | None
    last_mid: Decimal | None
    first_after_ts: datetime | None
    first_after_mid: Decimal | None


def venue_event_window(
    rows: list[dict], event_key: str, venue: str, event_ts: datetime
) -> VenueEventWindow:
    mids = _venue_mids(rows, event_key, venue)
    before = [(t, m) for t, m in mids if t <= event_ts]
    after = [(t, m) for t, m in mids if t > event_ts]
    return VenueEventWindow(
        venue=venue,
        last_ts=before[-1][0] if before else None,
        last_mid=before[-1][1] if before else None,
        first_after_ts=after[0][0] if after else None,
        first_after_mid=after[0][1] if after else None,
    )


@dataclass(frozen=True)
class Reprice:
    """One venue's repricing bracket: consecutive two-sided ticks between
    which the mid jumped. The move happened somewhere inside (prior_ts, ts];
    nothing sharper is claimed."""

    prior_ts: datetime
    prior_mid: Decimal
    ts: datetime
    mid: Decimal

    @property
    def jump(self) -> Decimal:
        return self.mid - self.prior_mid

    @property
    def interval_s(self) -> float:
        return (self.ts - self.prior_ts).total_seconds()


def find_reprice(
    rows: list[dict],
    event_key: str,
    venue: str,
    window: tuple[datetime, datetime],
    jump: Decimal = Decimal("0.10"),
) -> Reprice | None:
    """First consecutive-tick |mid change| >= `jump` whose LANDING tick falls
    inside `window` (start exclusive is not needed: the bracket may open
    before the window as long as it lands inside it)."""
    mids = _venue_mids(rows, event_key, venue)
    lo, hi = window
    for (t0, m0), (t1, m1) in zip(mids, mids[1:]):
        if lo <= t1 <= hi and abs(m1 - m0) >= jump:
            return Reprice(prior_ts=t0, prior_mid=m0, ts=t1, mid=m1)
    return None


@dataclass(frozen=True)
class DayEdges:
    """One UTC day's after-fee-at-size edge environment for one pair.
    best_profit = max over ticks of edge_at_size x max_lock_size, floored to
    the cent — a per-tick snapshot of the largest single lock on display,
    NOT a tradable daily total (episode logic lives in locks.backtest)."""

    day: date
    ticks: int
    pos_ticks: int
    max_edge: Decimal | None
    best_profit: Decimal | None
    best_ts: datetime | None  # timestamp of the best_profit tick


def daily_edge_summary(rows: list[dict], event_key: str) -> list[DayEdges]:
    by_day: dict[date, list[dict]] = {}
    for r in rows:
        if r["event_key"] == event_key:
            by_day.setdefault(r["ts"].date(), []).append(r)
    out = []
    for day in sorted(by_day):
        day_rows = by_day[day]
        pos = [
            r for r in day_rows
            if r["edge_at_size"] is not None and r["edge_at_size"] > 0
        ]
        profits = [
            (r["edge_at_size"] * r["max_lock_size"], r["ts"])
            for r in pos
            if r["max_lock_size"] is not None
        ]
        best = max(profits, key=lambda t: t[0], default=None)
        out.append(
            DayEdges(
                day=day,
                ticks=len(day_rows),
                pos_ticks=len(pos),
                max_edge=max((r["edge_at_size"] for r in pos), default=None),
                best_profit=(
                    best[0].quantize(CENT, rounding=ROUND_FLOOR)
                    if best else None
                ),
                best_ts=best[1] if best else None,
            )
        )
    return out
