"""Hand-computed basis-stats cases. Every expected number is derived in the
comments — if a test fails, redo the arithmetic before touching stats.py."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tinli_api.stats import HALF_LIFE_MIN_N, basis_stats

T0 = datetime(2026, 7, 18, tzinfo=UTC)


def hourly(values):
    """(ts, basis) rows spaced exactly 1h apart."""
    return [(T0 + timedelta(hours=i), Decimal(str(v)) if v is not None else None)
            for i, v in enumerate(values)]


def test_mean_stdev_z_by_hand():
    # values 1, 2, 3, 6: mean = 12/4 = 3.
    # sample var = ((-2)^2 + (-1)^2 + 0 + 3^2) / 3 = 14/3 = 4.6667
    # stdev = sqrt(14/3) = 2.160246899...
    # z_last = (6-3)/2.160246899 = 1.38873... -> toward zero 2dp = 1.38
    s = basis_stats(hourly([1, 2, 3, 6]))
    assert s.n == 4
    assert s.mean_cents == Decimal("3.0000")
    assert s.stdev_cents == Decimal("2.1602")
    assert s.z_last == Decimal("1.38")
    # n=4 < 30: no half-life, no matter how clean the series
    assert s.half_life_hours is None and s.ar1_phi is None


def test_none_basis_rows_are_excluded_not_zeroed():
    s = basis_stats(hourly([1, None, 2, None, 3, 6]))
    assert s.n == 4
    assert s.mean_cents == Decimal("3.0000")


def test_too_few_observations():
    assert basis_stats([]).n == 0
    one = basis_stats(hourly([5]))
    assert one.n == 1
    assert one.mean_cents == Decimal("5.0000")
    assert one.stdev_cents is None and one.z_last is None


def test_constant_series_has_no_z_and_no_half_life():
    s = basis_stats(hourly([2] * (HALF_LIFE_MIN_N + 5)))
    assert s.stdev_cents == Decimal("0.0000")
    assert s.z_last is None
    assert s.half_life_hours is None


def test_half_life_exact_on_noiseless_ar1():
    # x_{t+1} = 0.5 * x_t from 64: perfect AR(1), so OLS-with-intercept
    # recovers phi = 0.5 EXACTLY (every product/sum is an exact Decimal and
    # numerator = 0.5 * denominator by construction).
    # half-life = ln(0.5)/ln(0.5) = 1 interval x 1h spacing = 1.00 h.
    xs = [Decimal(64) * Decimal("0.5") ** i for i in range(HALF_LIFE_MIN_N + 2)]
    s = basis_stats([(T0 + timedelta(hours=i), x) for i, x in enumerate(xs)])
    assert s.ar1_phi == Decimal("0.5000")
    assert s.half_life_hours == Decimal("1.00")


def test_half_life_nonzero_mean_decay():
    # x_{t+1} = 10 + 0.8*(x_t - 10) from 20: phi = 0.8 exactly (noiseless).
    # half-life = ln(0.5)/ln(0.8) = (-0.6931472)/(-0.2231436) = 3.10628...
    # intervals; x 1h, quantized UP at 2dp -> 3.11 (never claim faster
    # reversion than measured).
    x = Decimal(20)
    xs = []
    for _ in range(HALF_LIFE_MIN_N + 10):
        xs.append(x)
        x = Decimal(10) + Decimal("0.8") * (x - Decimal(10))
    s = basis_stats([(T0 + timedelta(hours=i), v) for i, v in enumerate(xs)])
    assert s.ar1_phi == Decimal("0.8000")
    assert s.half_life_hours == Decimal("3.11")


def test_trending_series_refuses_half_life():
    # x_t = t: phi = 1 exactly (unit root) — no mean reversion to report.
    s = basis_stats(hourly(list(range(HALF_LIFE_MIN_N + 10))))
    assert s.half_life_hours is None and s.ar1_phi is None


def test_oscillating_series_refuses_half_life():
    # alternating +5/-5: phi = -1 — anti-persistent, not OU-style reversion.
    vals = [5 if i % 2 == 0 else -5 for i in range(HALF_LIFE_MIN_N + 10)]
    s = basis_stats(hourly(vals))
    assert s.half_life_hours is None and s.ar1_phi is None


def test_median_interval_scales_half_life():
    # same 0.5-decay series but 30-MINUTE spacing: 1 interval = 0.50 h.
    xs = [Decimal(64) * Decimal("0.5") ** i for i in range(HALF_LIFE_MIN_N + 2)]
    rows = [(T0 + timedelta(minutes=30 * i), x) for i, x in enumerate(xs)]
    assert basis_stats(rows).half_life_hours == Decimal("0.50")
