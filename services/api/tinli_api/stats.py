"""Basis statistics over the recorded history window.

Descriptive stats (mean, sample stdev, z of the latest print) plus an AR(1)
mean-reversion half-life for the cross-venue basis:

    x_t = c + phi * x_{t-1} + eps      (OLS with intercept)
    half_life = ln(1/2) / ln(phi) sampling intervals, phi in (0, 1)

Honesty guards — a statistic is None rather than wrong:
- mean/stdev need n >= 2; z needs stdev > 0.
- half-life needs n >= HALF_LIFE_MIN_N observations AND an estimated phi
  strictly inside (0, 1). Outside that range the series shows no measurable
  mean reversion in-window (trending or oscillating) and printing a
  half-life would be fiction.
- Snapshots are not perfectly evenly spaced; intervals are converted to
  hours via the MEDIAN sampling interval. This is stated in the UI as an
  approximation, not hidden.

Rounding follows the house rule (round against the signal, never for it):
z is quantized TOWARD ZERO (never inflate |z|), half-life is quantized UP
(never claim faster reversion than measured). Mean/stdev are descriptive
and use default half-even.
"""

from datetime import datetime
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal

from pydantic import BaseModel, Field

FOUR_DP = Decimal("0.0001")
TWO_DP = Decimal("0.01")
HALF = Decimal("0.5")
HALF_LIFE_MIN_N = 30  # below this an AR(1) fit is numerology, not a statistic


class BasisStats(BaseModel):
    n: int = Field(description="observations with a computable basis in the window")
    mean_cents: Decimal | None
    stdev_cents: Decimal | None = Field(
        default=None, description="sample standard deviation (n-1)"
    )
    z_last: Decimal | None = Field(
        default=None,
        description="(latest - mean) / stdev, quantized toward zero",
    )
    ar1_phi: Decimal | None = Field(
        default=None,
        description="AR(1) coefficient, only reported when half_life_hours is",
    )
    half_life_hours: Decimal | None = Field(
        default=None,
        description=f"ln(1/2)/ln(phi) x median sampling interval; None unless "
        f"n >= {HALF_LIFE_MIN_N} and phi is inside (0, 1)",
    )


def _median_interval_hours(ts: list[datetime]) -> Decimal | None:
    if len(ts) < 2:
        return None
    gaps = sorted(
        Decimal(int((b - a).total_seconds())) for a, b in zip(ts, ts[1:])
    )
    mid = len(gaps) // 2
    med_s = gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2
    if med_s <= 0:
        return None
    return med_s / Decimal("3600")


def basis_stats(rows: list[tuple[datetime, Decimal | None]]) -> BasisStats:
    """rows: (ts, raw_basis_cents) in ascending time order, None basis allowed."""
    obs = [(t, x) for t, x in rows if x is not None]
    n = len(obs)
    if n < 2:
        return BasisStats(n=n, mean_cents=obs[0][1].quantize(FOUR_DP) if n else None)

    xs = [x for _, x in obs]
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    stdev = var.sqrt()

    z = None
    if stdev > 0:
        z = ((xs[-1] - mean) / stdev).quantize(TWO_DP, rounding=ROUND_DOWN)

    phi_out = None
    half_life = None
    med_h = _median_interval_hours([t for t, _ in obs])
    if n >= HALF_LIFE_MIN_N and stdev > 0 and med_h is not None:
        # OLS with intercept on (x_{t-1}, x_t): phi = cov / var of the lagged
        # series, computed with exact Decimal sums
        lag, cur = xs[:-1], xs[1:]
        m = len(lag)
        s_l = sum(lag)
        s_c = sum(cur)
        s_ll = sum(a * a for a in lag)
        s_lc = sum(a * b for a, b in zip(lag, cur))
        den = m * s_ll - s_l * s_l
        if den != 0:
            phi = (m * s_lc - s_l * s_c) / den
            if 0 < phi < 1:
                intervals = HALF.ln() / phi.ln()
                half_life = (intervals * med_h).quantize(
                    TWO_DP, rounding=ROUND_CEILING
                )
                phi_out = phi.quantize(FOUR_DP)

    return BasisStats(
        n=n,
        mean_cents=mean.quantize(FOUR_DP),
        stdev_cents=stdev.quantize(FOUR_DP),
        z_last=z,
        ar1_phi=phi_out,
        half_life_hours=half_life,
    )
