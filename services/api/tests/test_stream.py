"""M8 stream core — Polymarket websocket book reconstruction against
RECORDED frames (fixtures/polymarket/ws_frames_fed.json, captured live
2026-07-20) plus hand-computed delta cases."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tinli_api import datasource
from tinli_api.main import app
from tinli_api.routes import StreamUpdate, build_pairs, sse_event
from tinli_api.screener import compute_all
from tinli_api.stream import PmBook, StreamHub, StreamSource
from tinli_api.venues import kalshi

FIXTURES = Path(__file__).parent / "fixtures"
FRAMES = json.loads((FIXTURES / "polymarket" / "ws_frames_fed.json").read_text(encoding="utf-8"))
CID = "0x8bf1c1536ecb1c08fe13c6b71e8ab1f58bf3461c4cb79f5f1679f869a06aef86"
YES_TOKEN = "111604417349377875799825956621596386269673370070912696668140891647145772186047"

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def hub_with_token_map() -> StreamHub:
    hub = StreamHub()
    hub._token_to_cid = {YES_TOKEN: CID}
    return hub


def test_snapshot_matches_recorded_top_of_book():
    # recorded snapshot: worst-first, so the venue's LAST bid level
    # (0.924 / 24514.9) is the best bid, last ask (0.925 / 23597.87) the
    # best ask — same ordering quirk as the REST book (docs/VENUES.md)
    hub = hub_with_token_map()
    hub._handle_pm_frame(FRAMES[0])
    book = hub._pm_books[CID].to_orderbook()
    assert book.bids[0].price == Decimal("0.924")
    assert book.bids[0].size == Decimal("24514.9")
    assert book.asks[0].price == Decimal("0.925")
    assert book.asks[0].size == Decimal("23597.87")
    assert book.market_id == f"polymarket:{CID}"


def test_delta_semantics_hand_computed():
    # snapshot: bids 0.40/10 and 0.42/5, ask 0.60/8 -> best bid 0.42
    # BUY 0.41/3 inserts a level (absolute size, not increment)
    # BUY 0.42/0 deletes the level     -> best bid falls to 0.41
    # BUY 0.40/7 REPLACES size 10 -> 7 (absolute, again)
    b = PmBook(CID)
    b.apply_snapshot(
        {
            "bids": [{"price": "0.40", "size": "10"}, {"price": "0.42", "size": "5"}],
            "asks": [{"price": "0.60", "size": "8"}],
        },
        NOW,
    )
    assert b.to_orderbook().bids[0].price == Decimal("0.42")
    b.apply_change("BUY", "0.41", "3", NOW)
    b.apply_change("BUY", "0.42", "0", NOW)
    b.apply_change("BUY", "0.40", "7", NOW)
    book = b.to_orderbook()
    assert [(l.price, l.size) for l in book.bids] == [
        (Decimal("0.41"), Decimal("3")),
        (Decimal("0.40"), Decimal("7")),
    ]
    assert book.asks[0].price == Decimal("0.60")


def test_full_recorded_replay_keeps_invariants():
    hub = hub_with_token_map()
    for frame in FRAMES:
        hub._handle_pm_frame(frame)
    # only the YES token's book is tracked: price_changes for the NO-token
    # twin and last_trade_price events must not create phantom books
    assert set(hub._pm_books) == {CID}
    book = hub._pm_books[CID].to_orderbook()
    bid_prices = [l.price for l in book.bids]
    ask_prices = [l.price for l in book.asks]
    assert bid_prices == sorted(bid_prices, reverse=True), "bids must be best-first"
    assert ask_prices == sorted(ask_prices), "asks must be best-first"
    assert book.bids[0].price < book.asks[0].price, "book must not be crossed"
    assert all(l.size > 0 for l in book.bids + book.asks), "size-0 levels must be gone"
    assert hub.pm_last_ok is not None
    assert hub.version > 0


def test_mid_stream_resnapshot_resets_levels():
    # a second `book` event replaces state wholesale; stale levels from the
    # first snapshot must not linger
    b = PmBook(CID)
    b.apply_snapshot({"bids": [{"price": "0.10", "size": "1"}], "asks": []}, NOW)
    b.apply_snapshot({"bids": [{"price": "0.20", "size": "2"}], "asks": []}, NOW)
    book = b.to_orderbook()
    assert [(l.price, l.size) for l in book.bids] == [(Decimal("0.20"), Decimal("2"))]


def test_stream_endpoint_503_when_hub_absent(monkeypatch):
    # demo mode / TestClient without lifespan: no hub -> a clear 503, never
    # a hang or a 500; the UI treats 503 as "fall back to polling"
    monkeypatch.setenv("TINLI_DEMO", "1")
    datasource.reset_source()
    r = TestClient(app).get("/v1/stream")
    assert r.status_code == 503
    assert "stream not running" in r.json()["detail"]
    datasource.reset_source()


def test_stream_update_builds_from_hub_caches():
    """A hub primed from recorded fixtures produces a complete SSE payload:
    every mapped pair present, streamed PM book + fixture Kalshi book meeting
    in the screener, payload framed as an SSE data event."""
    hub = hub_with_token_map()
    hub._handle_pm_frame(FRAMES[0])
    fed = next(p for p in hub.pairs if p.event_key == "fed-jul26-no-change")
    raw = json.loads(
        (FIXTURES / "kalshi" / f"orderbook_{fed.kalshi_ticker}.json").read_text(encoding="utf-8")
    )
    hub._kalshi_books[fed.kalshi_ticker] = kalshi.parse_orderbook(fed.kalshi_ticker, raw, NOW)

    source = StreamSource(hub)
    items = compute_all(source)
    assert len(items) == len(hub.pairs), "screener must emit one item per mapped pair"
    fed_item = next(i for i in items if i.event_key == "fed-jul26-no-change")
    assert fed_item.raw_basis_cents is not None, "both legs streamed -> basis computable"

    update = StreamUpdate(
        ts=NOW, venues=hub.venue_status(), pairs=build_pairs(source.markets()), divergence=items
    )
    line = sse_event(update)
    assert line.startswith("data: {") and line.endswith("\n\n")
    assert "fed-jul26-no-change" in line


def test_venue_status_states():
    hub = hub_with_token_map()
    s = hub.venue_status()
    assert s["polymarket"]["state"] == "connecting"
    assert s["kalshi"]["transport"] == "poll"
    hub.pm_last_ok = datetime.now(UTC)
    assert hub.venue_status()["polymarket"]["state"] == "live"
    hub.pm_last_ok = datetime.now(UTC) - timedelta(seconds=60)
    assert hub.venue_status()["polymarket"]["state"] == "degraded"
