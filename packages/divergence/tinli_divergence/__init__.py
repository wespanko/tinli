"""Cross-venue divergence engine. Sign convention and lock construction
are documented once, in tinli_divergence.engine's module docstring."""

from tinli_divergence.engine import DivergenceItem, VenueTop, compute_pair, sort_items, top
from tinli_divergence.fees import (
    PM_CATEGORY_RATES,
    FeeModel,
    KalshiFees,
    NullFees,
    PolymarketFees,
)

__version__ = "0.1.0"
__all__ = [
    "DivergenceItem",
    "VenueTop",
    "compute_pair",
    "sort_items",
    "top",
    "FeeModel",
    "KalshiFees",
    "PolymarketFees",
    "NullFees",
    "PM_CATEGORY_RATES",
]
