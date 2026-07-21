"""Tinli research layer: edge episodes, lock backtest, cross-venue lead-lag."""

from tinli_backtest.episodes import Episode, Tick, extract_episodes
from tinli_backtest.leadlag import LeadLag, MidSeries, build_series, lead_follow
from tinli_backtest.locks import ASSUMPTIONS, LockTrade, backtest

__version__ = "0.1.0"
__all__ = [
    "ASSUMPTIONS", "Episode", "LeadLag", "LockTrade", "MidSeries", "Tick",
    "backtest", "build_series", "extract_episodes", "lead_follow",
]
