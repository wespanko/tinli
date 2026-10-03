from decimal import Decimal

from tinli_risk import half_kelly, kelly_contracts, kelly_fraction

D = Decimal


def test_hand_computed_fraction():
    # f* = (p - c)/(1 - c) = (0.6 - 0.5)/0.5 = 0.2
    assert kelly_fraction(D("0.5"), D("0.6")) == D("0.2")
    assert half_kelly(D("0.5"), D("0.6")) == D("0.1")


def test_no_edge_means_no_bet():
    assert kelly_fraction(D("0.5"), D("0.5")) == 0
    assert kelly_fraction(D("0.7"), D("0.55")) == 0


def test_certainty_clips_to_full_bankroll():
    assert kelly_fraction(D("0.5"), D("1")) == 1


def test_degenerate_prices_are_none():
    assert kelly_fraction(D("0"), D("0.5")) is None
    assert kelly_fraction(D("1"), D("0.5")) is None


def test_contracts_for_bankroll_floor():
    # f = (0.6 - 0.44)/0.56 = 0.285714.. -> 0.2857; stake 285.70 on $1000;
    # 285.70 / 0.44 = 649.3 -> 649 contracts
    f = kelly_fraction(D("0.44"), D("0.6"))
    assert f == D("0.2857")
    assert kelly_contracts(f, D("1000"), D("0.44")) == D("649")
    assert kelly_contracts(D("0"), D("1000"), D("0.44")) == D("0")
    assert kelly_contracts(None, D("1000"), D("0.44")) is None
