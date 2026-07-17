"""Assisted pair curation — candidate discovery, NOT auto-matching.

Fetches top-volume OPEN markets from both venues and prints candidate
Kalshi<->Polymarket matches (title-token overlap + close-time proximity) as
ready-to-edit event_map.yaml stanzas, each with both venues' resolution
text so a HUMAN can compare criteria. Nothing is written anywhere: the
output is raw material for hand-curation, per the hard rule that event
matching is curated and NLP matching is out of scope.

Usage: .venv/Scripts/python scripts/curate.py [--kalshi-top 60] [--min-score 0.34]
"""

import argparse
import json
import re
from datetime import datetime

import yaml
from pathlib import Path

from tinli_api.venues import kalshi, polymarket
from tinli_api.venues.client import get_json

REPO = Path(__file__).resolve().parents[1]

STOP = {
    "the", "a", "an", "of", "in", "on", "at", "to", "will", "be", "by", "for",
    "vs", "v", "or", "and", "before", "after", "2026", "market", "who",
}


def tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP}


def score(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def close_dt(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kalshi-top", type=int, default=60)
    ap.add_argument("--min-score", type=float, default=0.34)
    args = ap.parse_args()

    mapped = yaml.safe_load((REPO / "data" / "event_map.yaml").read_text(encoding="utf-8"))
    known_tickers = {p["kalshi_ticker"] for p in mapped["pairs"]}
    known_cids = {p["pm_condition_id"] for p in mapped["pairs"]}

    print("fetching top-volume open markets from both venues…", flush=True)
    # /markets?status=open is creation-ordered and drowned in auto-generated
    # parlays (25 pages deep, verified 2026-07-16) — paginate /events with
    # nested markets instead: real events only, ~200/page
    k_raw: list[dict] = []
    cursor: str | None = None
    for page in range(40):
        params: dict = {"status": "open", "limit": 200, "with_nested_markets": "true"}
        if cursor:
            params["cursor"] = cursor
        raw = get_json(f"{kalshi.BASE}/events", params=params)
        events = raw.get("events", [])
        for e in events:
            for m in e.get("markets") or []:
                m["_event_title"] = e.get("title") or ""
                k_raw.append(m)
        cursor = raw.get("cursor")
        print(f"  kalshi events page {page + 1}: total markets {len(k_raw)}", flush=True)
        if not cursor or not events:
            break

    def k_vol(m: dict) -> float:
        return float(m.get("volume_24h_fp") or m.get("volume_24h") or 0)

    def k_title(m: dict) -> str:
        title = m.get("title") or m["_event_title"]
        sub = m.get("yes_sub_title") or ""
        return f"{title} {sub}".strip()

    k_raw = [m for m in k_raw if k_vol(m) > 0]
    k_raw.sort(key=k_vol, reverse=True)
    k_top = [m for m in k_raw if m["ticker"] not in known_tickers][: args.kalshi_top]

    pm_raw = get_json(
        f"{polymarket.GAMMA}/markets",
        params={
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
            "limit": "250",
        },
    )
    pm_open = [m for m in pm_raw if m.get("conditionId") not in known_cids]

    found = 0
    for km in k_top:
        title = k_title(km)
        k_close = close_dt(km.get("close_time", ""))
        best = []
        for pm in pm_open:
            s = score(title, pm.get("question", ""))
            if s < args.min_score:
                continue
            p_close = close_dt(pm.get("endDate", ""))
            if k_close and p_close and abs((k_close - p_close).days) <= 3:
                s += 0.15  # same-event bonus: resolution windows agree
            best.append((s, pm))
        best.sort(key=lambda t: t[0], reverse=True)
        if not best:
            continue
        found += 1
        s, pm = best[0]
        outcomes = polymarket._decode_str_list(pm.get("outcomes", "[]"))
        yes_guess = outcomes.index("Yes") if "Yes" in outcomes else "TODO"
        print("=" * 78)
        print(f"score {s:.2f}   K vol24h {float(km.get('volume_24h_fp') or km.get('volume_24h') or 0):,.0f}"
              f"   PM vol24h {float(pm.get('volume24hr') or 0):,.0f}")
        print(f"KALSHI  {km['ticker']}: {title}  (closes {km.get('close_time')})")
        print(f"  rules: {(km.get('rules_primary') or '')[:300]}")
        print(f"POLYMKT {pm['conditionId']}: {pm.get('question')}  (ends {pm.get('endDate')})")
        print(f"  desc:  {(pm.get('description') or '')[:300]}")
        print(f"  outcomes: {outcomes}  category: {pm.get('category')}")
        print("--- stanza (verify criteria, set pm_fee_category, THEN flip verified) ---")
        stanza = {
            "event_key": "TODO-slug",
            "question": title,
            "kalshi_ticker": km["ticker"],
            "pm_condition_id": pm["conditionId"],
            "pm_yes_token": yes_guess,
            "criteria_verified": False,
            "pm_fee_category": None,
            "notes": "TODO: compare resolution rules before trusting any edge",
        }
        print(yaml.safe_dump([stanza], sort_keys=False, allow_unicode=True))
    print(f"{found} candidate(s) above score {args.min_score} from top {args.kalshi_top} Kalshi markets")


if __name__ == "__main__":
    main()
