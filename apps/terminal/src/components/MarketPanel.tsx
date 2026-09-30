import { useState } from 'react'
import type { BookLevel, BasisStats, DivergenceItem, HistoryPoint, MarketQuote, Orderbook, Pair } from '../types'
import type { LockReport } from '../types.gen'
import { cents, clock, qty } from '../format'
import BasisChart from './BasisChart'
import DepthChart from './DepthChart'
import LockPanel from './LockPanel'
import Signed from './Signed'
import Stat from './Stat'

const DEPTH = 6
const DEPTH_KEY = 'tinli-depth-open'

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
      <div className="label">{label}</div>
      <div className="font-mono text-text text-[26px] leading-8">
        {mid == null ? '—' : mid.toFixed(1)}
      </div>
      <div className="font-mono text-[11px] text-muted">
        {book?.bids[0] ? <span className="text-up">{cents(book.bids[0].price)} bid</span> : 'no bid'}
        <span className="mx-1.5">·</span>
        {book?.asks[0] ? <span className="text-down">{cents(book.asks[0].price)} ask</span> : 'no ask'}
        {spread != null && <span className="mx-1.5">·</span>}
        {spread != null && `${spread.toFixed(1)}¢ spread`}
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
        <span className="label">{label}</span>
        <span className="ml-auto label">price / size</span>
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

/** Top-of-book lock summary, shown while the depth-walked report is in flight. */
function LockEconomics({ item }: { item: DivergenceItem }) {
  const dir =
    item.direction === 'buy_yes_kalshi_no_polymarket'
      ? 'YES on Kalshi, NO on Polymarket'
      : item.direction === 'buy_yes_polymarket_no_kalshi'
        ? 'YES on Polymarket, NO on Kalshi'
        : 'no executable lock'
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-2">
        <span className="label">Lock</span>
        <span className="text-text text-[12px]">{dir}</span>
        {item.fee_assumed_worst_case && (
          <span className="label text-gold" title="Polymarket fee category unknown">
            worst-case fee
          </span>
        )}
      </div>
      <div className="flex gap-8">
        <Stat
          label="Edge / contract"
          value={
            <Signed
              value={item.fee_adjusted_edge}
              text={item.fee_adjusted_edge == null ? '—' : `${cents(item.fee_adjusted_edge, 2)}¢`}
            />
          }
        />
        <Stat label="Max size" value={qty(item.max_lock_size)} />
        <Stat
          label="Edge at size"
          value={
            <Signed
              value={item.edge_at_size}
              text={item.edge_at_size == null ? '—' : `${cents(item.edge_at_size, 2)}¢`}
            />
          }
        />
      </div>
    </div>
  )
}

export default function MarketPanel({
  pair,
  item,
  history,
  historyStats,
  kalshiBook,
  pmBook,
  lock,
}: {
  pair: Pair | null
  item: DivergenceItem | null
  history: HistoryPoint[]
  historyStats: BasisStats | null
  kalshiBook: Orderbook | null
  pmBook: Orderbook | null
  lock: LockReport | null
}) {
  // depth curves and raw ladders are the second layer: off by default, one
  // toggle reveals both venues at once, remembered across pairs and reloads
  const [depth, setDepth] = useState(() => localStorage.getItem(DEPTH_KEY) === '1')
  if (!pair) return <div className="p-3 text-muted text-[12px]">select a pair</div>
  // guard against stale books from a previous selection still in state
  const freshK = kalshiBook && pair.kalshi && kalshiBook.market_id === pair.kalshi.id ? kalshiBook : null
  const freshP = pmBook && pair.polymarket && pmBook.market_id === pair.polymarket.id ? pmBook : null
  const asOf = freshK?.fetched_at ?? freshP?.fetched_at
  const k = midOf(freshK)
  const p = midOf(freshP)
  const basis = k.mid != null && p.mid != null ? k.mid - p.mid : null
  const toggleDepth = () => {
    const next = !depth
    localStorage.setItem(DEPTH_KEY, next ? '1' : '0')
    setDepth(next)
  }
  return (
    <div className="p-3 flex flex-col gap-3 h-full">
      <div>
        <h2 className="text-text text-[16px] leading-snug">{pair.question}</h2>
        <div className="text-muted text-[11px] mt-1 flex items-baseline gap-3">
          <span>yes-side books · as of {clock(asOf)}</span>
          {!pair.criteria_verified && <span className="label text-gold">Unverified</span>}
        </div>
      </div>

      <div className="flex items-stretch gap-1.5">
        <VenueQuote label="Kalshi" book={freshK} />
        <div className="flex flex-col items-center justify-center px-2">
          <div className="label">Basis</div>
          <Signed
            value={basis}
            text={basis == null ? '—' : `${basis > 0 ? '+' : ''}${basis.toFixed(1)}¢`}
            className="font-mono text-[15px]"
          />
        </div>
        <VenueQuote label="Polymarket" book={freshP} />
      </div>

      <BasisChart points={history} stats={historyStats} />

      {lock && lock.event_key === pair.event_key && lock.points.length > 0 ? (
        <LockPanel lock={lock} />
      ) : (
        item && <LockEconomics item={item} />
      )}

      <button
        onClick={toggleDepth}
        className="flex items-center gap-2 label hover:text-hover border-t border-line pt-2"
      >
        <span className="font-mono w-3 text-left">{depth ? '−' : '+'}</span>
        <span>Depth</span>
      </button>

      {depth && (
        <>
          <div className="flex gap-1.5 items-stretch">
            <DepthChart label="Kalshi" book={freshK} />
            <DepthChart label="Polymarket" book={freshP} />
          </div>

          <div className="flex gap-1.5 items-start">
            <Ladder label="Kalshi" quote={pair.kalshi} book={freshK} />
            <Ladder label="Polymarket" quote={pair.polymarket} book={freshP} />
          </div>
        </>
      )}

      {pair.notes && <div className="text-muted text-[11px]">{pair.notes}</div>}
    </div>
  )
}
