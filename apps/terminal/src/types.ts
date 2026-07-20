// Thin glue over the GENERATED API types (types.gen.ts) — UI-side aliases
// only. The wire shapes have one source of truth: the pydantic models
// (regenerate with `make types`). Do not hand-declare an API shape here.

import type { DivergenceItem, Market, OrderbookLevel, PairQuote } from './types.gen'

export type {
  AccountPosition,
  AccountPositionRisk,
  AccountReport,
  BasisStats,
  DivergenceItem,
  EventExposure,
  HistoryPoint,
  HistoryResponse,
  LockReport,
  Market,
  Orderbook,
  Position,
  PositionRisk,
  RiskReport,
  SizePoint,
  StreamUpdate,
  VenueStreamStatus,
  VenueTop,
} from './types.gen'

export type MarketQuote = Market | null
export type Pair = PairQuote
export type BookLevel = OrderbookLevel
export type Direction = NonNullable<DivergenceItem['direction']>

// /healthz returns a plain dict, not a pydantic model — hand-kept
export type Health = {
  status: string
  mode: 'live' | 'demo'
  readonly?: boolean
  stream?: boolean
  byok?: boolean
}
