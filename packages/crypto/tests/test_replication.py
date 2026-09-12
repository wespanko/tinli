"""Spread bounds and Deribit fees against hand-computed values.

Index 70,000 USD. Taker fee per leg = min(0.0003, 12.5% of premium) coin;
delivery fee = min(0.00015, 12.5% of premium) coin. At these premiums the
caps never bind: each leg costs (0.0003 + 0.00015) x 70,000 = 31.50 USD.
"""

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from tinli_crypto.fees import delivery_fee_usd, round_trip_leg_fee_usd, taker_fee_usd
from tinli_crypto.replication import CallQuote, hedge_bounds, sub_replication, super_replication

INDEX = Decimal("70000")
QUOTES = [
    CallQuote("C69", Decimal("69000"), Decimal("0.06"), Decimal("0.065")),
    CallQuote("C70", Decimal("70000"), Decimal("0.045"), Decimal("0.05")),
    CallQuote("C71", Decimal("71000"), Decimal("0.04"), Decimal("0.042")),
    CallQuote("C72", Decimal("72000"), Decimal("0.03"), Decimal("0.035")),
]


def test_fee_formulas():
    assert taker_fee_usd(Decimal("0.05"), INDEX, Decimal(1)) == Decimal("21.00")
    assert delivery_fee_usd(Decimal("0.05"), INDEX, Decimal(1)) == Decimal("10.50")
    # cap binds: premium 0.001 coin -> taker 0.000125, delivery 0.000125 -> 8.75 each
    assert taker_fee_usd(Decimal("0.001"), INDEX, Decimal(1)) == Decimal("8.75")
    assert round_trip_leg_fee_usd(Decimal("0.001"), INDEX, Decimal(1)) == Decimal("17.50")


def test_super_replication_at_listed_strike():
    # K = 71,000: spread (70k, 71k). Cost = ask(70k) - bid(71k) = 0.05 - 0.04 = 0.01 coin = 700 USD.
    # Fees 31.50 x 2 = 63. Per $1 (width 1000): (700 + 63) / 1000 = 0.763.
    b = super_replication(QUOTES, Decimal("71000"), INDEX)
    assert b is not None
    assert (b.lo.instrument, b.hi.instrument) == ("C70", "C71")
    assert b.width == Decimal("1000")
    assert b.per_dollar == Decimal("0.763000")
    assert b.fees_per_dollar == Decimal("0.063000")


def test_sub_replication_at_listed_strike():
    # K = 71,000: spread (71k, 72k). Proceeds = bid(71k) - ask(72k) = 0.04 - 0.035 = 0.005 = 350 USD.
    # Fees 63 -> (350 - 63) / 1000 = 0.287.
    b = sub_replication(QUOTES, Decimal("71000"), INDEX)
    assert b is not None
    assert (b.lo.instrument, b.hi.instrument) == ("C71", "C72")
    assert b.per_dollar == Decimal("0.287000")


def test_bounds_between_listed_strikes():
    # K = 70,500: super uses (69k, 70k) — both <= K; sub uses (71k, 72k)
    hb = hedge_bounds(QUOTES, Decimal("70500"), INDEX)
    assert hb.ask is not None and (hb.ask.lo.instrument, hb.ask.hi.instrument) == ("C69", "C70")
    assert hb.bid is not None and (hb.bid.lo.instrument, hb.bid.hi.instrument) == ("C71", "C72")
    assert hb.ask.per_dollar >= hb.bid.per_dollar


def test_missing_quote_side_means_no_bound():
    # super at K=71k needs ask(70k) and bid(71k); sub needs bid(71k) and ask(72k).
    # A missing bid(70k) is irrelevant to both:
    qs = [CallQuote("C70", Decimal("70000"), None, Decimal("0.05")), QUOTES[2], QUOTES[3]]
    assert super_replication(qs, Decimal("71000"), INDEX) is not None
    # a missing bid(71k) kills both
    qs2 = [QUOTES[1], CallQuote("C71", Decimal("71000"), None, Decimal("0.042")), QUOTES[3]]
    assert super_replication(qs2, Decimal("71000"), INDEX) is None
    assert sub_replication(qs2, Decimal("71000"), INDEX) is None


def test_too_few_strikes_means_no_bound():
    assert super_replication(QUOTES[:1], Decimal("71000"), INDEX) is None
    assert sub_replication(QUOTES[-1:], Decimal("71000"), INDEX) is None


@settings(max_examples=100)
@given(
    diffs=st.lists(st.floats(0.0, 0.05), min_size=3, max_size=3),
    base=st.floats(0.001, 0.05),
    spread=st.floats(0.0, 0.01),
)
def test_super_bound_never_below_sub_bound_on_convex_chain(diffs, base, spread):
    # An arbitrage-free call curve is decreasing and CONVEX in strike: the
    # spread (Ka,Kb) below K is worth at least the spread (Kc,Kd) above it.
    # Build one from descending increments; fees only widen the gap.
    d0, d1, d2 = sorted(diffs, reverse=True)
    mids = [base + d2 + d1 + d0, base + d2 + d1, base + d2, base]
    half = Decimal(repr(spread / 2))
    qs = [
        CallQuote(f"C{i}", Decimal(69000 + 1000 * i), Decimal(repr(m)) - half, Decimal(repr(m)) + half)
        for i, m in enumerate(mids)
    ]
    hb = hedge_bounds(qs, Decimal("70000"), INDEX)
    assert hb.ask is not None and hb.bid is not None
    assert hb.ask.per_dollar >= hb.bid.per_dollar
