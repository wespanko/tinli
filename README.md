# tinli

Trading terminal for prediction markets. One screen across Kalshi and
Polymarket: unified market data, a fee-aware divergence screener, and a
portfolio risk engine (exposure, VaR, Kelly sizing).

Site + waitlist: [tinli.dev](https://tinli.dev)

## Status

v0 feature-complete: M0 scaffold, M1 venue adapters, M2 API, M3 divergence
engine, M4 risk engine, M5 terminal UI, M6 history snapshots — all done.
Read-only public market data — no order placement, no accounts.

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
