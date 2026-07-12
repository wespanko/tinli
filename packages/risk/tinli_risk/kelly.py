"""Kelly sizing for binary contracts.

A contract bought at price c pays $1 on a win. With win probability p the
full-Kelly bankroll fraction is

    f* = (bp - q) / b,  b = (1-c)/c odds, q = 1-p
       = (p - c) / (1 - c)

SIZING GUIDANCE, NOT ADVICE: p is the USER'S estimate (Position.est_prob) —
Kelly against the market's own mid is zero edge by construction. The price
used is the mid; a real fill crosses the spread and pays taker fees, so true
edge is smaller than modeled. Full Kelly is famously aggressive; the report
also carries half-Kelly, the conventional practitioner default.
"""

from decimal import ROUND_FLOOR, Decimal

ZERO = Decimal("0")
ONE = Decimal("1")
HALF = Decimal("0.5")
# ROUND_FLOOR: a bet size is never rounded UP
FOUR_DP = Decimal("0.0001")


def kelly_fraction(price: Decimal, p_win: Decimal) -> Decimal | None:
    """Full-Kelly fraction of bankroll for one side at `price`, clipped to
    [0, 1]. Zero when there is no positive edge (p_win <= price). None when
    the price admits no bet (c = 0 or c = 1: nothing to win or free money —
    either way Kelly is undefined/degenerate)."""
    if price <= ZERO or price >= ONE:
        return None
    f = (p_win - price) / (ONE - price)
    return min(max(f, ZERO), ONE).quantize(FOUR_DP, rounding=ROUND_FLOOR)


def half_kelly(price: Decimal, p_win: Decimal) -> Decimal | None:
    f = kelly_fraction(price, p_win)
    return None if f is None else (f * HALF).quantize(FOUR_DP, rounding=ROUND_FLOOR)
