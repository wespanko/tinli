// Hand-written mirrors of the API's JSON. Every Decimal crosses the wire as
// a STRING (see test_markets_prices_are_strings_not_floats) — parse at the
// formatting edge only, never store floats.

export type Health = { status: string; mode: 'live' | 'demo' }

export type MarketQuote = {
  id: string
  question: string
  status: string
  yes_price: string
  best_bid: string | null
  best_ask: string | null
  icon_url: string | null
} | null

export type Pair = {
  event_key: string
  question: string
  criteria_verified: boolean
  notes: string
  kalshi: MarketQuote
  polymarket: MarketQuote
}

export type VenueTop = {
  bid: string | null
  bid_size: string | null
  ask: string | null
  ask_size: string | null
}

export type Direction = 'buy_yes_kalshi_no_polymarket' | 'buy_yes_polymarket_no_kalshi'

export type DivergenceItem = {
  event_key: string
  question: string
  criteria_verified: boolean
  notes: string
  kalshi: VenueTop
  polymarket: VenueTop
  raw_basis_cents: string | null
  direction: Direction | null
  fee_adjusted_edge: string | null
  max_lock_size: string | null
  edge_at_size: string | null
  fee_assumed_worst_case: boolean
  fetched_at: string
}

export type Position = {
  market_id: string
  side: 'yes' | 'no'
  contracts: string
  entry_price: string
  est_prob: string | null
  notes: string
}

export type PositionRisk = {
  position: Position
  event_id: string | null
  question: string | null
  mark: string | null
  market_value: string | null
  cost_basis: string
  unrealized_pnl: string | null
  max_loss: string | null
  kelly_full: string | null
  kelly_half: string | null
}

export type EventExposure = {
  event_id: string
  prob_yes: string
  delta_if_yes: string
  delta_if_no: string
  net_yes_contracts: string
}

export type RiskReport = {
  positions: PositionRisk[]
  by_event: EventExposure[]
  total_market_value: string
  total_cost_basis: string
  total_unrealized_pnl: string
  max_loss: string
  var_95_parametric: string
  var_95_monte_carlo: string
  mc_draws: number
  mc_seed: number
  unmarked_positions: number
  assumptions: string[]
  fetched_at: string
}

export type BookLevel = { price: string; size: string }

export type Orderbook = {
  market_id: string
  venue: 'kalshi' | 'polymarket'
  bids: BookLevel[]
  asks: BookLevel[]
  fetched_at: string
}
