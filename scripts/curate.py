"""Assisted pair curation — candidate discovery, NOT auto-matching.

Prints candidate Kalshi<->Polymarket matches (title-token overlap with
cross-venue vocabulary aliases + close-time proximity) as ready-to-edit
event_map.yaml stanzas, each with both venues' resolution text so a HUMAN
can compare criteria. Nothing is written anywhere: the output is raw
material for hand-curation, per the hard rule that event matching is
curated and NLP matching is out of scope.

The discovery logic lives in tinli_api.curation (shared with the CURATE
view); this script is the terminal front-end.

Usage: .venv/Scripts/python scripts/curate.py [--kalshi-top 60] [--min-score 0.34]
"""

import argparse
import io
import sys

import yaml

from tinli_api.curation import discover


def main() -> None:
    # venue text carries unicode (curly quotes); never let cp1252 kill the run
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kalshi-top", type=int, default=60)
    ap.add_argument("--min-score", type=float, default=0.34)
    args = ap.parse_args()

    print("fetching top-volume open markets from both venues (~2 min)…", flush=True)
    candidates = discover(kalshi_top=args.kalshi_top, min_score=args.min_score)

    for c in candidates:
        print("=" * 78)
        print(f"score {c.score:.2f}   K vol24h {c.kalshi_vol_24h:,.0f}"
              f"   PM vol24h {c.pm_vol_24h:,.0f}")
        print(f"KALSHI  {c.kalshi_ticker}: {c.kalshi_title}  (closes {c.kalshi_close})")
        print(f"  rules: {c.kalshi_rules[:300]}")
        print(f"POLYMKT {c.pm_condition_id}: {c.pm_question}  (ends {c.pm_end})")
        print(f"  desc:  {c.pm_description[:300]}")
        print(f"  outcomes: {c.pm_outcomes}")
        print("--- stanza (verify criteria, set pm_fee_category, THEN flip verified) ---")
        stanza = {
            "event_key": c.suggested_event_key,
            "question": c.kalshi_title,
            "kalshi_ticker": c.kalshi_ticker,
            "pm_condition_id": c.pm_condition_id,
            "pm_yes_token": c.pm_yes_token_guess if c.pm_yes_token_guess is not None else "TODO",
            "criteria_verified": False,
            "pm_fee_category": None,
            "notes": "TODO: compare resolution rules before trusting any edge",
        }
        print(yaml.safe_dump([stanza], sort_keys=False, allow_unicode=True))
    print(f"{len(candidates)} candidate(s) above score {args.min_score} "
          f"from top {args.kalshi_top} Kalshi markets")


if __name__ == "__main__":
    main()
