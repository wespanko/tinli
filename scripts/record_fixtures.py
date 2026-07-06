"""Record raw venue API responses for every pair in data/event_map.yaml.

The saved JSON is byte-for-byte what the venues returned; adapters parse these
fixtures in tests and in demo mode. Fixture data is never presented as live.

Usage: .venv/Scripts/python scripts/record_fixtures.py
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from tinli_api.venues import kalshi, polymarket
from tinli_api.venues.client import get_json

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "services" / "api" / "tests" / "fixtures"


def save(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def main() -> int:
    pairs = yaml.safe_load((ROOT / "data" / "event_map.yaml").read_text(encoding="utf-8"))["pairs"]
    recorded_at = datetime.now(UTC).isoformat()
    manifest = {"recorded_at": recorded_at, "pairs": []}

    for p in pairs:
        key = p["event_key"]
        kticker = p["kalshi_ticker"]
        cid = p["pm_condition_id"]
        print(f"recording {key} ...")

        k_market = get_json(f"{kalshi.BASE}/markets/{kticker}")
        k_book = get_json(f"{kalshi.BASE}/markets/{kticker}/orderbook", params={"depth": 20})
        save(FIXTURES / "kalshi" / f"market_{kticker}.json", k_market)
        save(FIXTURES / "kalshi" / f"orderbook_{kticker}.json", k_book)

        gamma = polymarket.get_gamma_market(cid)
        token = polymarket.yes_token_id(gamma, p["pm_yes_token"])
        pm_book = get_json(f"{polymarket.CLOB}/book", params={"token_id": token})
        save(FIXTURES / "polymarket" / f"gamma_{cid}.json", gamma)
        save(FIXTURES / "polymarket" / f"book_{cid}.json", pm_book)

        manifest["pairs"].append({"event_key": key, "kalshi_ticker": kticker, "pm_condition_id": cid})

    save(FIXTURES / "manifest.json", manifest)
    print(f"recorded {len(pairs)} pairs at {recorded_at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
