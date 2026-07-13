import type { BookLevel, MarketQuote, Orderbook, Pair } from '../types'
import { cents, clock, qty } from '../format'

const DEPTH = 6

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
  const bestBid = bids[0] ? parseFloat(bids[0].price) : null
  const bestAsk = asks[0] ? parseFloat(asks[0].price) : null
  const mid = bestBid != null && bestAsk != null ? ((bestBid + bestAsk) / 2) * 100 : null
  const spread = bestBid != null && bestAsk != null ? (bestAsk - bestBid) * 100 : null

  const row = (level: BookLevel, side: 'bid' | 'ask') => (
    <div key={`${side}${level.price}`} className="relative flex text-[12px] leading-5 px-2">
      <div
        className="absolute inset-y-0 right-0 bg-line/40"
        style={{ width: `${(parseFloat(level.size) / maxSize) * 100}%` }}
      />
      <span className={`relative tabular-nums ${side === 'ask' ? 'text-muted' : 'text-text'}`}>
        {cents(level.price)}
      </span>
      <span className="relative ml-auto tabular-nums text-muted">{qty(level.size)}</span>
    </div>
  )

  return (
    <div className="flex-1 min-w-0 border border-line rounded-sm flex flex-col">
      <div className="flex items-baseline gap-2 border-b border-line px-2 py-1">
        <span className="text-muted text-[10px] tracking-widest">{label}</span>
        <span className="ml-auto text-[11px] tabular-nums text-text">
          {mid == null ? '—' : mid.toFixed(2)}
        </span>
        <span className="text-[10px] tabular-nums text-muted">
          {spread == null ? '' : `±${(spread / 2).toFixed(1)}`}
        </span>
      </div>
      {!fresh ? (
        <div className="p-2 text-muted text-[11px]">no book</div>
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

export default function MarketPanel({
  pair,
  kalshiBook,
  pmBook,
}: {
  pair: Pair | null
  kalshiBook: Orderbook | null
  pmBook: Orderbook | null
}) {
  if (!pair) return <div className="p-2 text-muted text-[12px]">select a pair</div>
  const asOf = kalshiBook?.fetched_at ?? pmBook?.fetched_at
  return (
    <div className="p-2 flex flex-col gap-2 h-full">
      <div>
        <h2 className="text-text text-[14px] leading-tight">{pair.question}</h2>
        <div className="text-muted text-[11px] mt-0.5">
          {pair.event_key} · yes-side books · as of {clock(asOf)}
          {!pair.criteria_verified && (
            <span className="text-gold ml-2">! UNVERIFIED CRITERIA</span>
          )}
        </div>
      </div>
      <div className="flex gap-2 items-start">
        <Ladder label="KALSHI" quote={pair.kalshi} book={kalshiBook} />
        <Ladder label="POLYMARKET" quote={pair.polymarket} book={pmBook} />
      </div>
      {pair.notes && <div className="text-muted text-[11px]">{pair.notes}</div>}
    </div>
  )
}
