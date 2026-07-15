"""95% Value-at-Risk for a book of binary-outcome positions.

ASSUMPTIONS — the single authoritative statement; RiskReport.assumptions
echoes these so the UI can show them next to the numbers:

1. PRICE ≈ PROBABILITY. Each event's YES probability is taken from current
   venue mids, not an independent forecast. If the market is mispriced, so
   is this VaR.
2. INDEPENDENCE ACROSS EVENTS, perfect correlation within one. Positions
   sharing an event_key settle on the same outcome (that is the premise of
   the curated pair map); distinct events are treated as independent
   Bernoullis. Correlated events (e.g. two matches whose outcomes interact
   via group standings) will understate tail risk.
3. HORIZON = RESOLUTION. Binary contracts have no natural 1-day P&L
   distribution; this VaR answers "what can I lose by the time these events
   settle", not "by tomorrow".
4. PARAMETRIC = NORMAL APPROXIMATION of a sum of Bernoulli P&Ls. It is only
   trustworthy with many similar-sized independent events; with few events
   it can exceed the maximum possible loss, so it is CAPPED at max_loss.
   Monte Carlo samples the actual Bernoullis, but is capped too: it crosses
   the float boundary, and dust in the summed P&L plus ROUND_CEILING could
   otherwise report a VaR one cent above the maximum possible loss.

Everything is Decimal except inside the Monte Carlo simulation, which
converts to float64 at the numpy boundary. Results are rounded UP to the
cent (ROUND_CEILING) — risk is never rounded down.
"""

from decimal import ROUND_CEILING, Decimal

import numpy as np
from pydantic import BaseModel, Field

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")
# One-sided 95% standard normal quantile, Phi^-1(0.95).
Z_95 = Decimal("1.6449")


class EventPnl(BaseModel):
    """Portfolio P&L swing hanging on one Bernoulli outcome, in dollars
    relative to CURRENT MARKS (not entry prices)."""

    event_id: str = Field(description="event_key, or market_id for unmapped markets")
    prob_yes: Decimal = Field(ge=0, le=1)
    delta_if_yes: Decimal = Field(description="portfolio P&L vs. mark if the event resolves YES")
    delta_if_no: Decimal


def max_loss(events: list[EventPnl]) -> Decimal:
    """Worst case over ALL outcome combinations — every event resolves
    against us simultaneously. The hard floor no VaR may exceed."""
    worst = sum((min(e.delta_if_yes, e.delta_if_no) for e in events), ZERO)
    return max(ZERO, -worst).quantize(CENT, rounding=ROUND_CEILING)


def parametric_var(events: list[EventPnl]) -> Decimal:
    """Normal-approximation VaR (assumption 4). mu and sigma^2 are exact
    Bernoulli moments; only the 95th-percentile read-off assumes normality."""
    if not events:
        return ZERO
    mu = ZERO
    variance = ZERO
    for e in events:
        p = e.prob_yes
        mu += p * e.delta_if_yes + (ONE - p) * e.delta_if_no
        variance += p * (ONE - p) * (e.delta_if_yes - e.delta_if_no) ** 2
    var95 = -(mu - Z_95 * variance.sqrt())
    var95 = max(ZERO, var95).quantize(CENT, rounding=ROUND_CEILING)
    return min(var95, max_loss(events))


def monte_carlo_var(events: list[EventPnl], draws: int = 20_000, seed: int = 7) -> Decimal:
    """Sample the actual joint Bernoulli distribution. Seeded and therefore
    reproducible: same book + same seed = same number, so 3s UI polling
    doesn't flicker."""
    if not events:
        return ZERO
    rng = np.random.default_rng(seed)
    p = np.array([float(e.prob_yes) for e in events])
    if_yes = np.array([float(e.delta_if_yes) for e in events])
    if_no = np.array([float(e.delta_if_no) for e in events])
    yes = rng.random((draws, len(events))) < p
    pnl = yes @ if_yes + (~yes) @ if_no
    q05 = float(np.quantile(pnl, 0.05))
    var = Decimal(str(max(0.0, -q05))).quantize(CENT, rounding=ROUND_CEILING)
    return min(var, max_loss(events))
