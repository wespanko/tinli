# Engineering doctrine — Tinli conventions

Tinli is a trading terminal for prediction markets (Kalshi + Polymarket).
Differentiator is quantitative substance: unified cross-venue data layer,
fee-aware divergence screener, portfolio risk engine (VaR, exposure, Kelly
sizing). Audience: quant-minded traders. Marketing site + waitlist live at
tinli.dev; this repo is the product.

## Stack — decided, do not relitigate

Python 3.12 + FastAPI backend · React + Vite + TypeScript + Tailwind v4
frontend · pytest · polling now, websockets later · SQLite + parquet for v0
persistence · secrets in `.env` (never committed).

Ask before adding ANY dependency beyond:
fastapi, uvicorn, httpx, pyyaml, cachetools, pytest (installed) and the
already-approved future adds: hypothesis (M4), numpy (M4), pyarrow (M6).

## Layout

    services/api        FastAPI app (`tinli_api`)
    packages/risk       risk engine (`tinli_risk`)
    packages/schema     pydantic models + generated TS types (`tinli_schema`)
    apps/terminal       React UI
    data/event_map.yaml curated cross-venue pair mappings
    docs/VENUES.md      API recon notes — READ BEFORE touching adapters
    scripts/dev.py      runs uvicorn :8000 + vite :5173 (make dev/demo)

## Commands

`make setup` venv + editable installs + npm install · `make dev` live ·
`make demo` fixtures with SIMULATED DATA badge · `make test` pytest + tsc.
Windows: make is ezwinports (`winget install ezwinports.make`).

## Hard constraints

- v0 is READ-ONLY public market data. No order placement, no user auth, no
  scraping — documented public APIs only, with caching, exponential backoff
  (Kalshi 429s have no Retry-After header), and the identifiable User-Agent
  from `TINLI_USER_AGENT`.
- BYOK: any future authenticated feature uses the user's own venue keys from
  `.env`. Never proxy or resell venue data.
- Event matching is CURATED: `data/event_map.yaml` holds ~20 manually matched
  liquid pairs. NLP auto-matching is explicitly out of scope.
- Fee models are pluggable per venue, implemented from each venue's published
  fee schedule with the source URL in a code comment. If uncertain, mark a
  loud TODO — never guess a fee silently.
- Demo mode boots entirely from recorded fixtures with a visible
  "SIMULATED DATA" badge. Fixture data is never presented as live.
- Prices are `Decimal` end to end in Python — never float. Venues return
  decimal strings; see docs/VENUES.md for per-venue parsing gotchas
  (Kalshi deci-cent ticks, Polymarket books sorted worst→best, Gamma
  JSON-encoded string fields).

## UI conventions

Design tokens live ONLY in `apps/terminal/src/index.css` (`@theme`):
bg `#0A1524`, panel `#0F1E33`, border/line `#1E3A5C`, primary `#2774AE`,
hover `#8BB8E8`, gold `#FFD100`, text `#E6EDF5`, muted `#8FA3B8`.
Gold is for CTAs and key numbers ONLY. JetBrains Mono for ALL numbers.
Dense terminal layout: 1px borders, radius ≤ 4px, no shadows, no emojis.
Banned words in all copy: revolutionize, disrupt, unlock, supercharge,
empower, game-changing.

## Milestones — execute in order, verify each, commit per milestone

M0 recon + scaffold (done) · M1 adapters + unified schema, fixtures, pytest ·
M2 API: /v1/markets, /v1/markets/{id}/orderbook, /v1/pairs, TTL cache,
/healthz · M3 divergence engine (raw basis, fee-adjusted edge, size-aware
executable edge), /v1/divergence, hand-computed unit tests · M4 risk engine
(exposure, 95% VaR parametric AND Monte Carlo with documented assumptions,
Kelly), /v1/risk, property-based tests · M5 one dense terminal screen,
3s polling, demo badge · M6 parquet history snapshot job.

## Working style

Present a short plan before coding each milestone and WAIT for approval.
Small commits. If a venue's real API differs from expectations, update
docs/VENUES.md and adapt — don't force the plan. Definition of done:
`make demo` boots on fixtures with badge, `make dev` runs live, `make test`
green, README quickstart accurate.
