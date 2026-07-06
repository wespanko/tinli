import { useEffect, useState, type ReactNode } from 'react'

type Health = { status: string; mode: 'live' | 'demo' }

type MarketQuote = {
  yes_price: string
  best_bid: string | null
  best_ask: string | null
  status: string
  icon_url: string | null
} | null

type Pair = {
  event_key: string
  question: string
  criteria_verified: boolean
  kalshi: MarketQuote
  polymarket: MarketQuote
}

type View = 'cards' | 'table'

const POLL_MS = 3000

function cents(v: string | null | undefined): string {
  if (v == null) return '—'
  return (parseFloat(v) * 100).toFixed(1)
}

function kalshiMid(m: MarketQuote): number | null {
  if (!m || m.best_bid == null || m.best_ask == null) return null
  return (parseFloat(m.best_bid) + parseFloat(m.best_ask)) / 2
}

function basisCents(p: Pair): number | null {
  const mid = kalshiMid(p.kalshi)
  if (mid == null || !p.polymarket) return null
  return (mid - parseFloat(p.polymarket.yes_price)) * 100
}

function sortPairs(data: Pair[]): Pair[] {
  return [...data].sort((a, b) => {
    if (a.criteria_verified !== b.criteria_verified) return a.criteria_verified ? -1 : 1
    return Math.abs(basisCents(b) ?? 0) - Math.abs(basisCents(a) ?? 0)
  })
}

function Panel({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <section className="flex flex-col border border-line bg-panel rounded-sm min-h-0">
      <header className="border-b border-line px-2 py-1 text-muted text-[11px] tracking-widest">
        {title}
      </header>
      <div className="flex-1 overflow-y-auto text-muted">{children}</div>
    </section>
  )
}

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

function WatchTable({ pairs }: { pairs: Pair[] }) {
  return (
    <table className="w-full text-[12px] leading-5">
      <thead>
        <tr className="text-muted text-[10px] tracking-wider sticky top-0 bg-panel">
          <th className="text-left px-2 py-1 font-normal">PAIR</th>
          <th className="text-right px-1 py-1 font-normal">K BID</th>
          <th className="text-right px-1 py-1 font-normal">K ASK</th>
          <th className="text-right px-1 py-1 font-normal">PM</th>
          <th className="text-right px-2 py-1 font-normal">Δ¢</th>
        </tr>
      </thead>
      <tbody>
        {pairs.map((p) => {
          const basis = basisCents(p)
          return (
            <tr key={p.event_key} className="border-t border-line/50 text-text hover:bg-line/20">
              <td className="px-2 py-0.5 whitespace-nowrap overflow-hidden text-ellipsis max-w-44">
                {!p.criteria_verified && (
                  <span className="text-gold mr-1" title="resolution criteria not verified">
                    !
                  </span>
                )}
                {p.event_key}
              </td>
              <td className="text-right px-1 tabular-nums">{cents(p.kalshi?.best_bid)}</td>
              <td className="text-right px-1 tabular-nums">{cents(p.kalshi?.best_ask)}</td>
              <td className="text-right px-1 tabular-nums">{cents(p.polymarket?.yes_price)}</td>
              <td
                className={`text-right px-2 tabular-nums ${
                  basis != null && Math.abs(basis) >= 1 ? 'text-gold' : 'text-muted'
                }`}
              >
                {basis == null ? '—' : basis.toFixed(1)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [pairs, setPairs] = useState<Pair[]>([])
  const [view, setView] = useState<View>('cards')

  useEffect(() => {
    let alive = true
    const tick = () => {
      fetch('/healthz')
        .then((r) => r.json())
        .then((h) => alive && setHealth(h))
        .catch(() => alive && setHealth(null))
      fetch('/v1/pairs')
        .then((r) => r.json())
        .then((data: Pair[]) => alive && setPairs(sortPairs(data)))
        .catch(() => {})
    }
    tick()
    const id = setInterval(tick, POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  return (
    <div className="h-screen flex flex-col gap-1 p-1">
      <header className="flex items-center gap-3 border border-line bg-panel rounded-sm px-2 py-1">
        <span className="text-gold font-bold tracking-widest">TINLI</span>
        <span className="text-muted text-[11px]">KALSHI × POLYMARKET</span>
        <nav className="ml-4 flex text-[11px] border border-line rounded-sm overflow-hidden">
          {(['cards', 'table'] as View[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-2 py-0.5 tracking-wider uppercase ${
                view === v ? 'bg-primary text-text' : 'text-muted hover:text-hover'
              }`}
            >
              {v}
            </button>
          ))}
        </nav>
        <span className="ml-auto text-[11px]">
          {health === null ? (
            <span className="text-muted">API OFFLINE</span>
          ) : health.mode === 'demo' ? (
            <span className="border border-gold text-gold px-1.5 py-0.5 rounded-sm">
              SIMULATED DATA
            </span>
          ) : (
            <span className="text-primary">LIVE</span>
          )}
        </span>
      </header>
      {view === 'cards' ? (
        <main className="flex-1 overflow-y-auto min-h-0">
          <div className="grid grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-1">
            {pairs.length ? (
              pairs.map((p) => <PairCard key={p.event_key} pair={p} />)
            ) : (
              <div className="text-muted p-3">loading pairs…</div>
            )}
          </div>
        </main>
      ) : (
        <main className="flex-1 grid grid-cols-[minmax(340px,1fr)_2fr_1fr] gap-1 min-h-0">
          <Panel title={`WATCHLIST · ${pairs.length} PAIRS`}>
            <WatchTable pairs={pairs} />
          </Panel>
          <Panel title="MARKET">
            <div className="p-2">price chart + orderbooks land in M5</div>
          </Panel>
          <Panel title="DIVERGENCE / RISK">
            <div className="p-2">screener + risk panel land in M5</div>
          </Panel>
        </main>
      )}
    </div>
  )
}
