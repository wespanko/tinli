"""Conservative lock backtest over edge episodes.

The strategy is the product's own signal, taken literally: when a verified
pair shows a positive fee-adjusted edge at executable size, buy the lock
ONCE per episode at the recorded size, hold to resolution, collect $1 per
contract-pair whichever way the event settles.

Locked profit is known AT ENTRY (that is what a lock is): the recorded
edge_at_size already nets out both venues' exact fees and is quantized
toward -inf at every stage, so nothing here can overstate P&L.

Capital identity (derivation): a lock's payout is $1/contract at
resolution. Its all-in entry cost per contract is therefore
1 - edge_per_contract, so capital = size x (1 - edge). Annualized return
is simple: profit / capital x 365 / days_to_resolution.

Deliberate conservatisms and their limits (shipped in ASSUMPTIONS):
- one entry per episode, at the size displayed at the entry tick; the
  strategy never re-takes a persisting edge (understates capacity),
- but fills assume the full displayed depth with no queue or slippage
  (overstates fill quality) and no leg risk between the two venues,
- entries only on pairs whose resolution criteria were HUMAN-VERIFIED in
  the event map as of the recording date; flagged pairs' apparent edges
  are reported separately as trap evidence, never traded.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal

from tinli_backtest.episodes import Episode

CENT2 = Decimal("0.01")
FOUR_DP = Decimal("0.0001")
DAYS_PER_YEAR = Decimal("365")
MIN_HORIZON_DAYS = Decimal("0.25")  # same 6h floor as /v1/lock

ASSUMPTIONS = [
    "One lock per episode at the entry tick's displayed size; a persisting "
    "edge is never re-taken (conservative on capacity).",
    "Fills assume the full displayed depth at both venues with no queue, "
    "slippage, or leg risk (optimistic on execution).",
    "Locked profit = recorded edge_at_size x size; the edge already nets "
    "both venues' exact taker fees and is floor-quantized at every stage.",
    "Capital = size x (1 - edge): all-in cost of a $1-payout lock.",
    "Only pairs human-verified at recording time are traded; flagged pairs "
    "are excluded and their apparent edges reported as traps.",
    "Annualized return is simple, horizon = entry -> resolution date, "
    "floored at 6 hours.",
]


@dataclass(frozen=True)
class LockTrade:
    event_key: str
    entry_ts: datetime
    edge: Decimal  # dollars/contract at entry
    size: Decimal  # contracts
    profit: Decimal  # locked at entry
    capital: Decimal
    days_held: Decimal | None
    annualized_return: Decimal | None


def backtest(
    episodes: list[Episode],
    resolutions: dict[str, datetime],
    latency_ticks: int = 0,
) -> list[LockTrade]:
    trades: list[LockTrade] = []
    for ep in episodes:
        tick = ep.entry(latency_ticks)
        if tick is None:
            continue
        profit = (tick.edge * tick.size).quantize(CENT2, rounding=ROUND_FLOOR)
        capital = ((Decimal(1) - tick.edge) * tick.size).quantize(CENT2)
        resolution = resolutions.get(ep.event_key)
        days = annualized = None
        if resolution is not None and capital > 0:
            seconds = Decimal(int((resolution - tick.ts).total_seconds()))
            days = max(seconds / Decimal(86400), MIN_HORIZON_DAYS).quantize(FOUR_DP)
            annualized = (profit / capital * DAYS_PER_YEAR / days).quantize(
                FOUR_DP, rounding=ROUND_FLOOR
            )
        trades.append(LockTrade(
            event_key=ep.event_key, entry_ts=tick.ts, edge=tick.edge, size=tick.size,
            profit=profit, capital=capital, days_held=days, annualized_return=annualized,
        ))
    return trades
