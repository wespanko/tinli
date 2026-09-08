"""Depth-walked lock sizing: the edge-vs-size curve.

The screener's edge_at_size uses TOP-of-book only. This module walks the
FULL books: leg by leg, segment by segment, it consumes YES-ask levels on
the cheap venue and NO-ask levels (1 - YES bid) on the other, accumulating
exact cost and exact fees at every level boundary.

Conservatism, as everywhere in Tinli:
- Every curve point is a WHOLE number of contracts — the executable unit
  both venues always accept; fractional book depth is floored away, which
  can only understate the lock.
- Fees are charged PER SEGMENT (each price level treated as its own fill).
  Sum-of-ceilings >= ceiling-of-sum, so this can only overstate fees and
  understate the edge.
- The optimal point is the profit maximum over the curve; the curve itself
  continues past it (capped) so the UI can show the decay honestly.
- Direction is fixed at top-of-book (same rule as the screener) — a
  direction that flips at depth is not modeled.

All Decimal. The curve is per-pair, computed on demand from live books.
"""

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from pydantic import BaseModel, Field

from tinli_schema import Orderbook

from tinli_divergence.fees import FeeModel

ZERO = Decimal("0")
ONE = Decimal("1")
SIX_DP = Decimal("0.000001")
CENT = Decimal("0.01")
MAX_POINTS = 20  # level boundaries reported; beyond this the tail is noise


class SizePoint(BaseModel):
    size: Decimal = Field(description="cumulative lock contracts at this level boundary")
    avg_yes: Decimal = Field(description="size-weighted average YES fill price")
    avg_no: Decimal
    per_contract_edge: Decimal = Field(
        description="net edge per contract at this size, exact fees, floored"
    )
    total_profit: Decimal = Field(description="guaranteed settlement profit at this size")
    capital: Decimal = Field(description="cost of both legs plus all fees at this size")


class LockCurve(BaseModel):
    direction: str | None
    points: list[SizePoint]
    optimal: SizePoint | None = Field(
        description="size maximizing total_profit, only if that profit is positive"
    )
    depth_exhausted: bool = Field(
        description="True when the curve ends because a book ran out, not the point cap"
    )


def walk_lock(
    kalshi_book: Orderbook,
    pm_book: Orderbook,
    kalshi_fees: FeeModel,
    pm_fees: FeeModel,
) -> LockCurve:
    k_ask = kalshi_book.asks[0].price if kalshi_book.asks else None
    p_ask = pm_book.asks[0].price if pm_book.asks else None
    k_bid = kalshi_book.bids[0].price if kalshi_book.bids else None
    p_bid = pm_book.bids[0].price if pm_book.bids else None
    if k_ask is None or p_ask is None or k_bid is None or p_bid is None:
        return LockCurve(direction=None, points=[], optimal=None, depth_exhausted=True)

    # Same direction rule as the screener (authoritative rationale in
    # engine.py): compare both directions' fee-adjusted top-of-book edge,
    # kalshi-YES wins ties. The two modules MUST agree — a curve whose
    # direction differs from the screener row it expands would be nonsense.
    def _edge(ask_yes: Decimal, yes_f: FeeModel, ask_no: Decimal, no_f: FeeModel) -> Decimal:
        return (
            ONE - ask_yes - ask_no
            - yes_f.taker_rate() * ask_yes * (ONE - ask_yes)
            - no_f.taker_rate() * ask_no * (ONE - ask_no)
        )

    k_yes_edge = _edge(k_ask, kalshi_fees, ONE - p_bid, pm_fees)
    p_yes_edge = _edge(p_ask, pm_fees, ONE - k_bid, kalshi_fees)
    if k_yes_edge >= p_yes_edge:
        direction = "buy_yes_kalshi_no_polymarket"
        yes_levels = [(lv.price, lv.size) for lv in kalshi_book.asks]
        no_levels = [(ONE - lv.price, lv.size) for lv in pm_book.bids]  # best-first ✓
        yes_fees, no_fees = kalshi_fees, pm_fees
    else:
        direction = "buy_yes_polymarket_no_kalshi"
        yes_levels = [(lv.price, lv.size) for lv in pm_book.asks]
        no_levels = [(ONE - lv.price, lv.size) for lv in kalshi_book.bids]
        yes_fees, no_fees = pm_fees, kalshi_fees

    # merge the two ladders into fill segments: each segment is a run at one
    # (yes_price, no_price) pair, sized by whichever level exhausts first
    segments: list[tuple[Decimal, Decimal, Decimal]] = []
    yi = ni = 0
    yes_rem = yes_levels[0][1]
    no_rem = no_levels[0][1]
    while yi < len(yes_levels) and ni < len(no_levels):
        seg = min(yes_rem, no_rem)
        if seg <= 0:
            break
        segments.append((yes_levels[yi][0], no_levels[ni][0], seg))
        yes_rem -= seg
        no_rem -= seg
        if yes_rem == 0:
            yi += 1
            yes_rem = yes_levels[yi][1] if yi < len(yes_levels) else ZERO
        if no_rem == 0:
            ni += 1
            no_rem = no_levels[ni][1] if ni < len(no_levels) else ZERO

    # breakpoints are segment boundaries floored to WHOLE contracts — the
    # executable unit both venues always accept (same rationale as the
    # screener's max_lock_size; a sub-1-contract book yields an empty curve).
    # Each point is priced as its own standalone execution by _fill, so a
    # level split by the flooring is never double-charged fees.
    seen: set[Decimal] = set()
    breakpoints: list[Decimal] = []
    cum = ZERO
    for _, _, seg in segments:
        cum += seg
        n = cum.to_integral_value(rounding=ROUND_FLOOR)
        if n > 0 and n not in seen:
            seen.add(n)
            breakpoints.append(n)
        if len(breakpoints) >= MAX_POINTS:
            break

    def _fill(n: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """cost, fees, yes-notional, no-notional for a lock of exactly n
        contracts; fees charged per (possibly partial) segment — sum of
        ceilings only ever overstates."""
        remaining, cost, fees, acc_yes, acc_no = n, ZERO, ZERO, ZERO, ZERO
        for py, pn, seg in segments:
            take = min(seg, remaining)
            cost += (py + pn) * take
            fees += yes_fees.taker_fee(py, take) + no_fees.taker_fee(pn, take)
            acc_yes += py * take
            acc_no += pn * take
            remaining -= take
            if remaining == 0:
                break
        return cost, fees, acc_yes, acc_no

    points: list[SizePoint] = []
    for n in breakpoints:
        cost, fees, acc_yes, acc_no = _fill(n)
        capital = cost + fees
        profit = n - capital  # lock pays $1 x n at settlement
        points.append(
            SizePoint(
                size=n,
                avg_yes=(acc_yes / n).quantize(SIX_DP),
                avg_no=(acc_no / n).quantize(SIX_DP),
                per_contract_edge=(profit / n).quantize(SIX_DP, rounding=ROUND_FLOOR),
                total_profit=profit.quantize(CENT, rounding=ROUND_FLOOR),
                # capital REQUIRED rounds up, like every risk number
                capital=capital.quantize(CENT, rounding=ROUND_CEILING),
            )
        )

    best = max(points, key=lambda p: p.total_profit, default=None)
    optimal = best if best is not None and best.total_profit > 0 else None
    exhausted = len(breakpoints) < MAX_POINTS
    return LockCurve(direction=direction, points=points, optimal=optimal, depth_exhausted=exhausted)
