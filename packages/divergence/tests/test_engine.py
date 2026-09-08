"""Hand-computed divergence cases. Every expected number is derived in the
comments — if a test fails, redo the arithmetic before touching the engine."""

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from tinli_schema import Orderbook, OrderbookLevel, PairMapping

from tinli_divergence import (
    KalshiFees,
    NullFees,
    PolymarketFees,
    compute_pair,
    sort_items,
    walk_lock,
)

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


def test_direction_minimizes_cost_not_cheapest_yes_ask():
    # WIDE-SPREAD case where the naive rule (cheaper YES ask takes the YES
    # leg) picks the wrong direction. K: bid 0.40 / ask 0.50, PM: bid 0.20 /
    # ask 0.51. Zero fees.
    #   YES on Kalshi (naive pick, ask 0.50 <= 0.51):
    #     gross = 1 - 0.50 - (1 - 0.20) = 1 - 0.50 - 0.80 = -0.30
    #   YES on Polymarket:
    #     gross = 1 - 0.51 - (1 - 0.40) = 1 - 0.51 - 0.60 = -0.11  <- better
    # No positive edge exists either way (that would need a crossed book),
    # but the reported divergence must be the best executable one.
    item = compute_pair(
        pair(),
        book("kalshi", bids=[("0.40", "10")], asks=[("0.50", "10")]),
        book("polymarket", bids=[("0.20", "10")], asks=[("0.51", "10")]),
        NOW,
        kalshi_fees=NullFees(),
        pm_fees=NullFees(),
    )
    assert item.direction == "buy_yes_polymarket_no_kalshi"
    assert item.fee_adjusted_edge == Decimal("-0.11")


def test_direction_tie_in_gross_broken_by_fees():
    # Equal mids -> equal gross both ways; venue fee asymmetry decides.
    # K: bid 0.89 / ask 0.91 (mid 0.90), PM: bid 0.895 / ask 0.905 (mid 0.90).
    # gross either way = 1 - 0.91 - 0.105 = 1 - 0.905 - 0.11 = -0.015.
    # Fees (Kalshi 7%, PM sports 3%), f(p) = rate*p*(1-p):
    #   YES Kalshi:  0.07*0.91*0.09 + 0.03*0.105*0.895
    #              = 0.0057330 + 0.00281925 = 0.00855225
    #   YES PM:      0.03*0.905*0.095 + 0.07*0.11*0.89
    #              = 0.00257925 + 0.0068530  = 0.00943225
    # Kalshi-YES puts the expensive 7% venue at the price FARTHEST from 0.5
    # where p*(1-p) is smallest -> cheaper. edge = -0.015 - 0.00855225.
    # The naive ask rule (0.905 < 0.91) would pick the worse PM-YES side.
    item = compute_pair(
        pair(),
        book("kalshi", bids=[("0.89", "10")], asks=[("0.91", "10")]),
        book("polymarket", bids=[("0.895", "10")], asks=[("0.905", "10")]),
        NOW,
    )
    assert item.direction == "buy_yes_kalshi_no_polymarket"
    assert item.fee_adjusted_edge == Decimal("-0.02355225")


@given(
    k_bid=st.integers(min_value=1, max_value=97),
    k_spread=st.integers(min_value=1, max_value=20),
    p_bid=st.integers(min_value=1, max_value=97),
    p_spread=st.integers(min_value=1, max_value=20),
)
def test_direction_is_always_the_better_of_the_two(k_bid, k_spread, p_bid, p_spread):
    # Invariants, any non-crossed books (prices on the cent grid, capped
    # below 1): (1) the chosen direction's fee-adjusted edge is >= the
    # rejected direction's; (2) walk_lock agrees with the screener.
    cent = Decimal("0.01")
    kb, ka = cent * k_bid, cent * min(k_bid + k_spread, 99)
    pb, pa = cent * p_bid, cent * min(p_bid + p_spread, 99)
    k_book = book("kalshi", bids=[(str(kb), "50")], asks=[(str(ka), "50")])
    p_book = book("polymarket", bids=[(str(pb), "50")], asks=[(str(pa), "50")])
    kf, pf = KalshiFees(), PolymarketFees("sports")
    item = compute_pair(pair(), k_book, p_book, NOW)

    def edge(ask_yes, yes_f, ask_no, no_f):
        one = Decimal("1")
        return (
            one - ask_yes - ask_no
            - yes_f.taker_rate() * ask_yes * (one - ask_yes)
            - no_f.taker_rate() * ask_no * (one - ask_no)
        )

    k_yes = edge(ka, kf, Decimal("1") - pb, pf)
    p_yes = edge(pa, pf, Decimal("1") - kb, kf)
    assert item.fee_adjusted_edge == max(k_yes, p_yes)
    expected = (
        "buy_yes_kalshi_no_polymarket" if k_yes >= p_yes else "buy_yes_polymarket_no_kalshi"
    )
    assert item.direction == expected
    curve = walk_lock(k_book, p_book, kf, pf)
    assert curve.direction == item.direction


def test_fractional_depth_floors_max_lock_size():
    # PM bid depth 12.75 shares vs Kalshi ask 30: min is 12.75, floored to 12
    # whole contracts (the always-executable unit); zero fees keep edge 0.06.
    item = compute_pair(
        pair(),
        book("kalshi", bids=[("0.44", "30")], asks=[("0.46", "30")]),
        book("polymarket", bids=[("0.52", "12.75")], asks=[("0.54", "200")]),
        NOW,
        kalshi_fees=NullFees(),
        pm_fees=NullFees(),
    )
    assert item.max_lock_size == Decimal("12")
    assert item.edge_at_size == Decimal("0.06")


def test_sub_contract_depth_has_no_edge_at_size():
    # 0.4 shares of PM depth cannot fill one whole contract — no size, no
    # edge_at_size; fee_adjusted_edge (a per-contract rate) still reported
    item = compute_pair(
        pair(),
        book("kalshi", bids=[("0.44", "30")], asks=[("0.46", "30")]),
        book("polymarket", bids=[("0.52", "0.4")], asks=[("0.54", "200")]),
        NOW,
        kalshi_fees=NullFees(),
        pm_fees=NullFees(),
    )
    assert item.max_lock_size == Decimal("0")
    assert item.edge_at_size is None
    assert item.fee_adjusted_edge == Decimal("0.06")


def test_missing_fee_category_flags_worst_case():
    item = compute_pair(
        pair(pm_fee_category=None),
        book("kalshi", bids=[("0.44", "100")], asks=[("0.46", "100")]),
        book("polymarket", bids=[("0.52", "200")], asks=[("0.54", "200")]),
        NOW,
    )
    assert item.fee_assumed_worst_case is True
