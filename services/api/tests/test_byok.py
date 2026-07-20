"""M9 BYOK — Kalshi request signing, websocket book reconstruction, and the
read-only account report.

Signing spec and WS shapes are doc-derived (docs.kalshi.com, read
2026-07-20; exact JSON examples from the docs are used as fixtures here).
TODO(BYOK-live): pin against a real key + account the first time one is
configured — see docs/VENUES.md.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from tinli_api import datasource, routes
from tinli_api.main import app
from tinli_api.stream import KalshiBook, StreamHub
from tinli_api.venues import kalshi
from tinli_api.venues.kalshi_auth import KEY_ID_ENV, KEY_PATH_ENV, KalshiAuth, message
from tinli_schema import AccountPosition, Market

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


# -- request signing ----------------------------------------------------------


def test_signed_message_composition():
    # spec: f"{ts_ms}{METHOD}{path}" with the query string EXCLUDED
    assert (
        message(1234567890000, "get", "/trade-api/v2/portfolio/orders?limit=5")
        == "1234567890000GET/trade-api/v2/portfolio/orders"
    )


def test_signature_verifies_with_rsa_pss_sha256():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    auth = KalshiAuth("test-key-id", key)
    headers = auth.headers("GET", "/trade-api/v2/portfolio/positions", ts_ms=1234567890000)
    assert headers["KALSHI-ACCESS-KEY"] == "test-key-id"
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1234567890000"
    import base64

    key.public_key().verify(
        base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"]),
        b"1234567890000GET/trade-api/v2/portfolio/positions",
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )  # raises InvalidSignature on any parameter mismatch


def _write_test_key(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    p = tmp_path / "test_key.pem"
    p.write_bytes(pem)
    return p


def test_from_env_gates(tmp_path, monkeypatch):
    monkeypatch.delenv(KEY_ID_ENV, raising=False)
    monkeypatch.delenv(KEY_PATH_ENV, raising=False)
    assert KalshiAuth.from_env() is None, "no env -> feature off"
    monkeypatch.setenv(KEY_ID_ENV, "kid")
    monkeypatch.setenv(KEY_PATH_ENV, str(_write_test_key(tmp_path)))
    assert KalshiAuth.from_env() is not None
    # hosted read-only instances must refuse keys even when configured
    monkeypatch.setenv("TINLI_READONLY", "1")
    assert KalshiAuth.from_env() is None


# -- websocket book (doc example frames) --------------------------------------

SNAPSHOT = {  # verbatim from docs.kalshi.com/websockets/orderbook-updates.md
    "type": "orderbook_snapshot",
    "sid": 2,
    "seq": 2,
    "msg": {
        "market_ticker": "FED-23DEC-T3.00",
        "yes_dollars_fp": [["0.0800", "300.00"], ["0.2200", "333.00"]],
        "no_dollars_fp": [["0.5400", "20.00"], ["0.5600", "146.00"]],
    },
}


def test_kalshi_ws_book_snapshot_and_derived_asks():
    b = KalshiBook("FED-23DEC-T3.00")
    b.apply_snapshot(SNAPSHOT["msg"], NOW)
    book = b.to_orderbook()
    # yes bids best-first: 0.22 then 0.08
    assert [(l.price, l.size) for l in book.bids] == [
        (Decimal("0.2200"), Decimal("333.00")),
        (Decimal("0.0800"), Decimal("300.00")),
    ]
    # asks derived from NO bids: 1-0.56=0.44 (146) best, then 1-0.54=0.46 (20)
    assert [(l.price, l.size) for l in book.asks] == [
        (Decimal("0.4400"), Decimal("146.00")),
        (Decimal("0.4600"), Decimal("20.00")),
    ]


def test_kalshi_ws_delta_is_relative():
    # start yes@0.08 = 300.00; delta -54.00 -> 246.00 (docs call delta_fp an
    # update applied to the current book, negative allowed)
    b = KalshiBook("T")
    b.apply_snapshot({"yes_dollars_fp": [["0.08", "300.00"]], "no_dollars_fp": []}, NOW)
    b.apply_delta({"side": "yes", "price_dollars": "0.08", "delta_fp": "-54.00"}, NOW)
    assert b.yes[Decimal("0.08")] == Decimal("246.00")
    # a delta that empties the level removes it entirely
    b.apply_delta({"side": "yes", "price_dollars": "0.08", "delta_fp": "-246.00"}, NOW)
    assert Decimal("0.08") not in b.yes
    # a delta on an absent level creates it
    b.apply_delta({"side": "no", "price_dollars": "0.55", "delta_fp": "10.00"}, NOW)
    assert b.no[Decimal("0.55")] == Decimal("10.00")


def test_kalshi_frame_handler_flips_transport():
    hub = StreamHub()
    assert hub.kalshi_transport == "poll"
    hub._handle_kalshi_frame(SNAPSHOT)
    assert hub.kalshi_transport == "websocket"
    assert hub.venue_status()["kalshi"]["transport"] == "websocket"
    assert "FED-23DEC-T3.00" in hub._kalshi_ws_books
    # subscribe acks / unknown types are ignored, error frames raise
    hub._handle_kalshi_frame({"type": "subscribed", "id": 1})
    with pytest.raises(RuntimeError):
        hub._handle_kalshi_frame({"type": "error", "msg": {"code": 6, "msg": "nope"}})


# -- portfolio positions ------------------------------------------------------


def test_get_positions_parses_and_paginates(monkeypatch):
    pages = [
        {
            "market_positions": [
                {  # doc-shaped: signed fixed-point contracts, dollar strings
                    "ticker": "KXFEDDECISION-26JUL-H0",
                    "position_fp": "250.00",
                    "market_exposure_dollars": "137.500000",
                    "total_traded_dollars": "137.500000",
                    "realized_pnl_dollars": "0.000000",
                    "fees_paid_dollars": "2.750000",
                    "last_updated_ts": "2026-07-19T12:00:00Z",
                },
                {"ticker": "FLAT", "position_fp": "0.00"},  # flat: skipped
            ],
            "cursor": "page2",
        },
        {
            "market_positions": [
                {
                    "ticker": "KXBALLONDOR-26-LYAM",
                    "position_fp": "-40.00",  # negative = NO side
                    "market_exposure_dollars": "26.000000",
                    "total_traded_dollars": "30.000000",
                    "realized_pnl_dollars": "1.250000",
                    "fees_paid_dollars": "0.600000",
                },
            ],
            "cursor": None,
        },
    ]
    calls = []

    def fake_get_json(url, params=None, headers=None):
        assert callable(headers), "signed headers must be per-retry callables"
        calls.append(params)
        return pages[len(calls) - 1]

    monkeypatch.setattr("tinli_api.venues.kalshi.get_json", fake_get_json)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    out = kalshi.get_positions(KalshiAuth("k", key))
    assert len(calls) == 2 and calls[1]["cursor"] == "page2"
    assert [p.ticker for p in out] == ["KXFEDDECISION-26JUL-H0", "KXBALLONDOR-26-LYAM"]
    assert out[0].side == "yes" and out[0].contracts == Decimal("250.00")
    assert out[1].side == "no" and out[1].contracts == Decimal("40.00")
    assert out[1].realized_pnl == Decimal("1.250000")


# -- /v1/account --------------------------------------------------------------


@pytest.fixture
def demo_client(monkeypatch):
    monkeypatch.setenv("TINLI_DEMO", "1")
    datasource.reset_source()
    yield TestClient(app)
    datasource.reset_source()


def test_account_off_without_keys(demo_client, monkeypatch):
    monkeypatch.delenv(KEY_ID_ENV, raising=False)
    r = demo_client.get("/v1/account")
    assert r.status_code == 200
    body = r.json()
    assert body["byok"] is False and body["positions"] == []


def test_account_bad_key_file_is_422(demo_client, monkeypatch, tmp_path):
    bad = tmp_path / "not_a_key.pem"
    bad.write_text("garbage", encoding="utf-8")
    monkeypatch.setenv(KEY_ID_ENV, "kid")
    monkeypatch.setenv(KEY_PATH_ENV, str(bad))
    r = demo_client.get("/v1/account")
    assert r.status_code == 422
    assert KEY_ID_ENV in r.json()["detail"]


def test_account_marking_hand_computed(demo_client, monkeypatch, tmp_path):
    """YES 250 @ best_bid 0.93 -> value floor2(232.50)=232.50, cost 137.50,
    pnl +95.00. NO 40 with best_ask 0.35 -> mark 0.65, value 26.00, cost
    26.00, pnl 0. Unknown ticker -> unmarked, excluded from totals."""
    monkeypatch.setenv(KEY_ID_ENV, "kid")
    monkeypatch.setenv(KEY_PATH_ENV, str(_write_test_key(tmp_path)))

    positions = [
        AccountPosition(ticker="A", side="yes", contracts=Decimal("250"),
                        cost_basis=Decimal("137.50"), total_traded=Decimal("137.50"),
                        realized_pnl=Decimal(0), fees_paid=Decimal("2.75")),
        AccountPosition(ticker="B", side="no", contracts=Decimal("40"),
                        cost_basis=Decimal("26.00"), total_traded=Decimal("30.00"),
                        realized_pnl=Decimal("1.25"), fees_paid=Decimal("0.60")),
        AccountPosition(ticker="UNKNOWN", side="yes", contracts=Decimal("5"),
                        cost_basis=Decimal("1.00"), total_traded=Decimal("1.00"),
                        realized_pnl=Decimal(0), fees_paid=Decimal(0)),
    ]
    monkeypatch.setattr("tinli_api.routes.kalshi.get_positions", lambda auth: positions)

    def market(ticker, bid, ask):
        return Market(
            id=f"kalshi:{ticker}", venue="kalshi", question=ticker, status="open",
            yes_price=Decimal("0.5"), no_price=Decimal("0.5"),
            best_bid=Decimal(bid), best_ask=Decimal(ask), volume_24h=Decimal(0),
            close_ts=NOW, resolution_url="", fetched_at=NOW,
        )

    class FakeSource:
        def markets(self):
            return [market("A", "0.93", "0.94"), market("B", "0.34", "0.35")]

    monkeypatch.setattr("tinli_api.routes.get_source", lambda: FakeSource())

    body = demo_client.get("/v1/account").json()
    assert body["byok"] is True
    by_ticker = {r["position"]["ticker"]: r for r in body["positions"]}
    assert by_ticker["A"]["mark"] == "0.93"
    assert by_ticker["A"]["market_value"] == "232.50"
    assert by_ticker["A"]["unrealized_pnl"] == "95.00"
    assert by_ticker["B"]["mark"] == "0.65"
    assert by_ticker["B"]["market_value"] == "26.00"
    assert by_ticker["B"]["unrealized_pnl"] == "0.00"
    assert by_ticker["UNKNOWN"]["mark"] is None
    assert body["unmarked_positions"] == 1
    assert Decimal(body["total_market_value"]) == Decimal("258.50")
    assert Decimal(body["total_unrealized_pnl"]) == Decimal("95.00")
