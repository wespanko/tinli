import type { BookLevel, DivergenceItem, MarketQuote, Orderbook, Pair } from '../types'
import { cents, clock, qty } from '../format'
import DepthChart from './DepthChart'
import Signed from './Signed'

const DEPTH = 6

type Mid = { mid: number | null; spread: number | null }

function midOf(book: Orderbook | null): Mid {
  const bid = book?.bids[0] ? parseFloat(book.bids[0].price) : null
  const ask = book?.asks[0] ? parseFloat(book.asks[0].price) : null
  if (bid == null || ask == null) return { mid: null, spread: null }
  return { mid: ((bid + ask) / 2) * 100, spread: (ask - bid) * 100 }
}

function VenueQuote({ label, book }: { label: string; book: Orderbook | null }) {
  const { mid, spread } = midOf(book)
  return (
    <div className="flex-1 bg-panel-2 border border-line rounded-sm px-3 py-2">
      <div className="text-muted text-[10px] tracking-[0.15em]">{label}</div>
      {/* big standalone number: mono, proportional figures, not tabular */}
      <div className="font-mono text-text text-[26px] leading-8">
        {mid == null ? '—' : mid.toFixed(1)}
      </div>
      <div className="font-mono text-[11px] text-muted">
        {book?.bids[0] ? <span className="text-up">{cents(book.bids[0].price)} bid</span> : 'no bid'}
        <span className="mx-1.5">·</span>
        {book?.asks[0] ? <span className="text-down">{cents(book.asks[0].price)} ask</span> : 'no ask'}
        {spread != null && <span className="mx-1.5">·</span>}
        {spread != null && `${spread.toFixed(1)}¢ sprd`}
      </div>
    </div>
  )
}

function Ladder({
  label,
  quote,
  book,
}: {
  label: string
  quote: MarketQuote
  book: Orderbook | null
}) {
  // guard against a stale book from a previous selection still in state
  const fresh = book && quote && book.market_id === quote.id ? book : null
  const asks = fresh ? fresh.asks.slice(0, DEPTH) : []
  const bids = fresh ? fresh.bids.slice(0, DEPTH) : []
  const maxSize = Math.max(1, ...[...asks, ...bids].map((l) => parseFloat(l.size)))

  const row = (level: BookLevel, side: 'bid' | 'ask') => (
    <div
      key={`${side}${level.price}`}
      className="relative flex font-mono text-[12px] leading-[22px] px-2.5"
    >
      <div
        className={`absolute inset-y-[3px] right-0 rounded-l-sm ${
          side === 'ask' ? 'bg-down/12' : 'bg-up/12'
        }`}
        style={{ width: `${(parseFloat(level.size) / maxSize) * 100}%` }}
      />
      <span className={`relative tabular-nums ${side === 'ask' ? 'text-down' : 'text-up'}`}>
        {cents(level.price)}
      </span>
      <span className="relative ml-auto tabular-nums text-muted">{qty(level.size)}</span>
    </div>
  )

  return (
    <div className="flex-1 min-w-0 border border-line rounded-sm flex flex-col">
      <div className="flex items-center border-b border-line px-2.5 h-7">
        <span className="text-muted text-[10px] tracking-[0.15em]">{label}</span>
        <span className="ml-auto text-[10px] text-muted">PRICE / SIZE</span>
      </div>
      {!fresh ? (
        <div className="p-2.5 text-muted text-[11px]">no book</div>
      ) : (
        <div className="py-1">
          {/* asks worst-first so the best ask sits against the spread line */}
          {[...asks].reverse().map((l) => row(l, 'ask'))}
          <div className="border-t border-line my-0.5" />
          {bids.map((l) => row(l, 'bid'))}
        </div>
      )}
    </div>
  )
}

function LockEconomics({ item }: { item: DivergenceItem }) {
  const dir =
    item.direction === 'buy_yes_kalshi_no_polymarket'
      ? 'YES @ KALSHI + NO @ POLYMARKET'
      : item.direction === 'buy_yes_polymarket_no_kalshi'
        ? 'YES @ POLYMARKET + NO @ KALSHI'
        : 'no executable lock (missing book side)'
  const stat = (label: string, node: React.ReactNode) => (
    <div className="bg-panel-2 border border-line rounded-sm px-3 py-1.5">
      <div className="text-muted text-[10px] tracking-[0.12em]">{label}</div>
      <div className="font-mono text-[15px]">{node}</div>
    </div>
  )
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1.5">
        <span className="text-muted text-[10px] tracking-[0.15em]">LOCK</span>
        <span className="text-text text-[12px]">{dir}</span>
        {item.fee_assumed_worst_case && (
          <span className="text-gold text-[10px]" title="PM fee category unknown">
            WORST-CASE FEE
          </span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {stat(
          'EDGE / CONTRACT',
          <Signed
            value={item.fee_adjusted_edge}
            text={item.fee_adjusted_edge == null ? '—' : `${cents(item.fee_adjusted_edge, 2)}¢`}
          />,
        )}
        {stat(
          'MAX LOCK SIZE',
          <span className="tabular-nums text-text">{qty(item.max_lock_size)}</span>,
        )}
        {stat(
          'EDGE @ SIZE',
          <Signed
            value={item.edge_at_size}
            text={item.edge_at_size == null ? '—' : `${cents(item.edge_at_size, 2)}¢`}
          />,
        )}
      </div>
      <div className="text-muted text-[11px] mt-1.5">
        fee-adjusted, executable asks only — a positive edge locks $1 at resolution either way
      </div>
    </div>
  )
}

export default function MarketPanel({
  pair,
  item,
  kalshiBook,
  pmBook,
}: {
  pair: Pair | null
  item: DivergenceItem | null
  kalshiBook: Orderbook | null
  pmBook: Orderbook | null
}) {
  if (!pair) return <div className="p-3 text-muted text-[12px]">select a pair</div>
  // guard against stale books from a previous selection still in state
  const freshK = kalshiBook && pair.kalshi && kalshiBook.market_id === pair.kalshi.id ? kalshiBook : null
  const freshP = pmBook && pair.polymarket && pmBook.market_id === pair.polymarket.id ? pmBook : null
  const asOf = freshK?.fetched_at ?? freshP?.fetched_at
  const k = midOf(freshK)
  const p = midOf(freshP)
  const basis = k.mid != null && p.mid != null ? k.mid - p.mid : null
  return (
    <div className="p-3 flex flex-col gap-3 h-full">
      <div>
        <h2 className="text-text text-[16px] leading-snug">{pair.question}</h2>
        <div className="text-muted text-[11px] mt-1">
          {pair.event_key} · yes-side books · as of {clock(asOf)}
          {!pair.criteria_verified && (
            <span className="text-gold ml-2">! UNVERIFIED CRITERIA — GAP IS NOT EDGE</span>
          )}
        </div>
      </div>

      <div className="flex items-stretch gap-1.5">
        <VenueQuote label="KALSHI" book={freshK} />
        <div className="flex flex-col items-center justify-center px-2">
          <div className="text-muted text-[10px] tracking-[0.12em]">BASIS</div>
          <Signed
            value={basis == null ? null : String(basis)}
            text={basis == null ? '—' : `${basis > 0 ? '+' : ''}${basis.toFixed(1)}¢`}
            className="font-mono text-[15px]"
          />
        </div>
        <VenueQuote label="POLYMARKET" book={freshP} />
      </div>

      <div className="flex gap-1.5 items-stretch">
        <DepthChart label="KALSHI DEPTH" book={freshK} />
        <DepthChart label="POLYMARKET DEPTH" book={freshP} />
      </div>

      <div className="flex gap-1.5 items-start">
        <Ladder label="KALSHI BOOK" quote={pair.kalshi} book={freshK} />
        <Ladder label="POLYMARKET BOOK" quote={pair.polymarket} book={freshP} />
      </div>

      {item && <LockEconomics item={item} />}

      {pair.notes && <div className="text-muted text-[11px]">{pair.notes}</div>}
    </div>
  )
}
