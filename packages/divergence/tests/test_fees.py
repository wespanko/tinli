from decimal import Decimal

import pytest

from tinli_divergence import KalshiFees, PolymarketFees


def test_kalshi_fee_rounds_up_to_next_cent():
    # 0.07 x 1 x 0.50 x 0.50 = 0.0175 -> ceil to cent = 0.02
    assert KalshiFees().taker_fee(Decimal("0.50"), Decimal("1")) == Decimal("0.02")


def test_kalshi_fee_exact_cent_not_rounded_further():
    # 0.07 x 100 x 0.50 x 0.50 = 1.75 exactly -> stays 1.75
    assert KalshiFees().taker_fee(Decimal("0.50"), Decimal("100")) == Decimal("1.75")


def test_kalshi_fee_at_extreme_price_still_ceils():
    # 0.07 x 1 x 0.01 x 0.99 = 0.000693 -> ceil to cent = 0.01
    assert KalshiFees().taker_fee(Decimal("0.01"), Decimal("1")) == Decimal("0.01")


def test_pm_sports_rate():
    # 100 x 0.03 x 0.50 x 0.50 = 0.75 exactly
    assert PolymarketFees("sports").taker_fee(Decimal("0.50"), Decimal("100")) == Decimal("0.75")


def test_pm_rounds_to_five_decimals():
    # 1 x 0.03 x 0.333 x 0.667 = 0.006663333 -> 5dp half-up = 0.00666
    assert PolymarketFees("sports").taker_fee(Decimal("0.333"), Decimal("1")) == Decimal("0.00666")


def test_pm_minimum_fee_applies():
    # 0.01 x 0.03 x 0.0001 x 0.9999 ~= 3e-8 -> would round to 0; docs say
    # the smallest charged fee is 0.00001 USDC
    assert PolymarketFees("sports").taker_fee(Decimal("0.0001"), Decimal("0.01")) == Decimal(
        "0.00001"
    )


def test_pm_geopolitical_is_free():
    assert PolymarketFees("geopolitical").taker_fee(Decimal("0.50"), Decimal("1000")) == 0


def test_pm_missing_category_assumes_worst_case():
    fees = PolymarketFees(None)
    assert fees.assumed_worst_case is True
    assert fees.taker_rate() == Decimal("0.07")  # crypto rate = max on schedule


def test_pm_unknown_category_is_an_error():
    with pytest.raises(KeyError):
        PolymarketFees("horoscopes")
