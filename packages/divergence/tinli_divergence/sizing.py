"""Depth-walked lock sizing: the edge-vs-size curve.

The screener's edge_at_size uses TOP-of-book only. This module walks the
FULL books: leg by leg, segment by segment, it consumes YES-ask levels on
the cheap venue and NO-ask levels (1 - YES bid) on the other, accumulating
exact cost and exact fees at every level boundary.

Conservatism, as everywhere in Tinli:
- Fees are charged PER SEGMENT (each price level treated as its own fill).
  Sum-of-ceilings >= ceiling-of-sum, so this can only overstate fees and
  understate the edge.
- The walk STOPS when a segment's exact net edge turns non-positive only
  for the purpose of the optimal point; the curve itself continues (capped)
  so the UI can show the decay honestly.
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

    if k_ask <= p_ask:
        direction = "buy_yes_kalshi_no_polymarket"
        yes_levels = [(lv.price, lv.size) for lv in kalshi_book.asks]
        no_levels = [(ONE - lv.price, lv.size) for lv in pm_book.bids]  # best-first ✓
        yes_fees, no_fees = kalshi_fees, pm_fees
    else:
        direction = "buy_yes_polymarket_no_kalshi"
        yes_levels = [(lv.price, lv.size) for lv in pm_book.asks]
        no_levels = [(ONE - lv.price, lv.size) for lv in kalshi_book.bids]
        yes_fees, no_fees = pm_fees, kalshi_fees

    points: list[SizePoint] = []
    size = ZERO
    cost = ZERO  # both legs, ex-fees
    fees = ZERO
    yi = ni = 0
    yes_rem = yes_levels[0][1]
    no_rem = no_levels[0][1]

    while yi < len(yes_levels) and ni < len(no_levels) and len(points) < MAX_POINTS:
        py, pn = yes_levels[yi][0], no_levels[ni][0]
        seg = min(yes_rem, no_rem)
        if seg <= 0:
            break
        size += seg
        cost += (py + pn) * seg
        fees += yes_fees.taker_fee(py, seg) + no_fees.taker_fee(pn, seg)
        capital = cost + fees
        profit = size - capital  # lock pays $1 x size at settlement
        points.append(
            SizePoint(
                size=size,
                avg_yes=ZERO,  # filled below once totals are known
                avg_no=ZERO,
                per_contract_edge=(profit / size).quantize(SIX_DP, rounding=ROUND_FLOOR),
                total_profit=profit.quantize(CENT, rounding=ROUND_FLOOR),
                # capital REQUIRED rounds up, like every risk number
                capital=capital.quantize(CENT, rounding=ROUND_CEILING),
            )
        )
        yes_rem -= seg
        no_rem -= seg
        if yes_rem == 0:
            yi += 1
            yes_rem = yes_levels[yi][1] if yi < len(yes_levels) else ZERO
        if no_rem == 0:
            ni += 1
            no_rem = no_levels[ni][1] if ni < len(no_levels) else ZERO

    # size-weighted average fill prices per breakpoint (second pass keeps the
    # walk itself simple)
    acc_yes = ZERO
    acc_no = ZERO
    walked = ZERO
    yi = ni = 0
    yes_rem = yes_levels[0][1]
    no_rem = no_levels[0][1]
    for pt in points:
        while walked < pt.size:
            seg = min(yes_rem, no_rem, pt.size - walked)
            acc_yes += yes_levels[yi][0] * seg
            acc_no += no_levels[ni][0] * seg
            walked += seg
            yes_rem -= seg
            no_rem -= seg
            if yes_rem == 0 and yi + 1 < len(yes_levels):
                yi += 1
                yes_rem = yes_levels[yi][1]
            if no_rem == 0 and ni + 1 < len(no_levels):
                ni += 1
                no_rem = no_levels[ni][1]
        pt.avg_yes = (acc_yes / pt.size).quantize(SIX_DP)
        pt.avg_no = (acc_no / pt.size).quantize(SIX_DP)

    best = max(points, key=lambda p: p.total_profit, default=None)
    optimal = best if best is not None and best.total_profit > 0 else None
    exhausted = len(points) < MAX_POINTS
    return LockCurve(direction=direction, points=points, optimal=optimal, depth_exhausted=exhausted)
