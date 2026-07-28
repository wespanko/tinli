"""M12 in-app curation — map editing guards, doctrine enforcement, routes.

Every test runs against a TEMP copy of the map (TINLI_EVENT_MAP); the real
data/event_map.yaml is never touched.
"""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from tinli_api import curation, datasource
from tinli_api.main import app

HEADER = "# Curated pair mappings — test copy.\n# Field docs live here.\n\n"

PAIRS = [
    {
        "event_key": "pair-a", "question": "Pair A", "kalshi_ticker": "KA",
        "pm_condition_id": "0xa", "pm_yes_token": 0,
        "criteria_verified": True, "pm_fee_category": "finance", "notes": "seed",
    },
    {
        "event_key": "pair-b", "question": "Pair B", "kalshi_ticker": "KB",
        "pm_condition_id": "0xb", "pm_yes_token": 0,
        "criteria_verified": False, "pm_fee_category": None, "notes": "flagged seed",
    },
]


@pytest.fixture
def tmp_map(tmp_path, monkeypatch):
    path = tmp_path / "event_map.yaml"
    path.write_text(
        HEADER + yaml.safe_dump({"pairs": PAIRS}, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.setenv("TINLI_EVENT_MAP", str(path))
    datasource.load_pairs.cache_clear()
    yield path
    datasource.load_pairs.cache_clear()


@pytest.fixture
def client(tmp_map, monkeypatch):
    monkeypatch.delenv("TINLI_READONLY", raising=False)
    datasource.reset_source()
    yield TestClient(app)
    datasource.reset_source()


NEW = {
    "event_key": "pair-c", "question": "Pair C", "kalshi_ticker": "KC",
    "pm_condition_id": "0xc", "pm_yes_token": 1,
}


def test_add_pair_lands_flagged_even_if_caller_claims_verified(tmp_map):
    pair = curation.add_pair({**NEW, "criteria_verified": True})
    assert pair.criteria_verified is False, "adds are ALWAYS flagged"
    on_disk = yaml.safe_load(tmp_map.read_text(encoding="utf-8"))["pairs"]
    assert on_disk[-1]["event_key"] == "pair-c"
    assert on_disk[-1]["criteria_verified"] is False
    assert "compare both venues" in on_disk[-1]["notes"]


def test_add_pair_preserves_header_and_existing(tmp_map):
    curation.add_pair(dict(NEW))
    text = tmp_map.read_text(encoding="utf-8")
    assert text.startswith(HEADER), "header comment block must survive rewrites"
    assert "pair-a" in text and "flagged seed" in text


def test_add_pair_rejects_collisions(tmp_map):
    with pytest.raises(curation.MapError, match="already exists"):
        curation.add_pair({**NEW, "event_key": "pair-a"})
    with pytest.raises(curation.MapError, match="conditionId"):
        curation.add_pair({**NEW, "pm_condition_id": "0xa"})
    with pytest.raises(curation.MapError, match="kalshi_ticker"):
        curation.add_pair({**NEW, "kalshi_ticker": "KB"})


def test_verify_requires_substantive_notes(tmp_map):
    with pytest.raises(curation.MapError, match="requires comparison notes"):
        curation.set_verified("pair-b", True, "ok")
    pair = curation.set_verified(
        "pair-b", True, "compared both venues' rules 2026-07-27; tails match"
    )
    assert pair.criteria_verified is True
    assert "flagged seed | " in pair.notes, "notes append, never overwrite"


def test_unverify_needs_no_notes(tmp_map):
    pair = curation.set_verified("pair-a", False, "")
    assert pair.criteria_verified is False
    assert pair.notes == "seed"


def test_retire_and_last_pair_guard(tmp_map):
    curation.retire_pair("pair-b")
    assert [p.event_key for p in datasource.load_pairs()] == ["pair-a"]
    with pytest.raises(curation.MapError, match="last pair"):
        curation.retire_pair("pair-a")


def test_roundtrip_map_stays_hand_editable(tmp_map):
    """After an in-app edit the file still parses as the same shape the
    hand-editing workflow expects."""
    curation.add_pair(dict(NEW))
    curation.set_verified("pair-c", True, "compared: identical settlement sources, no tails")
    raw = yaml.safe_load(tmp_map.read_text(encoding="utf-8"))
    assert {p["event_key"] for p in raw["pairs"]} == {"pair-a", "pair-b", "pair-c"}
    assert all(isinstance(p["criteria_verified"], bool) for p in raw["pairs"])


# -- routes -------------------------------------------------------------------


def test_routes_mutate_and_return_pairs(client, monkeypatch):
    monkeypatch.setenv("TINLI_DEMO", "1")  # avoid live venue fetches in response build
    datasource.reset_source()
    r = client.post("/v1/curate/pairs", json={**NEW, "question": "Pair C"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pair"]["event_key"] == "pair-c"
    r = client.post("/v1/curate/pairs/pair-c/verify",
                    json={"verified": True, "notes": "x" * 25})
    assert r.status_code == 200
    r = client.delete("/v1/curate/pairs/pair-c")
    assert r.status_code == 200
    r = client.delete("/v1/curate/pairs/nope")
    assert r.status_code == 404


def test_routes_shape_errors(client):
    assert client.post("/v1/curate/pairs", json={**NEW, "event_key": "pair-a"}).status_code == 409
    r = client.post("/v1/curate/pairs/pair-b/verify", json={"verified": True, "notes": ""})
    assert r.status_code == 422
    assert "comparison notes" in r.json()["detail"]


def test_routes_readonly_guard(client, monkeypatch):
    monkeypatch.setenv("TINLI_READONLY", "1")
    assert client.post("/v1/curate/pairs", json=NEW).status_code == 403
    assert client.delete("/v1/curate/pairs/pair-a").status_code == 403
    assert client.post(
        "/v1/curate/pairs/pair-a/verify", json={"verified": False}
    ).status_code == 403


def test_candidates_endpoint_serves_cache(client, monkeypatch):
    calls = {"n": 0}

    def fake_discover(kalshi_top=60, min_score=0.34):
        calls["n"] += 1
        return [curation.Candidate(
            score=0.5, kalshi_ticker="KX", kalshi_title="T", kalshi_rules="r",
            kalshi_close=None, kalshi_vol_24h=1.0, kalshi_url="u",
            pm_condition_id="0xn", pm_question="q", pm_description="d",
            pm_end=None, pm_vol_24h=2.0, pm_url="u2", pm_outcomes=["Yes", "No"],
            pm_yes_token_guess=0, suggested_event_key="t",
        )]

    monkeypatch.setattr(curation, "discover", fake_discover)
    monkeypatch.setattr(curation, "_cache", None)
    r1 = client.get("/v1/curate/candidates")
    r2 = client.get("/v1/curate/candidates")
    assert r1.status_code == r2.status_code == 200
    assert calls["n"] == 1, "second hit must come from cache"
    assert r2.json()["candidates"][0]["kalshi_ticker"] == "KX"
    client.get("/v1/curate/candidates?refresh=true")
    assert calls["n"] == 2
