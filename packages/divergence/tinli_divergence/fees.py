"""Per-venue taker fee models, implemented from each venue's PUBLISHED fee
schedule. Every constant here must be traceable to a source URL below —
if a fee is ambiguous, we flag it loudly instead of guessing silently.

All amounts are Decimal dollars; `price` is the traded contract's price in
[0, 1]; `contracts` is the fill size. Only TAKER fees are modeled: the
divergence lock crosses the spread on both legs by construction.
"""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Protocol

ONE = Decimal("1")
CENT = Decimal("0.01")


class FeeModel(Protocol):
    def taker_fee(self, price: Decimal, contracts: Decimal) -> Decimal:
        """Exact fee charged for a taker fill of `contracts` at `price`."""
        ...

    def taker_rate(self) -> Decimal:
        """Idealized per-contract rate multiplier r in fee = r*p*(1-p)."""
        ...


class KalshiFees:
    """Kalshi general trading fee.

    Source: https://kalshi.com/docs/kalshi-fee-schedule.pdf (also
    https://help.kalshi.com/en/articles/13823805-fees):
      trading_fee = ceil_to_next_cent(0.07 x contracts x P x (1-P))
    charged per fill, rounded UP to the next cent.

    TODO(loud): the monthly PDF lists per-series exceptions (some series have
    maker fees or non-standard rates). All currently mapped series (World Cup,
    Wimbledon, Fed decision) take the general 7% rate as of the June 2026
    schedule — RE-CHECK THE PDF when adding pairs from new series.
    """

    RATE = Decimal("0.07")

    def taker_rate(self) -> Decimal:
        return self.RATE

    def taker_fee(self, price: Decimal, contracts: Decimal) -> Decimal:
        raw = self.RATE * contracts * price * (ONE - price)
        return raw.quantize(CENT, rounding=ROUND_CEILING)


# Polymarket taker-fee rate by market category.
# Source: https://docs.polymarket.com/trading/fees — "Makers are never
# charged fees. Only takers pay fees.", fee = C x feeRate x p x (1-p),
# rounded to 5 decimal places, minimum charged fee 0.00001 USDC.
PM_CATEGORY_RATES: dict[str, Decimal] = {
    "crypto": Decimal("0.07"),
    "sports": Decimal("0.03"),
    "finance": Decimal("0.04"),
    "politics": Decimal("0.04"),
    "mentions": Decimal("0.04"),
    "tech": Decimal("0.04"),
    "economics": Decimal("0.05"),
    "culture": Decimal("0.05"),
    "weather": Decimal("0.05"),
    "other": Decimal("0.05"),
    "geopolitical": Decimal("0"),
}
# If a pair has no curated category we assume the WORST case rather than
# guess: the highest rate on the schedule.
PM_WORST_CASE_RATE = max(PM_CATEGORY_RATES.values())
FIVE_DP = Decimal("0.00001")


class PolymarketFees:
    def __init__(self, category: str | None) -> None:
        self.category = category
        self.assumed_worst_case = category is None
        if category is None:
            self.rate = PM_WORST_CASE_RATE
        else:
            self.rate = PM_CATEGORY_RATES[category]

    def taker_rate(self) -> Decimal:
        return self.rate

    def taker_fee(self, price: Decimal, contracts: Decimal) -> Decimal:
        raw = contracts * self.rate * price * (ONE - price)
        fee = raw.quantize(FIVE_DP, rounding=ROUND_HALF_UP)
        if raw > 0 and fee == 0:
            fee = FIVE_DP  # documented minimum charged fee
        return fee


class NullFees:
    """Zero-fee model for tests and hypothetical no-fee comparisons."""

    def taker_rate(self) -> Decimal:
        return Decimal("0")

    def taker_fee(self, price: Decimal, contracts: Decimal) -> Decimal:
        return Decimal("0")
