"""Market data sources: live venue adapters or recorded fixtures (demo mode).

Both sources expose the same interface; routes never know which one they got.
Live results are TTL-cached so UI polling (3s) never hammers the venues.
"""

import json
import os
import threading
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import yaml
from cachetools import TTLCache

from tinli_schema import Market, Orderbook, PairMapping, Position

from tinli_api.venues import kalshi, polymarket

REPO_ROOT = Path(__file__).resolve().parents[3]
EVENT_MAP = REPO_ROOT / "data" / "event_map.yaml"
POSITIONS = REPO_ROOT / "data" / "positions.yaml"
FIXTURES = REPO_ROOT / "services" / "api" / "tests" / "fixtures"

CACHE_TTL_S = 2.0


@lru_cache(maxsize=1)
def load_pairs() -> tuple[PairMapping, ...]:
    raw = yaml.safe_load(EVENT_MAP.read_text(encoding="utf-8"))
    return tuple(PairMapping(**p) for p in raw["pairs"])


def load_positions() -> list[Position]:
    """Self-reported user positions. Deliberately NOT cached: users edit the
    file while the terminal runs, and it is tiny — re-read every request so
    changes show up on the next poll.

    Structural mistakes raise ValueError (not TypeError/AttributeError) so the
    route's 422 handler catches EVERY malformed shape of a hand-edited file:
    a bare `positions:` key is an empty book, not an error."""
    path = Path(os.environ.get("TINLI_POSITIONS", str(POSITIONS)))
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise ValueError("positions.yaml must be a mapping with a 'positions' list")
    entries = raw.get("positions") or []
    if not isinstance(entries, list):
        raise ValueError("'positions' must be a list")
    for i, p in enumerate(entries):
        if not isinstance(p, dict):
            raise ValueError(f"positions[{i}] must be a mapping of fields, got {type(p).__name__}")
    return [Position(**p) for p in entries]


def pair_for_market_id(market_id: str) -> PairMapping | None:
    for p in load_pairs():
        if market_id == f"kalshi:{p.kalshi_ticker}" or market_id == f"polymarket:{p.pm_condition_id}":
            return p
    return None


class DataSource(Protocol):
    def markets(self) -> list[Market]:
        """All markets referenced by the pair map, event_key filled in."""

    def orderbook(self, pair: PairMapping, venue: str) -> Orderbook: ...


def _tag(markets: list[Market], by_kalshi: dict[str, str], by_pm: dict[str, str]) -> list[Market]:
    tagged = []
    for m in markets:
        _, _, native = m.id.partition(":")
        key = by_kalshi.get(native) if m.venue == "kalshi" else by_pm.get(native)
        tagged.append(m.model_copy(update={"event_key": key}))
    return tagged


class LiveSource:
    def __init__(self) -> None:
        self._cache: TTLCache = TTLCache(maxsize=256, ttl=CACHE_TTL_S)
        # cachetools structures are not thread-safe; /v1/divergence fetches
        # books from a thread pool
        self._lock = threading.Lock()

    def markets(self) -> list[Market]:
        with self._lock:
            if "markets" in self._cache:
                return self._cache["markets"]
        pairs = load_pairs()
        by_kalshi = {p.kalshi_ticker: p.event_key for p in pairs}
        by_pm = {p.pm_condition_id: p.event_key for p in pairs}
        now = datetime.now(UTC)
        result = kalshi.get_markets(list(by_kalshi))
        gamma = polymarket.get_gamma_markets(list(by_pm))
        pm_yes = {p.pm_condition_id: p.pm_yes_token for p in pairs}
        for cid, gm in gamma.items():
            result.append(polymarket.parse_market(gm, pm_yes[cid], now))
        tagged = _tag(result, by_kalshi, by_pm)
        with self._lock:
            self._cache["markets"] = tagged
        return tagged

    def orderbook(self, pair: PairMapping, venue: str) -> Orderbook:
        key = ("book", venue, pair.event_key)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        if venue == "kalshi":
            book = kalshi.get_orderbook(pair.kalshi_ticker)
        else:
            gamma = polymarket.get_gamma_market(pair.pm_condition_id)
            token = polymarket.yes_token_id(gamma, pair.pm_yes_token)
            book = polymarket.get_orderbook(pair.pm_condition_id, token)
        with self._lock:
            self._cache[key] = book
        return book


class FixtureSource:
    """Serves the recorded fixtures. Never presented as live: /healthz says
    demo, and every fetched_at is the recording timestamp, not now()."""

    def __init__(self) -> None:
        manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
        self.recorded_at = datetime.fromisoformat(manifest["recorded_at"])

    def _load(self, rel: str) -> dict:
        return json.loads((FIXTURES / rel).read_text(encoding="utf-8"))

    def markets(self) -> list[Market]:
        pairs = load_pairs()
        by_kalshi = {p.kalshi_ticker: p.event_key for p in pairs}
        by_pm = {p.pm_condition_id: p.event_key for p in pairs}
        result = []
        for p in pairs:
            raw_k = self._load(f"kalshi/market_{p.kalshi_ticker}.json")["market"]
            result.append(kalshi.parse_market(raw_k, self.recorded_at))
            gamma = self._load(f"polymarket/gamma_{p.pm_condition_id}.json")
            raw_book = self._load(f"polymarket/book_{p.pm_condition_id}.json")
            book = polymarket.parse_book(p.pm_condition_id, raw_book, self.recorded_at)
            result.append(polymarket.parse_market(gamma, p.pm_yes_token, self.recorded_at, book=book))
        return _tag(result, by_kalshi, by_pm)

    def orderbook(self, pair: PairMapping, venue: str) -> Orderbook:
        if venue == "kalshi":
            raw = self._load(f"kalshi/orderbook_{pair.kalshi_ticker}.json")
            return kalshi.parse_orderbook(pair.kalshi_ticker, raw, self.recorded_at)
        raw = self._load(f"polymarket/book_{pair.pm_condition_id}.json")
        return polymarket.parse_book(pair.pm_condition_id, raw, self.recorded_at)


_source: DataSource | None = None


def get_source() -> DataSource:
    global _source
    if _source is None:
        demo = os.environ.get("TINLI_DEMO", "0") == "1"
        _source = FixtureSource() if demo else LiveSource()
    return _source


def reset_source() -> None:
    """Test hook: drop the cached source so TINLI_DEMO is re-read."""
    global _source
    _source = None
