# tinli

Trading terminal for prediction markets. One screen across Kalshi and
Polymarket: unified market data, a fee-aware divergence screener, and a
portfolio risk engine (exposure, VaR, Kelly sizing).

Site + waitlist: [tinli.dev](https://tinli.dev)

## Status

v0, under active development. Read-only public market data — no order
placement, no accounts. Milestones: M0 scaffold, M1 venue adapters, M2 API,
M3 divergence engine, M4 risk engine, M5 terminal UI (all done) · M6 history
snapshots (next).

The terminal is one dense screen: watchlist (click a pair to load its
books), cross-venue orderbook ladders, the fee-adjusted divergence
screener, and the risk panel — 3s polling, demo badge when on fixtures.

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

Copy `.env.example` to `.env` for local overrides. v0 needs no API keys.

## Layout

    services/api        FastAPI service
    packages/risk       risk engine
    packages/schema     shared pydantic models + generated TS types
    apps/terminal       React terminal UI
    data/event_map.yaml curated Kalshi↔Polymarket pair mappings
    docs/VENUES.md      venue API notes (endpoints, limits, gotchas)
