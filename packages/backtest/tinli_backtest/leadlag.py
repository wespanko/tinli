"""Cross-venue lead-lag: when one venue's mid moves, does the other follow?

Prediction-market mids move SPARSELY at snapshot cadence (most ticks are
flat), so instead of raw cross-correlation on near-all-zero returns, the
primary method is move-conditional: find venue-A mid moves of at least
`threshold`, then look ahead up to `horizon` ticks for venue B's first
move and classify it same-direction / opposite / none. If A truly leads B,
same-direction follows dominate; an exact binomial test against p=0.5
(follows vs opposes) quantifies it.

Sessions: recording gaps larger than `max_gap_s` split the series; moves
and follows never span a gap. Moves at the SAME tick land in a
`simultaneous` bucket — at 15-60s cadence, sub-cadence lead-lag is
unobservable and must not be attributed to either venue.

Money stays Decimal; only the test statistic uses floats.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from statistics import median


@dataclass(frozen=True)
class MidSeries:
    event_key: str
    ts: tuple[datetime, ...]
    k: tuple[Decimal, ...]  # kalshi mid
    p: tuple[Decimal, ...]  # polymarket mid


def build_series(rows: list[dict], event_key: str) -> MidSeries:
    """Co-observed mid series: rows where BOTH venues have a two-sided book."""
    ts, k, p = [], [], []
    for r in sorted((r for r in rows if r["event_key"] == event_key), key=lambda r: r["ts"]):
        if None in (r["k_bid"], r["k_ask"], r["p_bid"], r["p_ask"]):
            continue
        ts.append(r["ts"])
        k.append((r["k_bid"] + r["k_ask"]) / 2)
        p.append((r["p_bid"] + r["p_ask"]) / 2)
    return MidSeries(event_key=event_key, ts=tuple(ts), k=tuple(k), p=tuple(p))


def sessions(ts: tuple[datetime, ...], max_gap_s: float) -> list[range]:
    """Contiguous index ranges with no recording gap inside."""
    out, start = [], 0
    for i in range(1, len(ts)):
        if (ts[i] - ts[i - 1]).total_seconds() > max_gap_s:
            out.append(range(start, i))
            start = i
    if len(ts):
        out.append(range(start, len(ts)))
    return [r for r in out if len(r) >= 2]


def _moves(series: tuple[Decimal, ...], session: range, threshold: Decimal) -> dict[int, int]:
    """index -> direction (+1/-1) for |mid change| >= threshold inside one session."""
    out = {}
    for i in range(session.start + 1, session.stop):
        d = series[i] - series[i - 1]
        if abs(d) >= threshold:
            out[i] = 1 if d > 0 else -1
    return out


@dataclass
class LeadLag:
    """A-moves and what B did next (A leads B when follows >> opposes)."""

    n_moves: int = 0
    simultaneous: int = 0
    follows: int = 0
    opposes: int = 0
    unanswered: int = 0
    follow_lags_s: list[float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.follow_lags_s is None:
            self.follow_lags_s = []

    @property
    def median_lag_s(self) -> float | None:
        return median(self.follow_lags_s) if self.follow_lags_s else None

    @property
    def p_value(self) -> float | None:
        """Exact two-sided binomial: follows vs opposes against p=0.5.
        None when no directional responses at all."""
        n = self.follows + self.opposes
        if n == 0:
            return None
        k = max(self.follows, self.opposes)
        tail = sum(math.comb(n, j) for j in range(k, n + 1)) / 2**n
        return min(1.0, 2 * tail)

    def absorb(self, other: "LeadLag") -> None:
        self.n_moves += other.n_moves
        self.simultaneous += other.simultaneous
        self.follows += other.follows
        self.opposes += other.opposes
        self.unanswered += other.unanswered
        self.follow_lags_s.extend(other.follow_lags_s)


def lead_follow(
    series: MidSeries,
    leader: str,
    threshold: Decimal,
    horizon: int = 10,
    max_gap_s: float = 120.0,
) -> LeadLag:
    """How venue `leader`'s moves are answered by the other venue."""
    a_vals, b_vals = (series.k, series.p) if leader == "kalshi" else (series.p, series.k)
    result = LeadLag()
    for sess in sessions(series.ts, max_gap_s):
        a_moves = _moves(a_vals, sess, threshold)
        b_moves = _moves(b_vals, sess, threshold)
        for i, direction in a_moves.items():
            result.n_moves += 1
            if i in b_moves:
                result.simultaneous += 1
                continue
            answered = False
            for j in range(i + 1, min(i + 1 + horizon, sess.stop)):
                if j in b_moves:
                    if b_moves[j] == direction:
                        result.follows += 1
                        result.follow_lags_s.append(
                            (series.ts[j] - series.ts[i]).total_seconds()
                        )
                    else:
                        result.opposes += 1
                    answered = True
                    break
            if not answered:
                result.unanswered += 1
    return result
