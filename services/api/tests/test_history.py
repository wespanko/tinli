"""M6: parquet history round-trip and /v1/history endpoint (demo fixtures)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tinli_api import datasource
from tinli_api.history import _downsample, read_history, rows_from_items, write_rows
from tinli_api.main import app
from tinli_api.screener import compute_all

T0 = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def demo_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("TINLI_DEMO", "1")
    monkeypatch.setenv("TINLI_HISTORY_DIR", str(tmp_path / "history"))
    datasource.reset_source()
    yield
    datasource.reset_source()


@pytest.fixture
def client():
    return TestClient(app)


def snap(ts: datetime) -> list[dict]:
    return rows_from_items(compute_all(datasource.get_source()), ts)


def test_roundtrip_preserves_decimals_exactly():
    items = compute_all(datasource.get_source())
    write_rows(rows_from_items(items, T0))
    it = next(i for i in items if i.raw_basis_cents is not None)
    (row,) = read_history(it.event_key, hours=1, now=T0)
    assert row["ts"] == T0
    assert isinstance(row["raw_basis_cents"], Decimal)
    assert row["raw_basis_cents"] == it.raw_basis_cents.quantize(Decimal("0.000001"))
    assert row["k_bid"] == it.kalshi.bid
    assert row["p_ask"] == it.polymarket.ask
    assert row["max_lock_size"] == it.max_lock_size


def test_window_filters_and_sorts_across_files():
    old = T0 - timedelta(hours=30)  # outside a 24h window, previous day dir
    write_rows(snap(old))
    write_rows(snap(T0 - timedelta(hours=2)))
    write_rows(snap(T0 - timedelta(hours=1)))
    key = compute_all(datasource.get_source())[0].event_key
    rows = read_history(key, hours=24, now=T0)
    assert [r["ts"] for r in rows] == [T0 - timedelta(hours=2), T0 - timedelta(hours=1)]
    assert read_history(key, hours=48, now=T0)[0]["ts"] == old


def test_downsample_keeps_newest():
    rows = [{"ts": i} for i in range(1203)]
    kept = _downsample(rows, 500)
    assert len(kept) <= 501
    assert kept[-1]["ts"] == 1202


def test_api_history_serves_points(client):
    write_rows(snap(datetime.now(UTC)))
    key = compute_all(datasource.get_source())[0].event_key
    r = client.get(f"/v1/history/{key}?hours=24")
    assert r.status_code == 200
    body = r.json()
    assert body["event_key"] == key
    (pt,) = body["points"]
    assert isinstance(pt["raw_basis_cents"], (str, type(None))), "Decimals travel as strings"
    if pt["k_mid"] is not None:
        assert isinstance(pt["k_mid"], str)


def test_api_history_unknown_pair_404(client):
    assert client.get("/v1/history/not-a-pair").status_code == 404


def test_api_history_empty_window_is_empty_not_error(client):
    key = compute_all(datasource.get_source())[0].event_key
    r = client.get(f"/v1/history/{key}?hours=24")
    assert r.status_code == 200
    assert r.json()["points"] == []


def test_api_history_hours_bounds(client):
    key = compute_all(datasource.get_source())[0].event_key
    assert client.get(f"/v1/history/{key}?hours=0").status_code == 422
    assert client.get(f"/v1/history/{key}?hours=200").status_code == 422
