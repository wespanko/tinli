"""Digital pricing + surface interpolation against hand-computed values."""

import math
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from tinli_crypto.model import ExpirySlice, Surface, digital_call, digital_fair_value, norm_cdf


def test_norm_cdf_known_points():
    assert abs(norm_cdf(0.0) - 0.5) < 1e-12
    assert abs(norm_cdf(1.0) - 0.841345) < 1e-6
    assert abs(norm_cdf(-1.0) - 0.158655) < 1e-6


def test_digital_atm_one_year():
    # F=K=100, sigma=0.5, T=1, r=0: d2 = (0 - 0.125)/0.5 = -0.25, N(-0.25) = 0.401294
    assert abs(digital_call(100, 100, 0.5, 1.0, 0.0) - 0.401294) < 1e-6


def test_digital_itm_quarter():
    # F=100, K=90, sigma=0.2, T=0.25: ln(100/90)=0.1053605, sigma^2 T/2=0.005,
    # d2 = 0.1003605 / 0.1 = 1.003605, N(1.003605) = 0.842217 (N(1)=0.841345 + phi(1)*0.003605)
    assert abs(digital_call(100, 90, 0.2, 0.25, 0.0) - 0.842217) < 2e-5


def test_digital_discounting():
    # r=0.04, T=0.5: multiply by e^-0.02
    undiscounted = digital_call(100, 100, 0.5, 0.5, 0.0)
    assert abs(digital_call(100, 100, 0.5, 0.5, 0.04) - undiscounted * math.exp(-0.02)) < 1e-12


def test_digital_expired_is_intrinsic():
    assert digital_call(101, 100, 0.5, 0.0, 0.0) == 1.0
    assert digital_call(99, 100, 0.5, 0.0, 0.0) == 0.0


@settings(max_examples=200)
@given(
    f=st.floats(50, 200),
    sigma=st.floats(0.05, 2.0),
    t=st.floats(0.001, 3.0),
    k1=st.floats(50, 200),
    k2=st.floats(50, 200),
)
def test_digital_monotone_decreasing_in_strike(f, sigma, t, k1, k2):
    lo, hi = sorted((k1, k2))
    assert digital_call(f, lo, sigma, t, 0.0) >= digital_call(f, hi, sigma, t, 0.0) - 1e-12


def test_slice_iv_interpolates_linearly_and_extrapolates_flat():
    s = ExpirySlice(t_years=1.0, forward=100.0, strikes=(90.0, 100.0, 110.0), ivs=(0.6, 0.5, 0.55))
    assert s.iv_at(95.0) == 0.55
    assert s.iv_at(80.0) == 0.6
    assert s.iv_at(120.0) == 0.55
    assert s.iv_at(100.0) == 0.5


def test_surface_total_variance_interpolation():
    # w1 = 0.2^2 * 1 = 0.04, w2 = 0.4^2 * 2 = 0.32; at t=1.5: w = 0.18 -> iv = sqrt(0.12)
    s1 = ExpirySlice(t_years=1.0, forward=100.0, strikes=(100.0,), ivs=(0.2,))
    s2 = ExpirySlice(t_years=2.0, forward=104.0, strikes=(100.0,), ivs=(0.4,))
    surf = Surface(index=98.0, slices=(s1, s2))
    assert abs(surf.iv_at(100.0, 1.5) - math.sqrt(0.12)) < 1e-12
    # before the first expiry: flat vol from the first slice
    assert abs(surf.iv_at(100.0, 0.5) - 0.2) < 1e-12
    # forward: linear from (0, index) to (1, 100) to (2, 104)
    assert abs(surf.forward_at(0.5) - 99.0) < 1e-12
    assert abs(surf.forward_at(1.5) - 102.0) < 1e-12
    assert abs(surf.forward_at(3.0) - 104.0) < 1e-12


def test_fair_value_decimal_boundary():
    s1 = ExpirySlice(t_years=1.0, forward=100.0, strikes=(100.0,), ivs=(0.5,))
    surf = Surface(index=100.0, slices=(s1,))
    fv, iv = digital_fair_value(surf, Decimal("100"), 1.0, Decimal("0"))
    assert fv == Decimal("0.4013")
    assert iv == Decimal("0.5000")
