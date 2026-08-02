"""Tinli research layer: edge episodes, lock backtest, cross-venue lead-lag."""

from tinli_backtest.episodes import Episode, Tick, extract_episodes
from tinli_backtest.events import (
    DayEdges,
    Reprice,
    VenueEventWindow,
    daily_edge_summary,
    find_reprice,
    venue_event_window,
)
from tinli_backtest.leadlag import LeadLag, MidSeries, build_series, lead_follow
from tinli_backtest.locks import ASSUMPTIONS, LockTrade, backtest

__version__ = "0.1.0"
__all__ = [
    "ASSUMPTIONS", "DayEdges", "Episode", "LeadLag", "LockTrade", "MidSeries",
    "Reprice", "Tick", "VenueEventWindow", "backtest", "build_series",
    "daily_edge_summary", "extract_episodes", "find_reprice", "lead_follow",
    "venue_event_window",
]
