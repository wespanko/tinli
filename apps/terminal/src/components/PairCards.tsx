import type { Pair } from '../types'
import { cents } from '../format'
import { basisCents } from './WatchTable'

function DeltaChip({ basis }: { basis: number | null }) {
  if (basis == null) return <span className="text-muted text-sm">—</span>
  const hot = Math.abs(basis) >= 1
  return (
    <span
      className={`tabular-nums text-base px-1.5 py-0.5 rounded-sm border ${
        hot ? 'text-gold border-gold' : 'text-muted border-line'
      }`}
      title="Kalshi mid minus Polymarket price, in cents"
    >
      {basis > 0 ? '+' : ''}
      {basis.toFixed(1)}¢
    </span>
  )
}

function PairCard({ pair }: { pair: Pair }) {
  const basis = basisCents(pair)
  const icon = pair.polymarket?.icon_url
  const settled =
    pair.kalshi?.status !== 'open' || (pair.polymarket && pair.polymarket.status !== 'open')
  return (
    <article
      className={`border border-line bg-panel rounded-sm p-3 flex flex-col gap-2 ${
        settled ? 'opacity-50' : ''
      }`}
    >
      <div className="flex items-start gap-3">
        {icon ? (
          <img
            src={icon}
            alt=""
            className="w-12 h-12 rounded-sm object-cover border border-line shrink-0"
            loading="lazy"
          />
        ) : (
          <div className="w-12 h-12 rounded-sm border border-line bg-bg text-muted flex items-center justify-center text-lg shrink-0">
            {pair.event_key.slice(0, 2).toUpperCase()}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <h3 className="text-text text-[15px] leading-tight">{pair.question}</h3>
          <div className="text-muted text-[11px] mt-0.5 truncate">{pair.event_key}</div>
        </div>
        <DeltaChip basis={basis} />
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="border border-line rounded-sm py-1.5">
          <div className="text-muted text-[10px] tracking-wider">KALSHI BID</div>
          <div className="text-text text-xl tabular-nums">{cents(pair.kalshi?.best_bid)}</div>
        </div>
        <div className="border border-line rounded-sm py-1.5">
          <div className="text-muted text-[10px] tracking-wider">KALSHI ASK</div>
          <div className="text-text text-xl tabular-nums">{cents(pair.kalshi?.best_ask)}</div>
        </div>
        <div className="border border-line rounded-sm py-1.5">
          <div className="text-muted text-[10px] tracking-wider">POLYMARKET</div>
          <div className="text-text text-xl tabular-nums">{cents(pair.polymarket?.yes_price)}</div>
        </div>
      </div>
      {!pair.criteria_verified && (
        <div className="text-gold text-[11px]">
          ! UNVERIFIED — resolution criteria differ between venues; gap is not edge
        </div>
      )}
      {settled && <div className="text-muted text-[11px]">market no longer open</div>}
    </article>
  )
}

export default function PairCards({ pairs }: { pairs: Pair[] }) {
  return (
    <main className="flex-1 overflow-y-auto min-h-0">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-1">
        {pairs.length ? (
          pairs.map((p) => <PairCard key={p.event_key} pair={p} />)
        ) : (
          <div className="text-muted p-3">loading pairs…</div>
        )}
      </div>
    </main>
  )
}
