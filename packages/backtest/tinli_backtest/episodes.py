"""Edge episodes: maximal runs of consecutive ticks where a pair's
fee-adjusted at-size lock edge is strictly positive.

An episode is the tradeable unit of this research: the screener said "a
taker could lock a positive edge at this size, right now" for every tick
inside it. Episodes end when the edge dies OR when the recording has a gap
larger than `max_gap_s` — a recorder outage must never be mistaken for
edge persistence.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Tick:
    ts: datetime
    edge: Decimal  # edge_at_size, dollars/contract, > 0 inside an episode
    size: Decimal  # max_lock_size, contracts


@dataclass(frozen=True)
class Episode:
    event_key: str
    ticks: tuple[Tick, ...]

    @property
    def start(self) -> datetime:
        return self.ticks[0].ts

    @property
    def duration_s(self) -> float:
        """0 for a single-tick episode: the edge was observed once and gone
        by the next observation — its true lifetime is BELOW the recording
        cadence, not zero; report alongside the cadence."""
        return (self.ticks[-1].ts - self.ticks[0].ts).total_seconds()

    def entry(self, latency_ticks: int) -> Tick | None:
        """The tick a taker entering `latency_ticks` observations after
        episode start would actually get; None if the edge is already gone."""
        if latency_ticks >= len(self.ticks):
            return None
        return self.ticks[latency_ticks]


def extract_episodes(
    rows: list[dict], event_key: str, max_gap_s: float = 120.0
) -> list[Episode]:
    """rows: one pair's history rows (dicts with ts / edge_at_size /
    max_lock_size), any order. Ticks with edge None or <= 0 break runs."""
    mine = sorted((r for r in rows if r["event_key"] == event_key), key=lambda r: r["ts"])
    episodes: list[Episode] = []
    run: list[Tick] = []

    def flush() -> None:
        if run:
            episodes.append(Episode(event_key=event_key, ticks=tuple(run)))
            run.clear()

    for r in mine:
        edge, size = r["edge_at_size"], r["max_lock_size"]
        alive = edge is not None and edge > 0 and size is not None and size > 0
        if not alive:
            flush()
            continue
        if run and (r["ts"] - run[-1].ts).total_seconds() > max_gap_s:
            flush()  # recording gap: do not bridge it
        run.append(Tick(ts=r["ts"], edge=edge, size=size))
    flush()
    return episodes
