"""Hand-computed lock-curve cases + property tests. Every expected number is
derived in the comments — if a test fails, redo the arithmetic before touching
walk_lock."""

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import assume, given
from hypothesis import strategies as st

from tinli_schema import Orderbook, OrderbookLevel

from tinli_divergence import KalshiFees, NullFees, PolymarketFees, walk_lock

NOW = datetime(2026, 7, 18, tzinfo=UTC)


def book(venue: str, bids: list[tuple[str, str]], asks: list[tuple[str, str]]) -> Orderbook:
    return Orderbook(
        market_id=f"{venue}:test",
        venue=venue,
        bids=[OrderbookLevel(price=p, size=s) for p, s in bids],
        asks=[OrderbookLevel(price=p, size=s) for p, s in asks],
        fetched_at=NOW,
    )


def test_two_level_walk_zero_fees():
    # Kalshi asks 0.46x100 then 0.48x50; PM bids 0.52x80 then 0.50x120
    # (NO asks 0.48x80 then 0.50x120). Direction: 0.46 <= 0.54 -> YES Kalshi.
    # Breakpoints (segment = min of remaining level sizes):
    #   80:  cost (0.46+0.48)*80          = 75.20  profit 80-75.20  = 4.80
    #  100:  +(0.46+0.50)*20  -> 94.40             profit 100-94.40 = 5.60
    #  150:  +(0.48+0.50)*50  -> 143.40            profit 150-143.40= 6.60
    # per-contract: 4.80/80=0.06, 5.60/100=0.056, 6.60/150=0.044
    curve = walk_lock(
        book("kalshi", bids=[("0.44", "100")], asks=[("0.46", "100"), ("0.48", "50")]),
        book("polymarket", bids=[("0.52", "80"), ("0.50", "120")], asks=[("0.54", "200")]),
        NullFees(),
        NullFees(),
    )
    assert curve.direction == "buy_yes_kalshi_no_polymarket"
    assert [p.size for p in curve.points] == [Decimal("80"), Decimal("100"), Decimal("150")]
    assert [p.total_profit for p in curve.points] == [
        Decimal("4.80"),
        Decimal("5.60"),
        Decimal("6.60"),
    ]
    assert [p.per_contract_edge for p in curve.points] == [
        Decimal("0.06"),
        Decimal("0.056"),
        Decimal("0.044"),
    ]
    # deepest point still adds profit -> optimal is the last point
    assert curve.optimal is not None and curve.optimal.size == Decimal("150")
    assert curve.depth_exhausted is True
    # size-weighted average fills at 150: YES (0.46*100+0.48*50)/150 = 70/150,
    # NO (0.48*80+0.50*70)/150 = 73.40/150
    assert curve.points[-1].avg_yes == Decimal("0.466667")
    assert curve.points[-1].avg_no == Decimal("0.489333")
    assert curve.points[0].avg_yes == Decimal("0.46")
    assert curve.points[0].avg_no == Decimal("0.48")


def test_optimal_is_interior_when_depth_turns_negative():
    # Level 2 prices sum to 1.22 -> marginal edge -0.22/contract. The curve
    # keeps going (the UI shows the decay) but optimal stays at size 100.
    #   100: cost 0.94*100 = 94    profit  +6.00
    #   200: +1.22*100 = 216       profit -16.00
    curve = walk_lock(
        book("kalshi", bids=[("0.40", "5")], asks=[("0.46", "100"), ("0.60", "100")]),
        book("polymarket", bids=[("0.52", "100"), ("0.38", "100")], asks=[("0.54", "5")]),
        NullFees(),
        NullFees(),
    )
    assert [p.total_profit for p in curve.points] == [Decimal("6.00"), Decimal("-16.00")]
    assert curve.optimal is not None and curve.optimal.size == Decimal("100")
    assert curve.points[-1].per_contract_edge == Decimal("-0.08")


def test_single_level_matches_engine_edge_at_size():
    # Same book as the engine's depth-limited test: YES Kalshi 0.42x30, NO PM
    # 0.50x500. Exact fees on 30: Kalshi ceil(0.07*30*0.42*0.58)=0.52, PM
    # 0.03*30*0.25=0.22500. capital = 27.60+0.745 = 28.345 -> CEILING 28.35.
    # profit = 30-28.345 = 1.655 -> FLOOR 1.65; per-contract 0.055166 (floored)
    # == the engine's edge_at_size for this book, by construction.
    curve = walk_lock(
        book("kalshi", bids=[("0.40", "30")], asks=[("0.42", "30")]),
        book("polymarket", bids=[("0.50", "500")], asks=[("0.52", "500")]),
        KalshiFees(),
        PolymarketFees("sports"),
    )
    assert len(curve.points) == 1
    pt = curve.points[0]
    assert pt.size == Decimal("30")
    assert pt.capital == Decimal("28.35")
    assert pt.total_profit == Decimal("1.65")
    assert pt.per_contract_edge == Decimal("0.055166")
    assert curve.optimal == pt


def test_empty_book_side_yields_empty_curve():
    curve = walk_lock(
        book("kalshi", bids=[("0.45", "10")], asks=[]),
        book("polymarket", bids=[("0.44", "10")], asks=[("0.46", "10")]),
        NullFees(),
        NullFees(),
    )
    assert curve.direction is None
    assert curve.points == []
    assert curve.optimal is None
    assert curve.depth_exhausted is True


def test_no_optimal_when_lock_never_profits():
    # Prices sum above $1 from the first contract: every profit negative.
    curve = walk_lock(
        book("kalshi", bids=[("0.50", "10")], asks=[("0.56", "10")]),
        book("polymarket", bids=[("0.52", "10")], asks=[("0.58", "10")]),
        NullFees(),
        NullFees(),
    )
    assert curve.points and all(p.total_profit < 0 for p in curve.points)
    assert curve.optimal is None


def test_fractional_depth_floors_to_whole_contracts():
    # YES ask 0.46 x 2.5 vs NO ask 0.48 (PM bid 0.52) x 10: capacity 2.5,
    # floored to a single point at 2 contracts.
    #   cost = (0.46 + 0.48) * 2 = 1.88; zero fees -> profit = 2 - 1.88 = 0.12
    curve = walk_lock(
        book("kalshi", bids=[("0.44", "10")], asks=[("0.46", "2.5")]),
        book("polymarket", bids=[("0.52", "10")], asks=[("0.54", "10")]),
        NullFees(),
        NullFees(),
    )
    assert [p.size for p in curve.points] == [Decimal("2")]
    assert curve.points[0].total_profit == Decimal("0.12")
    assert curve.optimal is not None and curve.optimal.size == Decimal("2")


def test_sub_contract_depth_yields_empty_curve():
    # 0.9 contracts of depth cannot fill one whole contract: no points, no
    # optimal, and no fabricated sub-contract "lock"
    curve = walk_lock(
        book("kalshi", bids=[("0.44", "10")], asks=[("0.46", "0.9")]),
        book("polymarket", bids=[("0.52", "10")], asks=[("0.54", "10")]),
        NullFees(),
        NullFees(),
    )
    assert curve.points == []
    assert curve.optimal is None


# ---- properties ------------------------------------------------------------

prices = st.decimals(min_value="0.01", max_value="0.99", places=2)
# fractional sizes exercise the whole-contract flooring
sizes = st.decimals(min_value="0.01", max_value="500", places=2)


def _sorted_book(venue: str, bid_levels, ask_levels) -> Orderbook:
    """Best-first: bids descending, asks ascending, deduped prices."""
    bids = sorted({p for p, _ in bid_levels}, reverse=True)
    asks = sorted({p for p, _ in ask_levels})
    return Orderbook(
        market_id=f"{venue}:prop",
        venue=venue,
        bids=[OrderbookLevel(price=p, size=s) for p, (_, s) in zip(bids, bid_levels)],
        asks=[OrderbookLevel(price=p, size=s) for p, (_, s) in zip(asks, ask_levels)],
        fetched_at=NOW,
    )


levels = st.lists(st.tuples(prices, sizes), min_size=1, max_size=4)


@given(levels, levels, levels, levels)
def test_zero_fee_per_contract_edge_never_increases_with_size(kb, ka, pb, pa):
    # Marginal prices are non-decreasing walking away from top-of-book, so the
    # AVERAGE per-contract edge is non-increasing — with exact (null) fees.
    # (Real fee models break strict monotonicity by cent-ceiling noise only.)
    curve = walk_lock(
        _sorted_book("kalshi", kb, ka), _sorted_book("polymarket", pb, pa),
        NullFees(), NullFees(),
    )
    edges = [p.per_contract_edge for p in curve.points]
    assert all(a >= b for a, b in zip(edges, edges[1:]))
    assert all(a.size < b.size for a, b in zip(curve.points, curve.points[1:]))
    # every point is an executable whole-contract size
    assert all(p.size == p.size.to_integral_value() for p in curve.points)


@given(levels, levels, levels, levels)
def test_real_fees_only_ever_reduce_the_curve(kb, ka, pb, pa):
    k_book = _sorted_book("kalshi", kb, ka)
    p_book = _sorted_book("polymarket", pb, pa)
    free = walk_lock(k_book, p_book, NullFees(), NullFees())
    paid = walk_lock(k_book, p_book, KalshiFees(), PolymarketFees("sports"))
    # venue-asymmetric fees can legitimately flip the better direction (on
    # gross ties, or on the crossed books this strategy can generate); the
    # free-vs-paid comparison is only leg-for-leg meaningful when both walks
    # took the same legs
    assume(free.direction == paid.direction)
    assert [p.size for p in free.points] == [p.size for p in paid.points]
    for f, p in zip(free.points, paid.points):
        assert p.capital >= f.capital  # fees only add to capital
        assert p.total_profit <= f.total_profit  # and only shrink profit
        assert p.per_contract_edge <= f.per_contract_edge


@given(levels, levels, levels, levels)
def test_optimal_is_the_profit_maximum_and_positive(kb, ka, pb, pa):
    curve = walk_lock(
        _sorted_book("kalshi", kb, ka), _sorted_book("polymarket", pb, pa),
        KalshiFees(), PolymarketFees("sports"),
    )
    if curve.optimal is None:
        assert all(p.total_profit <= 0 for p in curve.points)
    else:
        assert curve.optimal.total_profit > 0
        assert curve.optimal.total_profit == max(p.total_profit for p in curve.points)


def _two_level():
    # same books as test_two_level_walk_zero_fees: capital(n) = 0.94n for
    # n <= 80, 75.20 + 0.96(n-80) for 80 < n <= 100, 94.40 + 0.98(n-100) after
    return (
        book("kalshi", bids=[("0.44", "100")], asks=[("0.46", "100"), ("0.48", "50")]),
        book("polymarket", bids=[("0.52", "80"), ("0.50", "120")], asks=[("0.54", "200")]),
    )


def test_bankroll_buys_largest_affordable_whole_lock():
    k, p = _two_level()
    # $50 / 0.94 = 53.19 -> 53 contracts, capital 49.82, profit 3.18
    curve = walk_lock(k, p, NullFees(), NullFees(), bankroll=Decimal("50"))
    fill = curve.for_bankroll
    assert fill is not None
    assert fill.size == Decimal("53")
    assert fill.capital == Decimal("49.82")
    assert fill.total_profit == Decimal("3.18")
    assert fill.binding == "bankroll"
    assert fill.bankroll == Decimal("50")
    assert curve.depth_contracts == Decimal("150")


def test_bankroll_past_depth_binds_on_depth():
    k, p = _two_level()
    # full depth is 150 contracts at capital 143.40; a bigger bankroll stops there
    curve = walk_lock(k, p, NullFees(), NullFees(), bankroll=Decimal("1000"))
    assert curve.for_bankroll is not None
    assert curve.for_bankroll.size == Decimal("150")
    assert curve.for_bankroll.capital == Decimal("143.40")
    assert curve.for_bankroll.binding == "depth"


def test_bankroll_never_sizes_past_the_profit_maximum():
    # the interior-optimum book: 100 profitable contracts, then a losing level
    curve = walk_lock(
        book("kalshi", bids=[("0.40", "5")], asks=[("0.46", "100"), ("0.60", "100")]),
        book("polymarket", bids=[("0.52", "100"), ("0.38", "100")], asks=[("0.54", "5")]),
        NullFees(),
        NullFees(),
        bankroll=Decimal("500"),
    )
    assert curve.for_bankroll is not None
    assert curve.for_bankroll.size == Decimal("100")
    assert curve.for_bankroll.binding == "edge"


def test_bankroll_too_small_for_one_contract_is_none():
    k, p = _two_level()
    curve = walk_lock(k, p, NullFees(), NullFees(), bankroll=Decimal("0.50"))
    assert curve.for_bankroll is None
    assert curve.points  # the curve itself is unaffected


def test_losing_lock_is_still_sized_for_a_bankroll():
    # asks sum to 1.02: every contract loses 2c, no optimal — but the user
    # asked what the trade would cost, so the fill is still reported
    curve = walk_lock(
        book("kalshi", bids=[("0.40", "50")], asks=[("0.52", "50")]),
        book("polymarket", bids=[("0.50", "50")], asks=[("0.60", "50")]),
        NullFees(),
        NullFees(),
        bankroll=Decimal("10.20"),
    )
    assert curve.optimal is None
    assert curve.for_bankroll is not None
    assert curve.for_bankroll.size == Decimal("10")
    assert curve.for_bankroll.total_profit == Decimal("-0.20")
    assert curve.for_bankroll.binding == "bankroll"
