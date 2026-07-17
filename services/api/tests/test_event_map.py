from pathlib import Path

import yaml

from tinli_schema import PairMapping

ROOT = Path(__file__).resolve().parents[3]


def load_pairs() -> list[PairMapping]:
    raw = yaml.safe_load((ROOT / "data" / "event_map.yaml").read_text(encoding="utf-8"))
    return [PairMapping(**p) for p in raw["pairs"]]


def test_event_map_parses_and_validates():
    # critical mass, not a fixed census — the map shrinks when markets
    # resolve and grows on re-curation (scripts/curate.py)
    pairs = load_pairs()
    assert len(pairs) >= 8


def test_event_keys_unique():
    pairs = load_pairs()
    keys = [p.event_key for p in pairs]
    assert len(keys) == len(set(keys))


def test_condition_ids_look_valid():
    for p in load_pairs():
        assert p.pm_condition_id.startswith("0x") and len(p.pm_condition_id) == 66
        assert p.kalshi_ticker.startswith("KX")


def test_unverified_pairs_carry_notes():
    for p in load_pairs():
        if not p.criteria_verified:
            assert len(p.notes) > 20, f"{p.event_key}: unverified pair must explain why"


def test_every_pair_has_fixtures():
    fixtures = Path(__file__).parent / "fixtures"
    for p in load_pairs():
        assert (fixtures / "kalshi" / f"market_{p.kalshi_ticker}.json").exists()
        assert (fixtures / "kalshi" / f"orderbook_{p.kalshi_ticker}.json").exists()
        assert (fixtures / "polymarket" / f"gamma_{p.pm_condition_id}.json").exists()
        assert (fixtures / "polymarket" / f"book_{p.pm_condition_id}.json").exists()
