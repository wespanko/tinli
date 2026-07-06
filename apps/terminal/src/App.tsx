import { useEffect, useState, type ReactNode } from 'react'

type Health = { status: string; mode: 'live' | 'demo' }

type MarketQuote = {
  yes_price: string
  best_bid: string | null
  best_ask: string | null
  status: string
} | null

type Pair = {
  event_key: string
  question: string
  criteria_verified: boolean
  kalshi: MarketQuote
  polymarket: MarketQuote
}

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

function Watchlist({ pairs }: { pairs: Pair[] }) {
  if (!pairs.length) return <div className="p-2">loading pairs…</div>
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

  useEffect(() => {
    let alive = true
    const tick = () => {
      fetch('/healthz')
        .then((r) => r.json())
        .then((h) => alive && setHealth(h))
        .catch(() => alive && setHealth(null))
      fetch('/v1/pairs')
        .then((r) => r.json())
        .then((data: Pair[]) => {
          if (!alive) return
          const sorted = [...data].sort((a, b) => {
            if (a.criteria_verified !== b.criteria_verified) return a.criteria_verified ? -1 : 1
            return Math.abs(basisCents(b) ?? 0) - Math.abs(basisCents(a) ?? 0)
          })
          setPairs(sorted)
        })
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
      <main className="flex-1 grid grid-cols-[minmax(340px,1fr)_2fr_1fr] gap-1 min-h-0">
        <Panel title={`WATCHLIST · ${pairs.length} PAIRS`}>
          <Watchlist pairs={pairs} />
        </Panel>
        <Panel title="MARKET">
          <div className="p-2">price chart + orderbooks land in M5</div>
        </Panel>
        <Panel title="DIVERGENCE / RISK">
          <div className="p-2">screener + risk panel land in M5</div>
        </Panel>
      </main>
    </div>
  )
}
