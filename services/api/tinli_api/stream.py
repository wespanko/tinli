"""M8 live streaming: Polymarket websocket + Kalshi fast-poll into one
in-process cache, consumed by the /v1/stream SSE endpoint.

Venue asymmetry (recon 2026-07-20, docs/VENUES.md): Polymarket's CLOB
websocket is public — full book snapshot on subscribe, then absolute-size
deltas. Kalshi's websocket returns 401 without an API key, which v0's
no-auth constraint rules out, so Kalshi is fast-polled over REST instead
(BYOK later can upgrade it to its websocket).

The hub never blocks request handlers: websocket frames and poll results
land in plain dicts guarded by the event loop (single-threaded mutation),
and REST fallback paths (LiveSource) are untouched — if the hub dies, the
UI's polling mode still works.
"""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from decimal import Decimal

import websockets

from tinli_schema import Market, Orderbook, PairMapping

from tinli_api.datasource import load_pairs
from tinli_api.venues import kalshi, polymarket

log = logging.getLogger("tinli.stream")

PM_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
KALSHI_POLL_S = float(os.environ.get("TINLI_KALSHI_POLL_S", "2.0"))
GAMMA_REFRESH_S = 300.0
BACKOFF_MAX_S = 60.0

# a venue is DEGRADED when its freshest data is older than this; the UI
# shows the per-venue state from /v1/stream payloads
STALE_AFTER_S = 10.0


class PmBook:
    """Mutable YES-token book rebuilt from websocket frames.

    Levels are absolute: a price_change carries the NEW total size at that
    price (size 0 deletes the level). Sizes/prices stay Decimal end to end.
    """

    def __init__(self, condition_id: str) -> None:
        self.condition_id = condition_id
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.updated_at: datetime | None = None

    def apply_snapshot(self, frame: dict, at: datetime) -> None:
        self.bids = {Decimal(l["price"]): Decimal(l["size"]) for l in frame.get("bids") or []}
        self.asks = {Decimal(l["price"]): Decimal(l["size"]) for l in frame.get("asks") or []}
        self.updated_at = at

    def apply_change(self, side: str, price: str, size: str, at: datetime) -> None:
        levels = self.bids if side == "BUY" else self.asks
        p, s = Decimal(price), Decimal(size)
        if s == 0:
            levels.pop(p, None)
        else:
            levels[p] = s
        self.updated_at = at

    def to_orderbook(self) -> Orderbook:
        raw = {
            "bids": [{"price": str(p), "size": str(s)} for p, s in self.bids.items()],
            "asks": [{"price": str(p), "size": str(s)} for p, s in self.asks.items()],
        }
        # parse_book re-sorts to best-first, same as the REST path
        return polymarket.parse_book(self.condition_id, raw, self.updated_at or datetime.now(UTC))


class StreamHub:
    """Owns the venue tasks and the freshest data. One instance per process,
    started from the app lifespan in live mode only."""

    def __init__(self) -> None:
        self.pairs: tuple[PairMapping, ...] = load_pairs()
        self._pm_books: dict[str, PmBook] = {}  # condition_id -> book
        self._token_to_cid: dict[str, str] = {}
        self._kalshi_markets: dict[str, Market] = {}  # ticker -> market
        self._kalshi_books: dict[str, Orderbook] = {}  # ticker -> book
        self._gamma: dict[str, dict] = {}  # condition_id -> gamma metadata
        self.pm_last_ok: datetime | None = None
        self.kalshi_last_ok: datetime | None = None
        self.version = 0
        self._changed = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._pm_ws_loop(), name="pm-ws"),
            asyncio.create_task(self._kalshi_poll_loop(), name="kalshi-poll"),
            asyncio.create_task(self._gamma_refresh_loop(), name="gamma-refresh"),
        ]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    def _bump(self) -> None:
        self.version += 1
        self._changed.set()

    async def wait_for_change(self, timeout: float) -> None:
        """Return when new data lands or the timeout passes (SSE heartbeat)."""
        self._changed.clear()
        try:
            await asyncio.wait_for(self._changed.wait(), timeout)
        except TimeoutError:
            pass

    # -- Polymarket websocket ------------------------------------------------

    async def _pm_ws_loop(self) -> None:
        backoff = 1.0
        while True:
            try:
                await self._pm_ws_once()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("polymarket ws dropped: %s: %s", type(exc).__name__, exc)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_S)

    async def _pm_ws_once(self) -> None:
        tokens = {}
        for p in self.pairs:
            gamma = self._gamma.get(p.pm_condition_id)
            if gamma is not None:
                tokens[polymarket.yes_token_id(gamma, p.pm_yes_token)] = p.pm_condition_id
        if not tokens:
            # gamma metadata not fetched yet; try again shortly
            await asyncio.sleep(1)
            return
        self._token_to_cid = tokens
        ua = os.environ.get("TINLI_USER_AGENT", "tinli/0.1")
        async with websockets.connect(
            PM_WS_URL, additional_headers={"User-Agent": ua}, open_timeout=15
        ) as ws:
            await ws.send(json.dumps({"assets_ids": list(tokens), "type": "market"}))
            log.info("polymarket ws subscribed: %d tokens", len(tokens))
            async for raw in ws:
                self._handle_pm_frame(json.loads(raw))

    def _handle_pm_frame(self, frame) -> None:
        now = datetime.now(UTC)
        # the first frame after subscribe is a LIST of book snapshots
        events = frame if isinstance(frame, list) else [frame]
        touched = False
        for ev in events:
            kind = ev.get("event_type")
            if kind == "book":
                cid = self._token_to_cid.get(ev.get("asset_id", ""))
                if cid is None:
                    continue
                book = self._pm_books.setdefault(cid, PmBook(cid))
                book.apply_snapshot(ev, now)
                touched = True
            elif kind == "price_change":
                for ch in ev.get("price_changes") or []:
                    cid = self._token_to_cid.get(ch.get("asset_id", ""))
                    if cid is None:
                        continue  # the venue also streams the NO token's twin
                    book = self._pm_books.setdefault(cid, PmBook(cid))
                    book.apply_change(ch["side"], ch["price"], ch["size"], now)
                    touched = True
            # last_trade_price / tick_size_change: not needed for books
        if touched:
            self.pm_last_ok = now
            self._bump()

    # -- Kalshi fast-poll ----------------------------------------------------

    async def _kalshi_poll_loop(self) -> None:
        interval = KALSHI_POLL_S
        while True:
            try:
                await self._kalshi_poll_once()
                interval = KALSHI_POLL_S
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Kalshi 429s carry no Retry-After: back the interval off
                # exponentially and recover on the next success
                interval = min(interval * 2, BACKOFF_MAX_S)
                log.warning(
                    "kalshi poll failed (%s: %s); next in %.0fs", type(exc).__name__, exc, interval
                )
            await asyncio.sleep(interval)

    async def _kalshi_poll_once(self) -> None:
        tickers = [p.kalshi_ticker for p in self.pairs]
        markets = await asyncio.to_thread(kalshi.get_markets, tickers)
        books: dict[str, Orderbook] = {}
        for t in tickers:  # sequential on purpose: half the poll budget, no burst
            books[t] = await asyncio.to_thread(kalshi.get_orderbook, t)
        self._kalshi_markets = {m.id.split(":", 1)[1]: m for m in markets}
        self._kalshi_books = books
        self.kalshi_last_ok = datetime.now(UTC)
        self._bump()

    # -- Gamma metadata (slow-moving: question, close_ts, volume) ------------

    async def _gamma_refresh_loop(self) -> None:
        backoff = 1.0
        while True:
            try:
                cids = [p.pm_condition_id for p in self.pairs]
                self._gamma = await asyncio.to_thread(polymarket.get_gamma_markets, cids)
                backoff = 1.0
                await asyncio.sleep(GAMMA_REFRESH_S)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("gamma refresh failed: %s: %s", type(exc).__name__, exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX_S)

    # -- read side -----------------------------------------------------------

    def venue_status(self) -> dict[str, dict]:
        def one(last_ok: datetime | None, transport: str) -> dict:
            if last_ok is None:
                return {"transport": transport, "state": "connecting", "age_s": None}
            age = (datetime.now(UTC) - last_ok).total_seconds()
            state = "live" if age <= STALE_AFTER_S else "degraded"
            return {"transport": transport, "state": state, "age_s": round(age, 1)}

        return {
            "kalshi": one(self.kalshi_last_ok, "poll"),
            "polymarket": one(self.pm_last_ok, "websocket"),
        }


class StreamSource:
    """DataSource view over the hub's caches, so the screener and the pairs
    builder run unchanged against streamed data. Raises LookupError for a
    leg that has not arrived yet — compute_all treats that as an empty book."""

    def __init__(self, hub: StreamHub) -> None:
        self.hub = hub

    def markets(self) -> list[Market]:
        result: list[Market] = []
        for p in self.hub.pairs:
            km = self.hub._kalshi_markets.get(p.kalshi_ticker)
            if km is not None:
                result.append(km.model_copy(update={"event_key": p.event_key}))
            gamma = self.hub._gamma.get(p.pm_condition_id)
            state = self.hub._pm_books.get(p.pm_condition_id)
            if gamma is not None:
                book = state.to_orderbook() if state else None
                fetched = (state.updated_at if state else None) or datetime.now(UTC)
                pm = polymarket.parse_market(gamma, p.pm_yes_token, fetched, book=book)
                result.append(pm.model_copy(update={"event_key": p.event_key}))
        return result

    def orderbook(self, pair: PairMapping, venue: str) -> Orderbook:
        if venue == "kalshi":
            book = self.hub._kalshi_books.get(pair.kalshi_ticker)
        else:
            state = self.hub._pm_books.get(pair.pm_condition_id)
            book = state.to_orderbook() if state else None
        if book is None:
            raise LookupError(f"no streamed {venue} book yet for {pair.event_key}")
        return book


_hub: StreamHub | None = None


def get_hub() -> StreamHub | None:
    return _hub


def set_hub(hub: StreamHub | None) -> None:
    global _hub
    _hub = hub
