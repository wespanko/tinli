"""Cross-venue divergence engine.

SIGN CONVENTION (the single authoritative statement — the API docstring
echoes this): raw_basis_cents = 100 x (kalshi_yes_mid - polymarket_yes_mid).
POSITIVE basis means Kalshi prices YES richer than Polymarket; negative
means Kalshi is cheaper. Mids are top-of-book (best_bid+best_ask)/2 from
the normalized YES books — never last-trade prints.

THE LOCK. For a matched pair, buying YES on one venue and NO on the other
locks $1.00 at resolution regardless of outcome (assuming the resolution
criteria really are equivalent — hence criteria_verified). We price the
lock with EXECUTABLE asks only:

  Direction: both assignments of the YES/NO legs are priced and the one
           with the better fee-adjusted edge is reported (rationale at the
           selection site in compute_pair). Books are normalized YES-side,
           so a venue's NO ask at price p is its YES bid at 1-p (both
           venues' complement identity; sizes carry over).

  gross_edge          = 1 - ask_yes - ask_no          (per contract)
  fee_adjusted_edge   = gross_edge - fees(1 contract, idealized unrounded)
  max_lock_size       = min(top-of-book depth on both legs), floored to
                        WHOLE contracts — the executable unit both venues
                        always accept (fractional trading exists on some
                        markets; ignoring it only understates size)
  edge_at_size        = per-contract edge at max_lock_size with each
                        venue's EXACT fee rounding applied to the full fill

Fees use taker models only — the lock crosses the spread on both legs.
Any missing book side makes the edge fields None: no executable price,
no claimed edge.
"""

from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Literal

from pydantic import BaseModel, Field

from tinli_schema import Orderbook, PairMapping

from tinli_divergence.fees import FeeModel, KalshiFees, PolymarketFees

ONE = Decimal("1")
HUNDRED = Decimal("100")
SIX_DP = Decimal("0.000001")


class VenueTop(BaseModel):
    """Top-of-book for one venue, YES-side."""

    bid: Decimal | None
    bid_size: Decimal | None
    ask: Decimal | None
    ask_size: Decimal | None


class DivergenceItem(BaseModel):
    event_key: str
    question: str
    criteria_verified: bool
    notes: str
    kalshi: VenueTop
    polymarket: VenueTop
    raw_basis_cents: Decimal | None = Field(
        description="100 x (kalshi_yes_mid - polymarket_yes_mid); positive = Kalshi rich"
    )
    direction: Literal["buy_yes_kalshi_no_polymarket", "buy_yes_polymarket_no_kalshi"] | None = (
        Field(description="which venue takes the YES leg of the lock")
    )
    fee_adjusted_edge: Decimal | None = Field(
        description="per-contract lock edge in dollars after idealized taker fees"
    )
    max_lock_size: Decimal | None = Field(
        description="min top-of-book depth across both legs, floored to whole "
        "contracts (the always-executable unit; sizing rounds against the user)"
    )
    edge_at_size: Decimal | None = Field(
        description="per-contract edge at max_lock_size with exact venue fee rounding"
    )
    legging_cost_per_contract: Decimal | None = Field(
        default=None,
        description="worst case of missing ONE leg: unwind the filled leg "
        "immediately at its venue's top-of-book, paying the spread plus taker "
        "fees both ways (idealized rates, rounded up). Adverse moves between "
        "fill and unwind are not modeled.",
    )
    fee_assumed_worst_case: bool = Field(
        description="True when the PM fee category was missing and the worst-case rate was used"
    )
    fetched_at: datetime


def top(book: Orderbook) -> VenueTop:
    return VenueTop(
        bid=book.bids[0].price if book.bids else None,
        bid_size=book.bids[0].size if book.bids else None,
        ask=book.asks[0].price if book.asks else None,
        ask_size=book.asks[0].size if book.asks else None,
    )


def _mid(t: VenueTop) -> Decimal | None:
    if t.bid is None or t.ask is None:
        return None
    return (t.bid + t.ask) / 2


def compute_pair(
    pair: PairMapping,
    kalshi_book: Orderbook,
    pm_book: Orderbook,
    fetched_at: datetime,
    kalshi_fees: FeeModel | None = None,
    pm_fees: FeeModel | None = None,
) -> DivergenceItem:
    k_fees = kalshi_fees if kalshi_fees is not None else KalshiFees()
    p_fees = pm_fees if pm_fees is not None else PolymarketFees(pair.pm_fee_category)
    k, p = top(kalshi_book), top(pm_book)

    k_mid, p_mid = _mid(k), _mid(p)
    raw_basis = HUNDRED * (k_mid - p_mid) if k_mid is not None and p_mid is not None else None

    direction = None
    fee_adjusted_edge = None
    max_lock_size = None
    edge_at_size = None
    legging_cost = None

    # NO ask on a venue = 1 - its YES bid (books are YES-side normalized);
    # the NO leg consumes the YES bid's depth.
    #
    # DIRECTION: evaluate the fee-adjusted edge of BOTH lock directions and
    # keep the better one. The obvious shortcut (cheaper YES ask takes the
    # YES leg) is wrong on wide-spread pairs: gross_K + gross_P =
    # -(k.ask - k.bid) - (p.ask - p.bid) <= 0, so at most one direction has
    # positive gross, and it is the one with the LOWER TOTAL COST
    # ask_yes + ask_no — which compares mids (k.ask + k.bid vs p.ask +
    # p.bid), not asks. A positive edge can never hide in the rejected
    # direction under either rule (that would need p.ask < k.bid <= k.ask
    # <= p.ask, a crossed book), but the ask rule could report the worse of
    # two negative edges. Fees are venue-asymmetric, so we compare after
    # fees rather than by cost alone; kalshi-YES wins ties for determinism.
    legs_ready = k.ask is not None and p.ask is not None and k.bid is not None and p.bid is not None
    if legs_ready:
        candidates = [
            (
                "buy_yes_kalshi_no_polymarket",
                k.ask, k.ask_size, k_fees,
                ONE - p.bid, p.bid_size, p_fees,
            ),
            (
                "buy_yes_polymarket_no_kalshi",
                p.ask, p.ask_size, p_fees,
                ONE - k.bid, k.bid_size, k_fees,
            ),
        ]
        best = None
        for cand in candidates:
            _, ask_yes, _, yes_fees, ask_no, _, no_fees = cand
            gross = ONE - ask_yes - ask_no
            per_contract_fees = (
                yes_fees.taker_rate() * ask_yes * (ONE - ask_yes)
                + no_fees.taker_rate() * ask_no * (ONE - ask_no)
            )
            edge = gross - per_contract_fees
            if best is None or edge > best[0]:
                best = (edge, gross, cand)
        fee_adjusted_edge, gross, chosen = best
        direction, ask_yes, yes_size, yes_fees, ask_no, no_size, no_fees = chosen

        # LEGGING RISK: if only one leg fills, the worst-case bail-out is an
        # immediate taker unwind on that leg's own venue — pay the spread
        # plus fees both ways. The NO leg's round trip is buy NO at
        # 1 - yes_bid, sell NO at 1 - yes_ask: the same venue YES spread.
        # A cost rounds UP, like every number charged against the user.
        def _unwind(p_in: Decimal, p_out: Decimal, f: FeeModel) -> Decimal:
            return (p_in - p_out) + f.taker_rate() * (
                p_in * (ONE - p_in) + p_out * (ONE - p_out)
            )

        if direction == "buy_yes_kalshi_no_polymarket":
            worst = max(
                _unwind(k.ask, k.bid, k_fees),
                _unwind(ONE - p.bid, ONE - p.ask, p_fees),
            )
        else:
            worst = max(
                _unwind(p.ask, p.bid, p_fees),
                _unwind(ONE - k.bid, ONE - k.ask, k_fees),
            )
        legging_cost = worst.quantize(SIX_DP, rounding=ROUND_CEILING)

        # whole contracts only: Kalshi books quote 2dp sizes and some markets
        # allow fractional trading, but an integer order is valid everywhere —
        # flooring can only understate the lock (docs/VENUES.md recon)
        max_lock_size = min(yes_size, no_size).to_integral_value(rounding=ROUND_FLOOR)
        if max_lock_size > 0:
            exact_fees = yes_fees.taker_fee(ask_yes, max_lock_size) + no_fees.taker_fee(
                ask_no, max_lock_size
            )
            # ROUND_FLOOR: quantizing toward -inf can only UNDERstate the
            # edge — the screener must never round an edge into existence
            edge_at_size = (gross - exact_fees / max_lock_size).quantize(
                SIX_DP, rounding=ROUND_FLOOR
            )

    return DivergenceItem(
        event_key=pair.event_key,
        question=pair.question,
        criteria_verified=pair.criteria_verified,
        notes=pair.notes,
        kalshi=k,
        polymarket=p,
        raw_basis_cents=raw_basis,
        direction=direction,
        fee_adjusted_edge=fee_adjusted_edge,
        max_lock_size=max_lock_size,
        edge_at_size=edge_at_size,
        legging_cost_per_contract=legging_cost,
        fee_assumed_worst_case=getattr(p_fees, "assumed_worst_case", False),
        fetched_at=fetched_at,
    )


def sort_items(items: list[DivergenceItem]) -> list[DivergenceItem]:
    """|fee_adjusted_edge| desc; edgeless items after edged ones; and
    UNVERIFIED PAIRS ALWAYS LAST — a big 'edge' on mismatched resolution
    criteria is a trap, and burying it below verified pairs is the point."""

    def key(item: DivergenceItem):
        has_edge = item.fee_adjusted_edge is not None
        return (
            0 if item.criteria_verified else 1,
            0 if has_edge else 1,
            -abs(item.fee_adjusted_edge) if has_edge else Decimal("0"),
        )

    return sorted(items, key=key)
