# Engineering doctrine — Tinli

## What this is

Tinli is a trading terminal for prediction markets: one screen across
**Kalshi and Polymarket**, aimed at quant-minded traders. The marketing site
and waitlist live at tinli.dev; **this repo is the product**. The
differentiator is quantitative substance — unified cross-venue data,
fee-aware arbitrage math, and a real risk engine — not another pretty market
browser. Keep that bar: every number shown must be defensible, every
assumption surfaced.

## Stack — decided, do not relitigate

Python 3.12 + FastAPI backend · React + Vite + TypeScript + Tailwind v4
frontend · pytest · polling now, websockets later · SQLite + parquet for v0
persistence · secrets in `.env` (never committed).

Ask before adding ANY dependency beyond those installed:
fastapi, uvicorn, httpx, pyyaml, cachetools, pyarrow, tzdata, numpy, pytest,
hypothesis (Python) · @fontsource-variable/inter and
@fontsource-variable/jetbrains-mono (JS).

## Layout

    services/api        FastAPI app (`tinli_api`) — routes, adapters,
                        screener, parquet history
    packages/risk       risk engine (`tinli_risk`)
    packages/divergence divergence engine (`tinli_divergence`)
    packages/schema     pydantic models + generated TS types (`tinli_schema`)
    apps/terminal       React UI
    data/event_map.yaml curated cross-venue pair mappings
    data/positions.yaml user's self-reported positions (never assert its
                        contents in tests — tests own their fixture book)
    data/history/       parquet snapshots (gitignored)
    docs/VENUES.md      API recon notes — READ BEFORE touching adapters
    scripts/dev.py      runs uvicorn :8000 + vite :5173 (make dev/demo)
    scripts/snapshot.py history recorder (make snapshot / --loop N)

## Commands

`make setup` venv + editable installs + npm install · `make dev` live ·
`make demo` fixtures with SIMULATED DATA badge · `make test` pytest + tsc ·
`make snapshot` record one history snapshot · `make types` regenerate
apps/terminal/src/types.gen.ts from the pydantic models (a drift test fails
if you change a model without regenerating) · `make curate` print candidate
pairs for human curation of the map · `make fixtures` re-record demo
fixtures after the map changes (one pair per PM conditionId — ids collide
otherwise).
Windows: make is ezwinports (`winget install ezwinports.make`).

## Architecture (bottom to top)

### Data layer (M1–M2)
- Venue adapters normalize both exchanges into **one schema**. Every price
  is a `Decimal` dollar on the 0–1 probability scale. **Nothing downstream
  may know which venue a number came from.**
- Adapters absorb venue quirks: Kalshi's deci-cent ticks and derived asks;
  Polymarket's worst-first books and JSON-encoded string fields.
- Event matching is **deliberately curated**: `data/event_map.yaml` holds
  the hand-verified pairs. No NLP guessing — never add automated matching
  without explicit direction.
- The FastAPI service exposes `/v1/markets`, `/v1/pairs`, and orderbooks,
  with TTL caching so UI polling never hammers the venues.
- Two run modes: **live**, or **demo** from recorded fixtures. Demo always
  shows a `SIMULATED DATA` badge and never masquerades as live.

### Divergence engine (M3) — the arbitrage core
- For each pair it prices **"the lock"**: buy YES on one venue, NO on the
  other, collect $1 at resolution regardless of outcome.
- Computes: raw basis → fee-adjusted edge (both venues' published fee
  schedules, implemented with source URLs in comments) → size-aware
  executable edge with exact fee rounding.
- **Always round edges down** — never round an edge into existence. This
  applies at rest too: parquet storage quantizes edges toward −∞.
- Pairs whose resolution criteria haven't been human-verified are flagged
  (`!` / UNVERIFIED) and buried. A big "edge" on mismatched contracts is a
  trap; the product treats it as one.

### Risk engine (M4)
- Positions are **self-reported** in `data/positions.yaml`. No venue auth in
  v0 — Tinli never touches user accounts. The file is hand-edited and
  hot-reloaded: a malformed file is ALWAYS a 422 naming the problem, never a
  500, and the UI surfaces the error instead of silently showing stale
  numbers.
- `/v1/risk` marks positions against the live feed: exposure, unrealized
  P&L, max loss, 95% VaR computed **two ways** (parametric and seeded Monte
  Carlo — both capped at max_loss), and Kelly sizing from the user's own
  probability estimates (never inferred from market prices).
- **Every assumption ships in the payload next to the numbers** (VaR horizon
  = resolution, MC seed/draws, price≈probability, independence across
  events).

### History (M6)
- `scripts/snapshot.py` records per-pair top-of-book + divergence outputs to
  decimal128 parquet under `data/history/`; `/v1/history/{event_key}` serves
  the window. No synthetic backfill, ever — an empty window says so.

### Terminal UI (M5 + redesign)
- One dense screen, 3s polling: selectable watchlist → selected pair's venue
  quotes with basis history, depth-curve charts and book ladders → lock
  economics → divergence screener → risk panel. A secondary CARDS view shows
  all pairs as tiles.
- Post-redesign visual system: real type hierarchy, bundled **Inter (labels,
  names, prose) + JetBrains Mono (every number and id slug)**, CVD-validated
  up/down colors, depth charts. Don't regress this.

## UI conventions

Design tokens live ONLY in `apps/terminal/src/index.css` (`@theme`):
bg `#0A1524`, panel `#0F1E33`, panel-2 `#132540`, border/line `#1E3A5C`,
primary `#2774AE`, hover `#8BB8E8`, gold `#FFD100`, text `#E6EDF5`,
muted `#8FA3B8`, up `#2EBD85`, down `#E5484D`.
Gold is for CTAs and KEY numbers only (badge, executable edges, MC VaR,
≥1¢ basis hot-flags), and doubles as the WARNING accent (`!` flags,
worst-case-fee markers, stale-data banners) — it is the palette's only
amber; do not add a separate warning color. up/down are direction semantics
(bids/asks, signed P&L) — text and thin marks, never large fills. JetBrains Mono for ALL
numbers; Inter for labels and prose. Dense terminal layout: 1px borders,
radius ≤ 4px, no shadows, no emojis. Verify UI work with a rendered
screenshot before calling it done.
Banned words in all copy: revolutionize, disrupt, unlock, supercharge,
empower, game-changing.

## Engineering posture (non-negotiable)

- `make test` stays green. New math ships with hand-computed expected values
  (derivation in a comment) plus Hypothesis property tests for invariants.
- All money math in `Decimal`, never float. Floats may exist only inside the
  Monte Carlo simulation and at the UI formatting edge.
- Small commits; one commit per milestone or coherent feature.
- Read-only public data only; identifiable User-Agent (`TINLI_USER_AGENT`);
  exponential backoff on rate limits (Kalshi 429s have no Retry-After).
- BYOK: any future authenticated feature uses the user's own venue keys from
  `.env`. Never proxy or resell venue data.
- Demo mode is always labeled; simulated data never presented as live.
- Fee models are pluggable per venue, from published fee schedules with the
  source URL in a code comment. If uncertain, mark a loud TODO — never guess
  a fee silently.

## Rules of thumb for changes

- If a feature needs venue-specific logic, it belongs in an adapter —
  downstream stays venue-agnostic.
- New event pairs go through `data/event_map.yaml` with human verification
  of resolution criteria; unverified pairs stay flagged.
- Bias conservative: round against the user's edge, surface assumptions,
  prefer "no signal" over a false one.
- Errors caused by user-editable files (positions.yaml) are 4xx with the
  location named, and the UI shows them — never a 500, never silence.

## Status & working style

v0 milestones M0–M6 are all shipped. Present a short plan before each new
milestone-sized feature and WAIT for approval. Small commits. If a venue's
real API differs from expectations, update docs/VENUES.md and adapt — don't
force the plan. Definition of done: `make demo` boots on fixtures with
badge, `make dev` runs live, `make test` green, README quickstart accurate,
UI changes screenshot-verified.
