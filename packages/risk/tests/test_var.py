"""Hand-computed VaR cases. Every expected number is derived in a comment —
if one fails, redo the arithmetic before touching the engine."""

from decimal import Decimal

from tinli_risk import EventPnl, max_loss, monte_carlo_var, parametric_var

D = Decimal


def ev(key: str, p: str, if_yes: str, if_no: str) -> EventPnl:
    return EventPnl(event_id=key, prob_yes=D(p), delta_if_yes=D(if_yes), delta_if_no=D(if_no))


def test_empty_book_is_zero_risk():
    assert parametric_var([]) == 0
    assert monte_carlo_var([]) == 0
    assert max_loss([]) == 0


def test_max_loss_sums_worst_side_per_event():
    # min(50,-50) = -50; min(-20,30) = -20; total -70 -> 70.00
    events = [ev("a", "0.5", "50", "-50"), ev("b", "0.4", "-20", "30")]
    assert max_loss(events) == D("70.00")


def test_parametric_single_coin_flip_capped_at_max_loss():
    # p=0.5, W=50, L=-50: mu=0, sigma = sqrt(0.25*100^2) = 50
    # normal read-off: 1.6449*50 = 82.245 — MORE than the 50 you can lose.
    # The cap (documented assumption 4) must bring it back to 50.00.
    events = [ev("a", "0.5", "50", "-50")]
    assert parametric_var(events) == D("50.00")


def test_parametric_hand_computed_uncapped():
    # p=0.9, W=10, L=-90: mu = 0.9*10 + 0.1*(-90) = 0
    # sigma^2 = 0.09 * (10-(-90))^2 = 900, sigma = 30
    # VaR = 1.6449*30 = 49.347 -> ceil to cent 49.35; max_loss 90 (no cap)
    events = [ev("a", "0.9", "10", "-90")]
    assert parametric_var(events) == D("49.35")


def test_monte_carlo_single_coin_flip_is_the_full_loss():
    # With p=0.5 the 5th percentile outcome is the losing branch: -50.
    events = [ev("a", "0.5", "50", "-50")]
    assert monte_carlo_var(events) == D("50.00")


def test_monte_carlo_reproducible_for_fixed_seed():
    events = [ev("a", "0.62", "38", "-62"), ev("b", "0.3", "70", "-30")]
    assert monte_carlo_var(events, seed=7) == monte_carlo_var(events, seed=7)


def test_monte_carlo_approaches_parametric_in_clt_regime():
    # 100 iid coin flips of +/-10 is where the normal approximation is honest:
    # sigma = sqrt(100*0.25*400) = 100, parametric = 164.49. The binomial 5th
    # percentile is ~ -164; with 30 flips the +/-20 P&L steps are too coarse
    # relative to the quantile and discreteness alone breaks 10% agreement.
    events = [ev(f"e{i}", "0.5", "10", "-10") for i in range(100)]
    param = parametric_var(events)
    mc = monte_carlo_var(events, draws=50_000)
    assert abs(mc - param) / param < D("0.10")


def test_locked_book_has_zero_var():
    # Same P&L either way (a cross-venue lock): nothing at risk.
    events = [ev("lock", "0.51", "2", "2")]
    assert max_loss(events) == 0
    assert parametric_var(events) == 0
    assert monte_carlo_var(events) == 0
