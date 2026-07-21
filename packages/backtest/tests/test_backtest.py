"""Backtest math — hand-computed expectations plus property tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from tinli_backtest import backtest, extract_episodes

T0 = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def row(minute_offset_s: float, edge, size, key="pair-a"):
    return {
        "event_key": key,
        "ts": T0 + timedelta(seconds=minute_offset_s),
        "edge_at_size": None if edge is None else Decimal(edge),
        "max_lock_size": None if size is None else Decimal(size),
    }


def test_episode_extraction_runs_gaps_and_death():
    rows = [
        row(0, "0.010", "100"),      # episode 1: ticks at 0s, 30s
        row(30, "0.008", "80"),
        row(60, None, None),         # edge dies -> episode 1 ends
        row(90, "0.005", "50"),      # episode 2: single tick
        row(120, "-0.002", "40"),    # negative edge is not an episode
        row(150, "0.004", "30"),     # episode 3 tick 1...
        row(400, "0.004", "30"),     # ...250s gap > 120s: episode 4, not 3
    ]
    eps = extract_episodes(rows, "pair-a", max_gap_s=120)
    assert [len(e.ticks) for e in eps] == [2, 1, 1, 1]
    assert eps[0].duration_s == 30.0
    assert eps[1].duration_s == 0.0  # single observation: lifetime < cadence
    # latency entry: 1 tick late into episode 1 gets the 30s tick; episode 2
    # is already gone
    assert eps[0].entry(1).edge == Decimal("0.008")
    assert eps[1].entry(1) is None


def test_lock_trade_hand_computed():
    """Entry edge 0.010 $/contract at size 100:
    profit  = 0.010 x 100                 = $1.00
    capital = (1 - 0.010) x 100           = $99.00
    5 days to resolution ->
    annualized = 1.00/99.00 x 365/5       = 0.7373... -> floor 4dp 0.7373"""
    rows = [row(0, "0.010", "100")]
    eps = extract_episodes(rows, "pair-a")
    resolution = {"pair-a": T0 + timedelta(days=5)}
    (trade,) = backtest(eps, resolution)
    assert trade.profit == Decimal("1.00")
    assert trade.capital == Decimal("99.00")
    assert trade.days_held == Decimal("5.0000")
    assert trade.annualized_return == Decimal("0.7373")


def test_latency_kills_short_episodes():
    rows = [row(0, "0.010", "100"), row(30, "0.006", "40")]
    eps = extract_episodes(rows, "pair-a")
    assert len(backtest(eps, {}, latency_ticks=0)) == 1
    assert backtest(eps, {}, latency_ticks=1)[0].profit == Decimal("0.24")  # 0.006 x 40
    assert backtest(eps, {}, latency_ticks=2) == []


@given(
    edge=st.decimals(min_value="0.000001", max_value="0.5", places=6),
    size=st.decimals(min_value="0.01", max_value="1000000", places=2),
)
def test_profit_capital_invariants(edge, size):
    """profit + capital <= size x 1 (the lock's payout) — the floor
    quantization may only ever lose money, never create it."""
    rows = [{"event_key": "p", "ts": T0, "edge_at_size": edge, "max_lock_size": size}]
    (trade,) = backtest(extract_episodes(rows, "p"), {})
    assert trade.profit >= 0
    assert trade.profit + trade.capital <= size * Decimal(1) + Decimal("0.005")
    assert trade.profit <= edge * size
