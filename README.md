# tinli

Trading terminal for prediction markets. One screen across Kalshi and
Polymarket: unified market data, a fee-aware divergence screener, and a
portfolio risk engine (exposure, VaR, Kelly sizing).

Site: [tinli.dev](https://tinli.dev)

## Research: is the cross-venue arb real?

Recorded venue data answers it — see
[docs/research/edge-persistence.md](docs/research/edge-persistence.md)
(auto-generated from decimal128 parquet history by
`scripts/research_note.py`, data accumulating continuously):

- **9.9%** of 788k recorded pair-ticks showed a positive lock edge after
  exact taker fees at displayed size (max 8.56¢/contract).
- When edges appear they **persist** — median ~7 minutes; one pair carried
  a continuously executable after-fee edge for **6.6 days**: nobody is
  bridging these venues at size.
- **Capacity is the binding constraint**: taking every edge over 40 days
  locks only ~$5,874 on ~$980k deployed (0.6% absolute) — though latency
  is starting to matter as the sample grows (~5-min-late entry now keeps
  66% of instant P&L, down from 93% three weeks ago). The backtest
  (`packages/backtest`) is deliberately conservative — one lock per
  episode, floor-quantized edges, verified pairs only.

A second study, [docs/research/lead-lag.md](docs/research/lead-lag.md),
asks which venue discovers price first (move-conditional follow analysis,
exact binomial tests): each venue's moves are answered by the other well
above chance (59% pooled follow rate, p < 0.001 both directions) but
symmetrically — no leader at 60s cadence. It now includes an **event
study of the 2026-07-29 FOMC decision**: Kalshi's Fed market closes at
the announcement, so event-time price discovery was structurally 100%
Polymarket (repriced ~80¢ → 99.4¢ inside one 61s snapshot bracket), and
the largest at-size lock ever recorded — **$1,438 after fees on one
tick** — was on display 36 minutes before the release.

## Status

v0 feature-complete through M12: venue adapters, divergence + risk
engines, terminal UI, history snapshots, live streaming (M8), BYOK Kalshi
auth (M9), research layer (M10–M11), in-app pair curation + keyboard nav
(M12), precise arb model (M14: carry-adjusted edges, whole-contract
sizing, legging risk). Read-only public market data — no order placement,
ever.

The terminal is two panes: one ranked pair list (each pair joined with
its fee-adjusted lock edge at executable size; unverified and settled
pairs collapsed under dividers) and the selected pair's market — venue
quotes, basis history, the depth-walked lock curve with carry and legging
risk, and depth curves plus raw ladders behind a DEPTH toggle. The
self-reported book and risk engine live in a BOOK tab. Streamed live
(Polymarket websocket + Kalshi fast-poll) with a 3s-polling fallback,
demo badge when on fixtures.

Positions for the risk engine (`/v1/risk`) are self-reported: edit
`data/positions.yaml` (an example book ships with the repo). No venue auth
in v0 — Tinli never sees your accounts.

## Quickstart

Prereqs: Python 3.12+ and Node 20+. Then:

    python run.py           # live public data -> http://localhost:5173
    python run.py demo      # recorded fixtures + SIMULATED DATA badge

First run bootstraps everything (venv, installs); later runs boot straight
in. GNU make users can keep using `make setup / dev / demo / test`
(Windows: `winget install ezwinports.make`).
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
