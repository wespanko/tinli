# tinli

Trading terminal for prediction markets. One screen across Kalshi and
Polymarket: unified market data, a fee-aware divergence screener, and a
portfolio risk engine (exposure, VaR, Kelly sizing).

Site + waitlist: [tinli.dev](https://tinli.dev)

## Research: is the cross-venue arb real?

Recorded venue data answers it — see
[docs/research/edge-persistence.md](docs/research/edge-persistence.md)
(auto-generated from decimal128 parquet history by
`scripts/research_note.py`, data accumulating continuously):

- **0.40%** of 212k recorded pair-ticks showed a positive lock edge after
  exact taker fees at displayed size (max 2.24¢/contract).
- When edges appear they **persist** — median 33s, longest 147 minutes of
  continuously executable after-fee edge: nobody is bridging these venues
  at size.
- **Capacity, not latency, is the binding constraint**: entering ~80s late
  still captures 88% of instant-entry P&L, but taking every edge for a
  week locks only ~$265 on ~$97k deployed. The backtest
  (`packages/backtest`) is deliberately conservative — one lock per
  episode, floor-quantized edges, verified pairs only.

## Status

v0 feature-complete through M9: venue adapters, divergence + risk engines,
terminal UI, history snapshots, live streaming (M8), BYOK Kalshi auth (M9).
Read-only public market data — no order placement, ever.

The terminal is one dense screen: watchlist (click a pair to load its
books), cross-venue orderbook ladders, the fee-adjusted divergence
screener, and the risk panel — streamed live (Polymarket websocket + Kalshi
fast-poll) with a 3s-polling fallback, demo badge when on fixtures.

Positions for the risk engine (`/v1/risk`) are self-reported: edit
`data/positions.yaml` (an example book ships with the repo). No venue auth
in v0 — Tinli never sees your accounts.

## Quickstart

Prereqs: Python 3.12, Node 20+, GNU make
(Windows: `winget install ezwinports.make`).

    make setup    # venv, package installs, npm install
    make dev      # API on :8000, UI on :5173, live public data
    make demo     # same, but recorded fixtures + SIMULATED DATA badge
    make test     # pytest + TypeScript checks
    make snapshot # record one history snapshot to data/history/ (parquet)

Continuous recording (feeds the basis-over-time chart):

    .venv/Scripts/python scripts/snapshot.py --loop 30

Copy `.env.example` to `.env` for local overrides. v0 needs no API keys.

## Hosted read-only instance

One container serves the API, the built UI, and the history recorder, with
positions editing disabled (`TINLI_READONLY=1`) and the example book
demoing the risk engine:

    docker build -t tinli .
    docker run -p 8080:8080 -v tinli_history:/data tinli

Fly.io: `fly launch --copy-config` once (creates the app + the
`tinli_history` volume from fly.toml), then `fly deploy`.

## Layout

    services/api        FastAPI service
    packages/risk       risk engine
    packages/schema     shared pydantic models + generated TS types
    apps/terminal       React terminal UI
    data/event_map.yaml curated Kalshi↔Polymarket pair mappings
    data/positions.yaml self-reported positions for /v1/risk
    data/history/       parquet snapshots (gitignored; make snapshot)
    docs/VENUES.md      venue API notes (endpoints, limits, gotchas)
