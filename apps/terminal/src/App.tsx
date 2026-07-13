import { useEffect, useState } from 'react'

import type {
  DivergenceItem,
  Health,
  HistoryPoint,
  HistoryResponse,
  Orderbook,
  Pair,
  RiskReport,
} from './types'
import DivergencePanel from './components/DivergencePanel'
import MarketPanel from './components/MarketPanel'
import PairCards from './components/PairCards'
import Panel from './components/Panel'
import RiskPanel from './components/RiskPanel'
import WatchTable, { sortPairs } from './components/WatchTable'

type View = 'terminal' | 'cards'

const POLL_MS = 3000

function getJson<T>(url: string): Promise<T | null> {
  return fetch(url)
    .then((r) => (r.ok ? (r.json() as Promise<T>) : null))
    .catch(() => null)
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [pairs, setPairs] = useState<Pair[]>([])
  const [divergence, setDivergence] = useState<DivergenceItem[]>([])
  const [risk, setRisk] = useState<RiskReport | null>(null)
  const [kalshiBook, setKalshiBook] = useState<Orderbook | null>(null)
  const [pmBook, setPmBook] = useState<Orderbook | null>(null)
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [view, setView] = useState<View>('terminal')

  // one 3s heartbeat for everything except the per-pair books
  useEffect(() => {
    let alive = true
    const tick = () => {
      getJson<Health>('/healthz').then((h) => alive && setHealth(h))
      getJson<Pair[]>('/v1/pairs').then((d) => alive && d && setPairs(sortPairs(d)))
      getJson<DivergenceItem[]>('/v1/divergence').then((d) => alive && d && setDivergence(d))
      getJson<RiskReport>('/v1/risk').then((d) => alive && d && setRisk(d))
    }
    tick()
    const id = setInterval(tick, POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const activeKey = selected ?? pairs[0]?.event_key ?? null
  const activePair = pairs.find((p) => p.event_key === activeKey) ?? null
  const activeItem = divergence.find((d) => d.event_key === activeKey) ?? null

  // books ride the same cadence: `pairs` is replaced every heartbeat, which
  // re-runs this effect — no second timer needed
  useEffect(() => {
    if (!activePair) return
    let alive = true
    if (activePair.kalshi) {
      getJson<Orderbook>(
        `/v1/markets/${encodeURIComponent(activePair.kalshi.id)}/orderbook`,
      ).then((b) => alive && b && setKalshiBook(b))
    }
    if (activePair.polymarket) {
      getJson<Orderbook>(
        `/v1/markets/${encodeURIComponent(activePair.polymarket.id)}/orderbook`,
      ).then((b) => alive && b && setPmBook(b))
    }
    return () => {
      alive = false
    }
  }, [pairs, activeKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // history moves at snapshot cadence, not tick cadence: refetch on selection
  // change and every 30s, not every 3s heartbeat
  useEffect(() => {
    if (!activeKey) return
    let alive = true
    setHistory([])
    const load = () =>
      getJson<HistoryResponse>(`/v1/history/${encodeURIComponent(activeKey)}?hours=24`).then(
        (h) => alive && h && h.event_key === activeKey && setHistory(h.points),
      )
    load()
    const id = setInterval(load, 30_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [activeKey])

  return (
    <div className="h-screen flex flex-col gap-1 p-1">
      <header className="flex items-center gap-3 border border-line bg-panel rounded-sm px-3 h-9 shrink-0">
        <span className="font-mono text-gold font-bold tracking-[0.2em] text-[14px]">TINLI</span>
        <span className="text-muted text-[11px] tracking-[0.1em]">KALSHI × POLYMARKET</span>
        <nav className="ml-4 flex text-[10px] border border-line rounded-sm overflow-hidden">
          {(['terminal', 'cards'] as View[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-2.5 py-1 tracking-[0.12em] uppercase ${
                view === v ? 'bg-primary text-text' : 'text-muted hover:text-hover'
              }`}
            >
              {v}
            </button>
          ))}
        </nav>
        <span className="ml-auto text-[11px]">
          {health === null ? (
            <span className="text-down">API OFFLINE</span>
          ) : health.mode === 'demo' ? (
            <span className="border border-gold text-gold px-2 py-0.5 rounded-sm text-[10px] tracking-[0.12em]">
              SIMULATED DATA
            </span>
          ) : (
            <span className="text-up text-[10px] tracking-[0.12em]">● LIVE</span>
          )}
        </span>
      </header>
      {view === 'cards' ? (
        <PairCards pairs={pairs} />
      ) : (
        <main className="flex-1 grid grid-cols-[minmax(320px,26rem)_minmax(360px,1fr)_minmax(400px,34rem)] gap-1 min-h-0">
          <Panel title={`WATCHLIST · ${pairs.length} PAIRS`}>
            <WatchTable pairs={pairs} selected={activeKey} onSelect={setSelected} />
          </Panel>
          <Panel title="MARKET">
            <MarketPanel
              pair={activePair}
              item={activeItem}
              history={history}
              kalshiBook={kalshiBook}
              pmBook={pmBook}
            />
          </Panel>
          <div className="flex flex-col gap-1 min-h-0">
            <Panel title="DIVERGENCE · FEE-ADJUSTED LOCK EDGES">
              <DivergencePanel items={divergence} selected={activeKey} onSelect={setSelected} />
            </Panel>
            <Panel title="RISK · SELF-REPORTED BOOK">
              <RiskPanel report={risk} />
            </Panel>
          </div>
        </main>
      )}
    </div>
  )
}
