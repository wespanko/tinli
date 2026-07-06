import { useEffect, useState, type ReactNode } from 'react'

type Health = { status: string; mode: 'live' | 'demo' }

function Panel({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <section className="flex flex-col border border-line bg-panel rounded-sm min-h-0">
      <header className="border-b border-line px-2 py-1 text-muted text-[11px] tracking-widest">
        {title}
      </header>
      <div className="flex-1 p-2 text-muted">{children}</div>
    </section>
  )
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    fetch('/healthz')
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null))
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
      <main className="flex-1 grid grid-cols-[1fr_2fr_1fr] gap-1 min-h-0">
        <Panel title="WATCHLIST">mapped pairs land in M5</Panel>
        <Panel title="MARKET">price chart + orderbooks land in M5</Panel>
        <Panel title="DIVERGENCE / RISK">screener + risk panel land in M5</Panel>
      </main>
    </div>
  )
}
