# VENUES.md — API recon notes

Verified with live unauthenticated probes on **2026-07-05**. Re-verify response
shapes against recorded fixtures in M1; docs and reality drift.

---

## Kalshi — Trade API v2

- **Base URL:** `https://api.elections.kalshi.com/trade-api/v2`
  (mirror: `external-api.kalshi.com`; demo env: `external-api.demo.kalshi.co`)
- **Docs:** https://docs.kalshi.com
- **Auth:** none for market data. Verified empirically: `GET /markets` and
  `GET /markets/{ticker}/orderbook` return 200 with no headers, even though the
  doc pages list `KALSHI-ACCESS-KEY/SIGNATURE/TIMESTAMP`. Those (RSA-PSS
  signed) are required only for trading/portfolio endpoints — out of scope in
  v0 (BYOK later).

### Endpoints used

| Endpoint | Notes |
|---|---|
| `GET /markets` | `limit` ≤ 1000, `cursor` pagination, filters: `event_ticker`, `series_ticker`, `tickers` (CSV), `status`, `min/max_close_ts` |
| `GET /markets/{ticker}` | single market |
| `GET /markets/{ticker}/orderbook` | `depth` 0–100 (0 = all levels) |
| `GET /events`, `GET /events/{event_ticker}` | event grouping for display |

### Response shape — market object (as observed)

- Prices are **decimal dollar strings**, not integer cents: `yes_bid_dollars`,
  `yes_ask_dollars`, `no_bid_dollars`, `no_ask_dollars`, `last_price_dollars`
  (e.g. `"0.0475"`). Parse as `Decimal`, never float.
- Sizes/volumes are fixed-point strings: `volume_24h_fp`, `volume_fp`,
  `open_interest_fp` (contracts, 2dp).
- `liquidity_dollars` is **deprecated and always 0** — do not map it to our
  `liquidity` field; derive liquidity from orderbook depth instead.
- `close_time` ISO 8601; `status` enum
  `initialized|inactive|active|closed|determined|disputed|amended|finalized`.
  **Gotcha:** the query param uses `status=open` but the market object says
  `status: "active"` — they are different vocabularies.
- Markets can be **deci-cent priced**: `price_level_structure: "deci_cent"`,
  `price_ranges.step = "0.0010"`, `fractional_trading_enabled: true`. Never
  assume whole-cent ticks.
- `response_price_units: "usd_cent"` appears in responses; legacy integer-cent
  fields may coexist with the `_dollars` fields. M1 fixtures pin exactly which
  fields we parse.

### Orderbook shape (as observed)

```json
{ "orderbook_fp": { "yes_dollars": [["0.1500", "100.00"], ...],
                    "no_dollars":  [["0.8500", "75.00"], ...] } }
```

- Each level is `[price_string, contract_qty_string]`.
- **Bids only, both sides.** There are no asks: a yes ask at P is a no bid at
  1−P. Best yes ask = 1 − best no bid.
- Docs say levels are ordered best→worst; our probe hit an empty book.
  **TODO(M1):** confirm ordering against a liquid-market fixture.

### Rate limits

- Token-bucket (since 2026-04-23): Basic tier **200 read tokens/sec**, default
  cost **10 tokens/request** → ~20 reads/sec. Source:
  https://docs.kalshi.com/getting_started/rate_limits
- **429s carry no `Retry-After` and no `X-RateLimit-*` headers** → exponential
  backoff with jitter is mandatory, not optional.

### Fees (for M3 fee model)

- Taker: `ceil_to_next_cent(0.07 × contracts × P × (1−P))` per fill.
  Max 1.75¢/contract at P=0.50.
- Maker: 25% of the taker rate, charged only on fill.
- Sources: https://kalshi.com/docs/kalshi-fee-schedule.pdf (monthly PDF),
  https://kalshi.com/fee-schedule,
  https://help.kalshi.com/en/articles/13823805-fees
- **TODO(M3):** the PDF lists per-series exceptions (some series have maker
  fees, different rates). Read the current month's PDF at implementation time —
  do not hardcode from these notes.

---

## Polymarket — Gamma + CLOB

Two public APIs, both verified no-auth. (A third, `data-api.polymarket.com`,
is for user positions/trades — not needed in v0.)

### Gamma API — `https://gamma-api.polymarket.com` (metadata catalogue)

| Endpoint | Notes |
|---|---|
| `GET /markets` | `limit`, `offset` pagination; filters `active`, `closed`, `slug`, `id`, `condition_ids`; sort via `order` + `ascending` |
| `GET /events` | groups related markets (e.g. all World Cup winner markets) |

Response gotchas (verified):

- Returns a bare **JSON array**, not a wrapped object.
- `outcomes`, `outcomePrices`, `clobTokenIds` are **JSON-encoded strings**
  (`"[\"Yes\", \"No\"]"`) — double-decode them.
- Field names are camelCase: `conditionId`, `endDate`, `volume24hr`,
  `liquidityNum`, `orderPriceMinTickSize` (e.g. 0.001), `orderMinSize`.
- Identity model: a Gamma market = one binary question with a `conditionId`
  and **two `clobTokenIds` (YES token, NO token)** in `outcomes` order. All
  CLOB queries are per token id.

### CLOB API — `https://clob.polymarket.com` (books, prices, history)

| Endpoint | Notes |
|---|---|
| `GET /book?token_id=` | full L2 book for one token |
| `GET /prices-history?market=<token_id>&interval=1d&fidelity=60` | `interval` (`1d`,`1w`,`max`,…) or `startTs`/`endTs`; `fidelity` in minutes |
| `GET /price?token_id=&side=buy\|sell`, `GET /midpoint?token_id=` | spot quotes; batch variants exist |

Book shape (verified):

```json
{ "market": "<conditionId>", "asset_id": "<token_id>", "timestamp": "1783315537923",
  "bids": [{"price": "0.001", "size": "1026935.09"}, ...],
  "asks": [{"price": "0.999", "size": "19394597.59"}, ...] }
```

- String decimals; `timestamp` is **milliseconds**.
- **Levels are sorted worst→best: the best bid/ask is the LAST element.**
  Verified live — do not assume top-of-book is index 0.
- `prices-history` returns `{"history": [{"t": <unix_sec>, "p": <float>}]}`.

### Rate limits

Cloudflare throttling — excess requests are **delayed/queued, not rejected**.
Gamma: 4000 req/10s general, `/markets` 300 req/10s, `/events` 500 req/10s.
CLOB market data: 500–1500 req/10s per endpoint.
Source: https://docs.polymarket.com/api-reference/rate-limits

### Fees (for M3 fee model)

- **Makers never pay. Takers only.**
- `fee = contracts × feeRate × p × (1−p)`, rounded to 5 dp, min 0.00001 USDC.
- `feeRate` by market category: crypto **0.07**, sports **0.03**,
  finance/politics/mentions/tech **0.04**, economics/culture/weather/other
  **0.05**, geopolitical **0**.
- Source: https://docs.polymarket.com/trading/fees
- **TODO(M3):** category must be derived per market (Gamma tags) — verify the
  exact field and mapping at implementation time; never guess a category
  silently.

---

## Cross-venue notes for the M1 unified schema

- Both venues quote prices in the 0–1 probability range → normalize to
  `Decimal` dollars everywhere; render as cents in the UI.
- Keys: Kalshi = `ticker` (human-readable); Polymarket = `conditionId` +
  per-outcome token ids. `data/event_map.yaml` pairs must store the Kalshi
  ticker, the Polymarket conditionId (or slug), **and which PM token is YES**.
- Kalshi books are bids-only (derive asks); Polymarket books have both sides
  but sorted worst→best. The adapter layer normalizes both to
  best-first bid/ask arrays.
- All outbound requests use an identifiable User-Agent:
  `tinli/0.1 (+https://tinli.dev)` — set in one shared HTTP client.
