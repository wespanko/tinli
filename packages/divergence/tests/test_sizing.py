"""Hand-computed lock-curve cases + property tests. Every expected number is
derived in the comments — if a test fails, redo the arithmetic before touching
walk_lock."""

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given
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


# ---- properties ------------------------------------------------------------

prices = st.decimals(min_value="0.01", max_value="0.99", places=2)
sizes = st.integers(min_value=1, max_value=500).map(Decimal)


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


@given(levels, levels, levels, levels)
def test_real_fees_only_ever_reduce_the_curve(kb, ka, pb, pa):
    k_book = _sorted_book("kalshi", kb, ka)
    p_book = _sorted_book("polymarket", pb, pa)
    free = walk_lock(k_book, p_book, NullFees(), NullFees())
    paid = walk_lock(k_book, p_book, KalshiFees(), PolymarketFees("sports"))
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
