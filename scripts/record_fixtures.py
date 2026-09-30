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

from tinli_api.datasource import CRYPTO_SERIES
from tinli_api.venues import deribit, kalshi, polymarket
from tinli_api.venues.client import get_json

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "services" / "api" / "tests" / "fixtures"


def save(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def main() -> int:
    pairs = yaml.safe_load((ROOT / "data" / "event_map.yaml").read_text(encoding="utf-8"))["pairs"]
    manifest_path = FIXTURES / "manifest.json"
    # --crypto-only re-records just the crypto ladders and keeps the pair
    # fixtures (and their recorded_at) untouched — tests pin pair values
    crypto_only = "--crypto-only" in sys.argv
    if crypto_only and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        recorded_at = manifest["recorded_at"]
        pairs = []
    else:
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
        try:
            pm_book = get_json(f"{polymarket.CLOB}/book", params={"token_id": token})
        except Exception as exc:
            # resolved/delisted markets lose their CLOB book (404) — record
            # the truth: an empty book, which downstream renders as no quotes
            print(f"  WARNING: no CLOB book for {key} ({exc}); recording empty book")
            pm_book = {"bids": [], "asks": []}
        save(FIXTURES / "polymarket" / f"gamma_{cid}.json", gamma)
        save(FIXTURES / "polymarket" / f"book_{cid}.json", pm_book)

        manifest["pairs"].append({"event_key": key, "kalshi_ticker": kticker, "pm_condition_id": cid})

    # crypto ladders: the Kalshi above/below series + the Deribit chain
    # and index, byte-for-byte, for BTC and ETH
    for coin, series in CRYPTO_SERIES.items():
        print(f"recording crypto {coin} ({series} + deribit) ...")
        save(
            FIXTURES / "kalshi" / f"series_{series}.json",
            {"markets": kalshi.get_series_markets(series)},
        )
        save(
            FIXTURES / "deribit" / f"summary_{coin}.json",
            {"result": deribit.get_book_summaries(coin)},
        )
        save(FIXTURES / "deribit" / f"index_{coin}.json", deribit.get_index(coin))
    manifest["crypto"] = list(CRYPTO_SERIES)
    # the ladders' own clock: demo mode prices them as of THIS instant, so
    # time-to-expiry is what it was when the chain was seen
    manifest["crypto_recorded_at"] = datetime.now(UTC).isoformat()

    save(FIXTURES / "manifest.json", manifest)
    print(f"recorded {len(pairs)} pairs + {len(CRYPTO_SERIES)} crypto ladders at {recorded_at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
