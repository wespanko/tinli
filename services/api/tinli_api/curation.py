"""In-app pair curation (M12): candidate discovery + guarded map editing.

The hard rule stands — event matching is CURATED, never auto-matched. This
module changes the ergonomics, not the doctrine:

- Discovery surfaces candidates with BOTH venues' resolution text and never
  writes anything.
- Adding a pair always lands it criteria_verified: false (flagged).
- Verifying is a separate explicit action that REQUIRES comparison notes.
- All writes go to data/event_map.yaml — still the single source of truth,
  still hand-editable — atomically (tmp + replace), preserving the file's
  header comment block.

Discovery is slow (Kalshi /events is paginated ~40 pages deep); results
are cached in-process for CANDIDATES_TTL_S and refreshed on demand.
"""

import os
import re
import threading
import time
from datetime import UTC, datetime

import yaml
from pydantic import BaseModel, Field

from tinli_schema import PairMapping

from tinli_api import datasource
from tinli_api.venues import kalshi, polymarket
from tinli_api.venues.client import get_json

CANDIDATES_TTL_S = 600.0
KALSHI_TOP = 60
MIN_SCORE = 0.34

STOP = {
    "the", "a", "an", "of", "in", "on", "at", "to", "will", "be", "by", "for",
    "vs", "v", "or", "and", "before", "after", "2026", "market", "who",
}


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP}


def _score(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _close_dt(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class Candidate(BaseModel):
    """One suggested Kalshi<->Polymarket match, with everything a human
    needs to compare resolution criteria IN the UI."""

    score: float
    kalshi_ticker: str
    kalshi_title: str
    kalshi_rules: str
    kalshi_close: str | None
    kalshi_vol_24h: float
    kalshi_url: str
    pm_condition_id: str
    pm_question: str
    pm_description: str
    pm_end: str | None
    pm_vol_24h: float
    pm_url: str
    pm_outcomes: list[str]
    pm_yes_token_guess: int | None = Field(
        description="index of 'Yes' in outcomes when unambiguous; null means "
        "the human must pick (e.g. team-name outcomes)"
    )
    suggested_event_key: str


def _slug(title: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in STOP][:5]
    return "-".join(words) or "new-pair"


def discover(kalshi_top: int = KALSHI_TOP, min_score: float = MIN_SCORE) -> list[Candidate]:
    """Same discovery as scripts/curate.py, returning models instead of
    stdout. Slow: full Kalshi /events pagination (creation-ordered
    /markets is drowned in auto-generated parlays — docs/VENUES.md)."""
    pairs = datasource.load_pairs()
    known_tickers = {p.kalshi_ticker for p in pairs}
    known_cids = {p.pm_condition_id for p in pairs}

    k_raw: list[dict] = []
    cursor: str | None = None
    for _ in range(40):
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
    k_top = [m for m in k_raw if m["ticker"] not in known_tickers][:kalshi_top]

    pm_raw = get_json(
        f"{polymarket.GAMMA}/markets",
        params={
            "active": "true", "closed": "false", "order": "volume24hr",
            "ascending": "false", "limit": "250",
        },
    )
    pm_open = [m for m in pm_raw if m.get("conditionId") not in known_cids]

    out: list[Candidate] = []
    for km in k_top:
        title = k_title(km)
        k_close = _close_dt(km.get("close_time", ""))
        best: list[tuple[float, dict]] = []
        for pm in pm_open:
            s = _score(title, pm.get("question", ""))
            if s < min_score:
                continue
            p_close = _close_dt(pm.get("endDate", ""))
            if k_close and p_close and abs((k_close - p_close).days) <= 3:
                s += 0.15  # resolution windows agree: same-event bonus
            best.append((s, pm))
        if not best:
            continue
        best.sort(key=lambda t: t[0], reverse=True)
        s, pm = best[0]
        outcomes = polymarket._decode_str_list(pm.get("outcomes", "[]"))
        out.append(Candidate(
            score=round(s, 3),
            kalshi_ticker=km["ticker"],
            kalshi_title=title,
            kalshi_rules=km.get("rules_primary") or "",
            kalshi_close=km.get("close_time"),
            kalshi_vol_24h=k_vol(km),
            kalshi_url=f"https://kalshi.com/markets/{km['ticker']}",
            pm_condition_id=pm["conditionId"],
            pm_question=pm.get("question") or "",
            pm_description=pm.get("description") or "",
            pm_end=pm.get("endDate"),
            pm_vol_24h=float(pm.get("volume24hr") or 0),
            pm_url=f"https://polymarket.com/market/{pm.get('slug', '')}",
            pm_outcomes=[str(o) for o in outcomes],
            pm_yes_token_guess=outcomes.index("Yes") if "Yes" in outcomes else None,
            suggested_event_key=_slug(title),
        ))
    out.sort(key=lambda c: c.score, reverse=True)
    return out


_cache: tuple[float, list[Candidate]] | None = None
_cache_lock = threading.Lock()


def cached_discover(refresh: bool = False) -> tuple[list[Candidate], float]:
    """(candidates, age_seconds). One discovery at a time; a stale cache is
    served while a refresh call recomputes."""
    global _cache
    with _cache_lock:
        now = time.monotonic()
        if _cache is not None and not refresh and now - _cache[0] < CANDIDATES_TTL_S:
            return _cache[1], now - _cache[0]
    found = discover()
    with _cache_lock:
        _cache = (time.monotonic(), found)
    return found, 0.0


# -- map editing --------------------------------------------------------------


class MapError(ValueError):
    """User-facing map-edit failure (409/422 shaped by the route)."""


def _read_map() -> tuple[str, list[dict]]:
    """(header_text, pairs) — header is everything before the `pairs:` line,
    preserved verbatim so the field documentation survives rewrites."""
    text = datasource.event_map_path().read_text(encoding="utf-8")
    idx = text.find("\npairs:")
    header = text[: idx + 1] if idx >= 0 else ""
    return header, yaml.safe_load(text)["pairs"]


def _write_map(header: str, pairs: list[dict]) -> None:
    body = yaml.safe_dump({"pairs": pairs}, sort_keys=False, allow_unicode=True, width=1000)
    tmp = datasource.event_map_path().with_suffix(".yaml.tmp")
    tmp.write_text(header + body, encoding="utf-8", newline="\n")
    tmp.replace(datasource.event_map_path())
    datasource.load_pairs.cache_clear()


def add_pair(stanza: dict) -> PairMapping:
    """Add a candidate as a FLAGGED pair. criteria_verified is forced false
    regardless of input — verification is a separate explicit action."""
    stanza = dict(stanza)
    stanza["criteria_verified"] = False
    stanza.setdefault(
        "notes",
        f"added from in-app curation {datetime.now(UTC):%Y-%m-%d}; "
        "compare both venues' resolution rules before trusting any edge",
    )
    pair = PairMapping(**stanza)  # pydantic 422s malformed input
    header, pairs = _read_map()
    if any(p["event_key"] == pair.event_key for p in pairs):
        raise MapError(f"event_key '{pair.event_key}' already exists")
    if any(p["pm_condition_id"] == pair.pm_condition_id for p in pairs):
        raise MapError(
            f"pm_condition_id already mapped — one pair per conditionId "
            f"(ids collide in fixtures and locks otherwise)"
        )
    if any(p["kalshi_ticker"] == pair.kalshi_ticker for p in pairs):
        raise MapError(f"kalshi_ticker '{pair.kalshi_ticker}' already mapped")
    pairs.append(pair.model_dump())
    _write_map(header, pairs)
    return pair


def set_verified(event_key: str, verified: bool, notes: str) -> PairMapping:
    """Flip criteria_verified. VERIFYING requires substantive notes — the
    doctrine's audit trail of what a human compared. Notes are appended
    (dated), never overwritten."""
    if verified and len(notes.strip()) < 20:
        raise MapError(
            "verifying requires comparison notes (>= 20 chars): what you "
            "compared in both venues' rules and any tail differences"
        )
    header, pairs = _read_map()
    for p in pairs:
        if p["event_key"] == event_key:
            p["criteria_verified"] = verified
            if notes.strip():
                stamp = f"{datetime.now(UTC):%Y-%m-%d}"
                p["notes"] = f"{p.get('notes', '')} | {stamp}: {notes.strip()}".strip(" |")
            _write_map(header, pairs)
            return PairMapping(**p)
    raise MapError(f"unknown event_key: {event_key}")


def retire_pair(event_key: str) -> None:
    header, pairs = _read_map()
    kept = [p for p in pairs if p["event_key"] != event_key]
    if len(kept) == len(pairs):
        raise MapError(f"unknown event_key: {event_key}")
    if not kept:
        raise MapError("refusing to retire the last pair — the map must not be empty")
    _write_map(header, kept)
