import { useState } from 'react'
import type { Groups, Row } from '../pairs'
import { positiveEdge } from '../pairs'
import type { BasisStats, BookLevel, DivergenceItem, HistoryPoint, LockReport, MarketQuote, Orderbook, Pair } from '../types'
import { cents, clock, qty, signedCents } from '../format'
import BasisChart from './BasisChart'
import DepthChart from './DepthChart'
import LockSizing from './LockSizing'
import Signed from './Signed'
import Stat from './Stat'

const DEPTH = 8
const BOOKS_KEY = 'tinli-books-open'

function midOf(book: Orderbook | null): { mid: number | null; spread: number | null } {
  const bid = book?.bids[0] ? parseFloat(book.bids[0].price) : null
  const ask = book?.asks[0] ? parseFloat(book.asks[0].price) : null
  if (bid == null || ask == null) return { mid: null, spread: null }
  return { mid: ((bid + ask) / 2) * 100, spread: (ask - bid) * 100 }
}

function Rail({
  groups,
  selected,
  onSelect,
  onToggle,
}: {
  groups: Groups
  selected: string | null
  onSelect: (eventKey: string) => void
  onToggle: (group: 'unverified' | 'settled') => void
}) {
  const { verified, unverified, settled, visible } = groups
  const unverifiedShown = unverified.length > 0 && visible.includes(unverified[0])
  const settledShown = settled.length > 0 && visible.includes(settled[0])
  const row = (r: Row, muted: boolean) => {
    const active = r.pair.event_key === selected
    const executable = r.pair.criteria_verified && positiveEdge(r.item?.edge_at_size)
    return (
      <button
        key={r.pair.event_key}
        onClick={() => onSelect(r.pair.event_key)}
        className={`w-full flex items-center gap-2 px-3 h-7 border-l-2 text-left ${
          active ? 'border-l-primary bg-primary/10 text-hover' : 'border-l-transparent hover:bg-panel-2'
        } ${muted && !active ? 'text-muted' : ''}`}
      >
        <span className="truncate text-[12px]">{r.pair.question}</span>
        <span className={`ml-auto num text-[11px] ${executable ? 'text-gold' : 'text-dim'}`}>
          {signedCents(r.item?.edge_at_size)}
        </span>
      </button>
    )
  }
  const divider = (label: string, open: boolean, toggle: () => void) => (
    <button onClick={toggle} className="w-full flex items-center gap-2 px-3 h-6 label hover:text-hover bg-panel-2/50">
      <span className="w-3 num">{open ? '−' : '+'}</span>
      {label}
    </button>
  )
  return (
    <aside className="panel overflow-y-auto">
      <div className="section-head">
        <span className="label">Pairs</span>
        <span className="text-[11px] text-muted">{verified.length} verified</span>
      </div>
      {verified.map((r) => row(r, false))}
      {unverified.length > 0 && divider(`Unverified · ${unverified.length}`, unverifiedShown, () => onToggle('unverified'))}
      {unverifiedShown && unverified.map((r) => row(r, true))}
      {settled.length > 0 && divider(`Settled · ${settled.length}`, settledShown, () => onToggle('settled'))}
      {settledShown && settled.map((r) => row(r, true))}
    </aside>
  )
}

function Ladder({ label, quote, book }: { label: string; quote: MarketQuote; book: Orderbook | null }) {
  const fresh = book && quote && book.market_id === quote.id ? book : null
  const asks = fresh ? fresh.asks.slice(0, DEPTH) : []
  const bids = fresh ? fresh.bids.slice(0, DEPTH) : []
  const maxSize = Math.max(1, ...[...asks, ...bids].map((l) => parseFloat(l.size)))
  const row = (level: BookLevel, side: 'bid' | 'ask') => (
    <div key={`${side}${level.price}`} className="relative flex num text-[11px] leading-[20px] px-2.5">
      <div
        className={`absolute inset-y-[3px] right-0 rounded-l-sm ${side === 'ask' ? 'bg-down/12' : 'bg-up/12'}`}
        style={{ width: `${(parseFloat(level.size) / maxSize) * 100}%` }}
      />
      <span className={`relative ${side === 'ask' ? 'text-down' : 'text-up'}`}>{cents(level.price)}</span>
      <span className="relative ml-auto text-muted">{qty(level.size)}</span>
    </div>
  )
  return (
    <div className="flex-1 min-w-0 border border-line rounded-sm">
      <div className="flex items-center border-b border-line px-2.5 h-7">
        <span className="label">{label} book</span>
        <span className="ml-auto label">price / size</span>
      </div>
      {!fresh ? (
        <div className="p-2.5 text-muted text-[11px]">no book</div>
      ) : (
        <div className="py-1">
          {[...asks].reverse().map((l) => row(l, 'ask'))}
          <div className="border-t border-line my-0.5" />
          {bids.map((l) => row(l, 'bid'))}
        </div>
      )}
    </div>
  )
}

export default function MarketPage({
  pair,
  item,
  lock,
  history,
  historyStats,
  kalshiBook,
  pmBook,
  bankroll,
  groups,
  selected,
  onSelect,
  onToggle,
  onClose,
}: {
  pair: Pair
  item: DivergenceItem | null
  lock: LockReport | null
  history: HistoryPoint[]
  historyStats: BasisStats | null
  kalshiBook: Orderbook | null
  pmBook: Orderbook | null
  bankroll: number | null
  groups: Groups
  selected: string | null
  onSelect: (eventKey: string) => void
  onToggle: (group: 'unverified' | 'settled') => void
  onClose: () => void
}) {
  const [books, setBooks] = useState(() => localStorage.getItem(BOOKS_KEY) === '1')
  const freshK = kalshiBook && pair.kalshi && kalshiBook.market_id === pair.kalshi.id ? kalshiBook : null
  const freshP = pmBook && pair.polymarket && pmBook.market_id === pair.polymarket.id ? pmBook : null
  const asOf = freshK?.fetched_at ?? freshP?.fetched_at
  const k = midOf(freshK)
  const p = midOf(freshP)
  const basis = k.mid != null && p.mid != null ? k.mid - p.mid : null
  const freshLock = lock && lock.event_key === pair.event_key ? lock : null
  const toggleBooks = () => {
    const next = !books
    localStorage.setItem(BOOKS_KEY, next ? '1' : '0')
    setBooks(next)
  }
  const quote = (label: string, book: Orderbook | null, m: { mid: number | null; spread: number | null }) => (
    <Stat
      label={label}
      value={m.mid == null ? '—' : m.mid.toFixed(1)}
      size="lg"
      sub={
        <>
          {book?.bids[0] ? <span className="text-up">{cents(book.bids[0].price)} bid</span> : 'no bid'}
          <span className="mx-1.5">·</span>
          {book?.asks[0] ? <span className="text-down">{cents(book.asks[0].price)} ask</span> : 'no ask'}
          {m.spread != null && <span className="mx-1.5">·</span>}
          {m.spread != null && `${m.spread.toFixed(1)}¢ spread`}
        </>
      }
    />
  )

  return (
    <main className="flex-1 grid grid-cols-[14rem_minmax(0,1fr)] gap-px min-h-0">
      <Rail groups={groups} selected={selected} onSelect={onSelect} onToggle={onToggle} />
      <section className="panel overflow-y-auto">
        <div className="p-4 flex flex-col gap-5">
          <div className="flex items-start gap-4">
            <button onClick={onClose} className="btn mt-1" title="back to the board (esc)">
              ← Board
            </button>
            <div className="min-w-0">
              <h1 className="text-[18px] leading-snug text-text">{pair.question}</h1>
              <div className="text-[11px] text-muted mt-0.5 flex items-baseline gap-3">
                <span>yes-side books · as of {clock(asOf)}</span>
                {!pair.criteria_verified && <span className="label text-gold">Unverified</span>}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-x-12 gap-y-3">
            {quote('Kalshi', freshK, k)}
            <Stat
              label="Basis"
              value={<Signed value={basis} text={basis == null ? '—' : `${basis > 0 ? '+' : ''}${basis.toFixed(1)}¢`} />}
              sub="Kalshi mid − Polymarket mid"
            />
            {quote('Polymarket', freshP, p)}
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 items-start">
            <LockSizing lock={freshLock} item={item} bankroll={bankroll} />
            <div className="flex flex-col gap-3">
              <BasisChart points={history} stats={historyStats} />
              <div className="flex gap-1.5 items-stretch">
                <DepthChart label="Kalshi" book={freshK} />
                <DepthChart label="Polymarket" book={freshP} />
              </div>
              <button onClick={toggleBooks} className="flex items-center gap-2 label hover:text-hover">
                <span className="num w-3 text-left">{books ? '−' : '+'}</span>
                <span>Raw books</span>
              </button>
              {books && (
                <div className="flex gap-1.5 items-start">
                  <Ladder label="Kalshi" quote={pair.kalshi} book={freshK} />
                  <Ladder label="Polymarket" quote={pair.polymarket} book={freshP} />
                </div>
              )}
            </div>
          </div>

          {pair.notes && <div className="text-muted text-[11px] max-w-3xl">{pair.notes}</div>}
        </div>
      </section>
    </main>
  )
}
