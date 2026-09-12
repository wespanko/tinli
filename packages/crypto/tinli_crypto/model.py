"""Digital-option fair value off a listed vol surface.

A Kalshi "BTC above K at time T" contract pays $1 if S_T > K: a cash-or-
nothing digital call. Under lognormal dynamics with forward F and
implied vol sigma for expiry T:

    fair = e^(-rT) * N(d2),   d2 = (ln(F/K) - sigma^2 T / 2) / (sigma sqrt(T))

The surface comes from Deribit mark IVs. Interpolation, in this order:
  1. within each listed expiry, IV is linear in strike between the two
     listed strikes bracketing K (flat beyond the listed range);
  2. across expiries, TOTAL VARIANCE (sigma^2 T) is linear in T between
     the two listed expiries bracketing the Kalshi expiry; before the
     first listed expiry, variance scales linearly from zero (flat vol);
  3. the forward is linear in T between (0, index) and the listed
     expiries' underlying prices.

FLOAT NOTICE. This module is MODEL space, not money: log, sqrt and the
normal CDF need floats. The result crosses back into Decimal at exactly
one boundary (`digital_fair_value`) and is quantized to 4 dp with
ROUND_HALF_EVEN — a fair value is an estimate with no "safe" side; the
engine rounds the EDGE against the user, not the estimate. Money math
(fees, edges, hedge costs) never touches this file.
"""

import math
from dataclasses import dataclass
from decimal import Decimal

FOUR_DP = Decimal("0.0001")
SECONDS_PER_YEAR = 365.0 * 86400.0


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def digital_call(forward: float, strike: float, sigma: float, t_years: float, rate: float) -> float:
    """e^(-rT) N(d2). Degenerate inputs resolve to the intrinsic value."""
    if t_years <= 0 or sigma <= 0:
        return math.exp(-rate * max(t_years, 0.0)) * (1.0 if forward > strike else 0.0)
    d2 = (math.log(forward / strike) - 0.5 * sigma * sigma * t_years) / (sigma * math.sqrt(t_years))
    return math.exp(-rate * t_years) * norm_cdf(d2)


@dataclass(frozen=True)
class ExpirySlice:
    """One listed expiry: strikes with their mark IVs (annualized, as a
    fraction, e.g. 0.45) and the venue's underlying/forward price."""

    t_years: float
    forward: float
    strikes: tuple[float, ...]  # ascending
    ivs: tuple[float, ...]

    def iv_at(self, strike: float) -> float:
        ks, vs = self.strikes, self.ivs
        if not ks:
            raise ValueError("empty expiry slice")
        if strike <= ks[0]:
            return vs[0]
        if strike >= ks[-1]:
            return vs[-1]
        for i in range(1, len(ks)):
            if strike <= ks[i]:
                w = (strike - ks[i - 1]) / (ks[i] - ks[i - 1])
                return vs[i - 1] + w * (vs[i] - vs[i - 1])
        return vs[-1]  # unreachable: covered by the >= ks[-1] guard


@dataclass(frozen=True)
class Surface:
    index: float
    slices: tuple[ExpirySlice, ...]  # ascending in t_years, all t > 0

    def _bracket(self, t: float) -> tuple[ExpirySlice | None, ExpirySlice | None]:
        lo: ExpirySlice | None = None
        for s in self.slices:
            if s.t_years >= t:
                return lo, s
            lo = s
        return lo, None

    def forward_at(self, t: float) -> float:
        lo, hi = self._bracket(t)
        if hi is None:
            return lo.forward if lo else self.index
        t0, f0 = (lo.t_years, lo.forward) if lo else (0.0, self.index)
        if hi.t_years == t0:
            return hi.forward
        return f0 + (hi.forward - f0) * (t - t0) / (hi.t_years - t0)

    def iv_at(self, strike: float, t: float) -> float:
        """Total variance linear in T between bracketing expiries; flat vol
        before the first listed expiry and after the last."""
        lo, hi = self._bracket(t)
        if hi is None:
            return lo.iv_at(strike) if lo else float("nan")
        if lo is None:
            return hi.iv_at(strike)
        w_lo = lo.iv_at(strike) ** 2 * lo.t_years
        w_hi = hi.iv_at(strike) ** 2 * hi.t_years
        if hi.t_years == lo.t_years:
            return hi.iv_at(strike)
        w = w_lo + (w_hi - w_lo) * (t - lo.t_years) / (hi.t_years - lo.t_years)
        return math.sqrt(max(w, 0.0) / t) if t > 0 else hi.iv_at(strike)


def digital_fair_value(surface: Surface, strike: Decimal, t_years: float, rate: Decimal) -> tuple[Decimal, Decimal]:
    """(fair value in dollars per $1 contract, interpolated IV as a fraction)
    — the single float -> Decimal boundary of the model."""
    if not surface.slices:
        raise ValueError("surface has no expiries")
    k = float(strike)
    sigma = surface.iv_at(k, t_years)
    fwd = surface.forward_at(t_years)
    fv = digital_call(fwd, k, sigma, t_years, float(rate))
    return Decimal(repr(fv)).quantize(FOUR_DP), Decimal(repr(sigma)).quantize(FOUR_DP)
