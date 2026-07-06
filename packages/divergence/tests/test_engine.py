"""Hand-computed divergence cases. Every expected number is derived in the
comments — if a test fails, redo the arithmetic before touching the engine."""

from datetime import UTC, datetime
from decimal import Decimal

from tinli_schema import Orderbook, OrderbookLevel, PairMapping

from tinli_divergence import NullFees, compute_pair, sort_items

NOW = datetime(2026, 7, 6, tzinfo=UTC)


def book(venue: str, bids: list[tuple[str, str]], asks: list[tuple[str, str]]) -> Orderbook:
    return Orderbook(
        market_id=f"{venue}:test",
        venue=venue,
        bids=[OrderbookLevel(price=p, size=s) for p, s in bids],
        asks=[OrderbookLevel(price=p, size=s) for p, s in asks],
        fetched_at=NOW,
    )


def pair(**overrides) -> PairMapping:
    defaults = dict(
        event_key="test-pair",
        question="?",
        kalshi_ticker="KXTEST",
        pm_condition_id="0x" + "0" * 64,
        pm_yes_token=0,
        criteria_verified=True,
        pm_fee_category="sports",
    )
    return PairMapping(**{**defaults, **overrides})


def test_symmetric_zero_fee_lock():
    # Kalshi: bid 0.44, ask 0.46 (size 100). PM: bid 0.52 (size 200), ask 0.54.
    # Kalshi YES ask 0.46 <= PM YES ask 0.54 -> buy YES on Kalshi.
    #   NO leg on PM: ask_no = 1 - 0.52 = 0.48, depth = 200.
    #   gross = 1 - 0.46 - 0.48 = 0.06; zero fees -> fee_adjusted_edge = 0.06
    #   max_lock = min(100, 200) = 100; edge_at_size = 0.06
    # raw basis: mids 0.45 vs 0.53 -> 100 x (0.45 - 0.53) = -8.0 cents
    item = compute_pair(
        pair(),
        book("kalshi", bids=[("0.44", "100")], asks=[("0.46", "100")]),
        book("polymarket", bids=[("0.52", "200")], asks=[("0.54", "200")]),
        NOW,
        kalshi_fees=NullFees(),
        pm_fees=NullFees(),
    )
    assert item.direction == "buy_yes_kalshi_no_polymarket"
    assert item.fee_adjusted_edge == Decimal("0.06")
    assert item.max_lock_size == Decimal("100")
    assert item.edge_at_size == Decimal("0.06")
    assert item.raw_basis_cents == Decimal("-8.0")


def test_fees_kill_the_edge():
    # Kalshi: bid 0.48, ask 0.50. PM: bid 0.51, ask 0.53. Real fee models.
    # Direction: Kalshi ask 0.50 <= 0.53 -> YES on Kalshi at 0.50,
    #   NO on PM at 1 - 0.51 = 0.49.
    # gross = 1 - 0.50 - 0.49 = 0.01  (a real 1-cent gross lock!)
    # idealized fees per contract:
    #   Kalshi: 0.07 x 0.50 x 0.50           = 0.0175
    #   PM sports: 0.03 x 0.49 x 0.51        = 0.0074970
    # fee_adjusted = 0.01 - 0.0175 - 0.007497 = -0.014997 -> fees ate it
    item = compute_pair(
        pair(),
        book("kalshi", bids=[("0.48", "500")], asks=[("0.50", "500")]),
        book("polymarket", bids=[("0.51", "500")], asks=[("0.53", "500")]),
        NOW,
    )
    assert item.fee_adjusted_edge == Decimal("-0.014997")
    assert item.fee_adjusted_edge < 0 < Decimal("0.01")  # gross was positive


def test_depth_limited_edge_with_exact_fee_rounding():
    # Kalshi: bid 0.40, ask 0.42 size 30. PM: bid 0.50 size 500, ask 0.52.
    # Direction: YES on Kalshi at 0.42; NO on PM at 1 - 0.50 = 0.50.
    # gross = 1 - 0.42 - 0.50 = 0.08
    # max_lock = min(30, 500) = 30  <- the thin Kalshi ask caps the lock
    # exact fees on 30 contracts:
    #   Kalshi: 0.07 x 30 x 0.42 x 0.58 = 0.511560 -> ceil cent -> 0.52
    #   PM:     30 x 0.03 x 0.50 x 0.50 = 0.225    -> 5dp        -> 0.22500
    #   total 0.74500 -> per contract 0.745/30 = 0.02483333...
    # edge_at_size = 0.08 - 0.0248333... = 0.0551666... -> engine floors to
    # 6dp (never round an edge UP) -> 0.055166
    item = compute_pair(
        pair(),
        book("kalshi", bids=[("0.40", "30")], asks=[("0.42", "30")]),
        book("polymarket", bids=[("0.50", "500")], asks=[("0.52", "500")]),
        NOW,
    )
    assert item.max_lock_size == Decimal("30")
    assert item.edge_at_size == Decimal("0.055166")
    # idealized per-contract fees are cheaper than the rounded ones:
    #   Kalshi 0.07x0.42x0.58 = 0.0170520; PM 0.03x0.5x0.5 = 0.0075
    #   fee_adjusted = 0.08 - 0.017052 - 0.0075 = 0.055448
    assert item.fee_adjusted_edge == Decimal("0.055448")
    assert item.edge_at_size < item.fee_adjusted_edge


def test_negative_edge_reported_not_hidden():
    # Kalshi: bid 0.45, ask 0.47. PM: bid 0.44, ask 0.46.
    # Direction: PM ask 0.46 <= Kalshi ask 0.47 -> YES on PM at 0.46,
    #   NO on Kalshi at 1 - 0.45 = 0.55.
    # gross = 1 - 0.46 - 0.55 = -0.01 -> no lock exists; report it, zero fees
    item = compute_pair(
        pair(),
        book("kalshi", bids=[("0.45", "10")], asks=[("0.47", "10")]),
        book("polymarket", bids=[("0.44", "10")], asks=[("0.46", "10")]),
        NOW,
        kalshi_fees=NullFees(),
        pm_fees=NullFees(),
    )
    assert item.direction == "buy_yes_polymarket_no_kalshi"
    assert item.fee_adjusted_edge == Decimal("-0.01")


def test_empty_book_side_yields_null_edge():
    # Kalshi has no asks (e.g. settled market) -> no executable YES leg ->
    # every edge field is None; no fabricated numbers.
    item = compute_pair(
        pair(),
        book("kalshi", bids=[("0.45", "10")], asks=[]),
        book("polymarket", bids=[("0.44", "10")], asks=[("0.46", "10")]),
        NOW,
        kalshi_fees=NullFees(),
        pm_fees=NullFees(),
    )
    assert item.direction is None
    assert item.fee_adjusted_edge is None
    assert item.max_lock_size is None
    assert item.edge_at_size is None
    assert item.raw_basis_cents is None  # kalshi mid needs both sides


def test_unverified_pairs_sort_last_regardless_of_edge():
    # verified pair with a tiny 0.5c edge must outrank an unverified pair
    # with a monster 14c "edge" — mismatched criteria make it a trap.
    small_verified = compute_pair(
        pair(event_key="small-but-real"),
        book("kalshi", bids=[("0.50", "10")], asks=[("0.51", "10")]),
        book("polymarket", bids=[("0.525", "10")], asks=[("0.53", "10")]),
        NOW,
        kalshi_fees=NullFees(),
        pm_fees=NullFees(),
    )
    big_unverified = compute_pair(
        pair(event_key="trap", criteria_verified=False),
        book("kalshi", bids=[("0.40", "10")], asks=[("0.42", "10")]),
        book("polymarket", bids=[("0.72", "10")], asks=[("0.74", "10")]),
        NOW,
        kalshi_fees=NullFees(),
        pm_fees=NullFees(),
    )
    assert abs(big_unverified.fee_adjusted_edge) > abs(small_verified.fee_adjusted_edge)
    ordered = sort_items([big_unverified, small_verified])
    assert [i.event_key for i in ordered] == ["small-but-real", "trap"]


def test_missing_fee_category_flags_worst_case():
    item = compute_pair(
        pair(pm_fee_category=None),
        book("kalshi", bids=[("0.44", "100")], asks=[("0.46", "100")]),
        book("polymarket", bids=[("0.52", "200")], asks=[("0.54", "200")]),
        NOW,
    )
    assert item.fee_assumed_worst_case is True
