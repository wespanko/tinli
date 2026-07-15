"""Property-based tests (hypothesis) — invariants that must hold for ANY
book, not just the hand-computed ones."""

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from tinli_risk import EventPnl, kelly_fraction, max_loss, monte_carlo_var, parametric_var

probs = st.decimals(min_value="0", max_value="1", places=2, allow_nan=False, allow_infinity=False)
deltas = st.decimals(
    min_value="-500", max_value="500", places=2, allow_nan=False, allow_infinity=False
)


@st.composite
def event_books(draw, max_size=6):
    n = draw(st.integers(min_value=0, max_value=max_size))
    return [
        EventPnl(
            event_id=f"e{i}",
            prob_yes=draw(probs),
            delta_if_yes=draw(deltas),
            delta_if_no=draw(deltas),
        )
        for i in range(n)
    ]


@given(event_books())
def test_parametric_var_bounded_by_max_loss_and_nonnegative(events):
    var = parametric_var(events)
    assert 0 <= var <= max_loss(events)


@given(event_books(max_size=4))
@settings(max_examples=40, deadline=None)
def test_monte_carlo_var_bounded_by_max_loss_and_nonnegative(events):
    # exact bound: the cap inside monte_carlo_var absorbs float dust
    var = monte_carlo_var(events, draws=500)
    assert 0 <= var <= max_loss(events)


@given(event_books())
def test_risk_is_monotone_in_position_size(events):
    doubled = [
        EventPnl(
            event_id=e.event_id,
            prob_yes=e.prob_yes,
            delta_if_yes=e.delta_if_yes * 2,
            delta_if_no=e.delta_if_no * 2,
        )
        for e in events
    ]
    assert max_loss(doubled) == 2 * max_loss(events)  # exact: cents stay cents
    assert parametric_var(doubled) >= parametric_var(events)


@given(
    st.decimals(min_value="0.01", max_value="0.99", places=2, allow_nan=False),
    probs,
)
def test_kelly_is_a_fraction_and_zero_without_edge(price, p_win):
    f = kelly_fraction(price, p_win)
    assert f is not None
    assert 0 <= f <= 1
    if p_win <= price:
        assert f == 0


@given(st.decimals(min_value="0.01", max_value="0.99", places=2, allow_nan=False))
def test_kelly_monotone_in_conviction(price):
    fractions = [kelly_fraction(price, Decimal(p) / 100) for p in range(0, 101, 5)]
    assert fractions == sorted(fractions)
