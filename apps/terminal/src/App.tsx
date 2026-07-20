import { useEffect, useRef, useState } from 'react'

import type {
  BasisStats,
  DivergenceItem,
  Health,
  HistoryPoint,
  HistoryResponse,
  LockReport,
  Orderbook,
  Pair,
  RiskReport,
  StreamUpdate,
} from './types'
import { cents } from './format'
import DivergencePanel from './components/DivergencePanel'
import EdgeAlert, { liveEdges } from './components/EdgeAlert'
import IntroPanel from './components/IntroPanel'
import MarketPanel from './components/MarketPanel'
import PairCards from './components/PairCards'
import Panel from './components/Panel'
import RiskPanel from './components/RiskPanel'
import WatchTable, { sortPairs } from './components/WatchTable'

type View = 'terminal' | 'cards'

const POLL_MS = 3000
const STREAM_RETRY_MS = 15_000
const INTRO_KEY = 'tinli-intro-seen'
const ALERTS_KEY = 'tinli-alerts-on'

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
  const [riskError, setRiskError] = useState<string | null>(null)
  const [kalshiBook, setKalshiBook] = useState<Orderbook | null>(null)
  const [pmBook, setPmBook] = useState<Orderbook | null>(null)
  const [lock, setLock] = useState<LockReport | null>(null)
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [historyStats, setHistoryStats] = useState<BasisStats | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [view, setView] = useState<View>('terminal')
  const [showIntro, setShowIntro] = useState(() => localStorage.getItem(INTRO_KEY) !== '1')
  const [alertsOn, setAlertsOn] = useState(() => localStorage.getItem(ALERTS_KEY) === '1')
  const [streamed, setStreamed] = useState<StreamUpdate | null>(null)
  // ref mirror so the poll tick can skip work without re-arming its interval
  const streamOnRef = useRef(false)
  const streamOn = streamed !== null
  streamOnRef.current = streamOn

  // risk errors are surfaced, not swallowed: a 4xx names the user's
  // positions.yaml mistake, and the stale report must be labeled as such.
  // Also called directly after a book save so the panel updates immediately.
  const fetchRisk = () => {
    fetch('/v1/risk')
      .then(async (r) => {
        if (r.ok) {
          setRisk((await r.json()) as RiskReport)
          setRiskError(null)
        } else {
          const body = await r.json().catch(() => null)
          setRiskError(body?.detail ?? `HTTP ${r.status}`)
        }
      })
      .catch(() => {}) // network-level failure: header already shows API OFFLINE
  }

  // one 3s heartbeat for everything except the per-pair books. While the
  // SSE stream is delivering, pairs + divergence come from it instead and
  // the tick skips those fetches — health and risk stay polled either way.
  useEffect(() => {
    let alive = true
    const tick = () => {
      getJson<Health>('/healthz').then((h) => alive && setHealth(h))
      if (!streamOnRef.current) {
        getJson<Pair[]>('/v1/pairs').then((d) => {
          if (!alive || !d || streamOnRef.current) return
          const sorted = sortPairs(d)
          setPairs(sorted)
          // pin the initial selection ONCE — the list re-sorts every poll, and
          // a pairs[0] fallback would flip the MARKET panel under the reader
          setSelected((prev) => prev ?? sorted[0]?.event_key ?? null)
        })
        getJson<DivergenceItem[]>('/v1/divergence').then(
          (d) => alive && d && !streamOnRef.current && setDivergence(d),
        )
      }
      fetchRisk()
    }
    tick()
    const id = setInterval(tick, POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // live streaming (M8): subscribe to /v1/stream in live mode. Every failure
  // path — demo 503, hub down, proxy without SSE — lands back on the 3s
  // polling above; the stream is an upgrade, never a requirement.
  useEffect(() => {
    if (health?.mode !== 'live' || !health.stream) return
    let es: EventSource | null = null
    let retry: ReturnType<typeof setTimeout> | null = null
    let alive = true
    const connect = () => {
      if (!alive) return
      es = new EventSource('/v1/stream')
      es.onmessage = (ev) => {
        if (!alive) return
        const update = JSON.parse(ev.data) as StreamUpdate
        setStreamed(update)
        const sorted = sortPairs(update.pairs)
        setPairs(sorted)
        setSelected((prev) => prev ?? sorted[0]?.event_key ?? null)
        setDivergence(update.divergence)
      }
      es.onerror = () => {
        // CONNECTING means the browser is retrying by itself; CLOSED (e.g.
        // an HTTP error response) needs our own slow retry
        if (es?.readyState === EventSource.CLOSED) {
          es.close()
          es = null
          setStreamed(null)
          if (alive) retry = setTimeout(connect, STREAM_RETRY_MS)
        }
      }
    }
    connect()
    return () => {
      alive = false
      es?.close()
      if (retry) clearTimeout(retry)
      setStreamed(null)
    }
  }, [health?.mode, health?.stream])

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
    getJson<LockReport>(`/v1/lock/${encodeURIComponent(activePair.event_key)}`).then(
      (l) => alive && l && setLock(l),
    )
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
    setHistoryStats(null)
    const load = () =>
      getJson<HistoryResponse>(`/v1/history/${encodeURIComponent(activeKey)}?hours=24`).then(
        (h) => {
          if (!alive || !h || h.event_key !== activeKey) return
          setHistory(h.points)
          setHistoryStats(h.stats)
        },
      )
    load()
    const id = setInterval(load, 30_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [activeKey])

  // browser notification when a verified pair's executable edge turns
  // positive — the signal this product exists to catch. Alert on ENTER into
  // the positive set only; the banner persists while the edge lives.
  const edges = liveEdges(divergence)
  const prevEdgeKeys = useRef<Set<string>>(new Set())
  useEffect(() => {
    const keys = new Set(edges.map((e) => e.event_key))
    if (alertsOn && 'Notification' in window && Notification.permission === 'granted') {
      for (const e of edges) {
        if (!prevEdgeKeys.current.has(e.event_key)) {
          new Notification('Tinli — executable lock edge', {
            body: `${e.question}: +${cents(e.edge_at_size, 2)}¢/contract at size ${e.max_lock_size}`,
          })
        }
      }
    }
    prevEdgeKeys.current = keys
  }, [divergence, alertsOn]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleAlerts = () => {
    const next = !alertsOn
    if (next && 'Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }
    localStorage.setItem(ALERTS_KEY, next ? '1' : '0')
    setAlertsOn(next)
  }

  const settled = pairs.filter(
    (p) => p.kalshi?.status !== 'open' && p.polymarket?.status !== 'open',
  ).length

  const closeIntro = () => {
    localStorage.setItem(INTRO_KEY, '1')
    setShowIntro(false)
  }

  return (
    <div className="h-screen flex flex-col gap-1 p-1">
      {showIntro && <IntroPanel onClose={closeIntro} />}
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
        <button
          onClick={toggleAlerts}
          title="browser notification when a verified pair's executable edge turns positive"
          className={`ml-3 border rounded-sm px-2 py-0.5 text-[10px] tracking-[0.12em] ${
            alertsOn ? 'border-gold text-gold' : 'border-line text-muted hover:text-hover'
          }`}
        >
          ALERTS {alertsOn ? 'ON' : 'OFF'}
        </button>
        <span className="ml-auto text-[11px]">
          {health === null ? (
            <span className="text-down">API OFFLINE</span>
          ) : health.mode === 'demo' ? (
            <span className="border border-gold text-gold px-2 py-0.5 rounded-sm text-[10px] tracking-[0.12em]">
              SIMULATED DATA
            </span>
          ) : (() => {
            const stale = Object.entries(streamed?.venues ?? {}).filter(
              ([, v]) => v.state !== 'live',
            )
            if (streamOn && stale.length > 0) {
              const [name, v] = stale[0]
              return (
                <span
                  className="text-gold text-[10px] tracking-[0.12em]"
                  title="this venue's feed has not updated recently; quotes for it may be stale"
                >
                  ! {name.toUpperCase()} {v.age_s != null ? `STALE ${Math.round(v.age_s)}s` : 'CONNECTING'}
                </span>
              )
            }
            return (
              <span
                className="text-up text-[10px] tracking-[0.12em]"
                title={
                  streamOn
                    ? 'streaming: Polymarket websocket + Kalshi fast-poll, pushed on change'
                    : 'polling venue REST APIs every 3s'
                }
              >
                ● LIVE {streamOn ? '· STREAM' : '· POLL'}
              </span>
            )
          })()}
        </span>
      </header>
      <EdgeAlert edges={edges} onSelect={setSelected} />
      {view === 'cards' ? (
        <PairCards pairs={pairs} />
      ) : (
        <main className="flex-1 grid grid-cols-[minmax(320px,26rem)_minmax(360px,1fr)_minmax(400px,34rem)] gap-1 min-h-0">
          <Panel
            title={`WATCHLIST · ${pairs.length} PAIRS`}
            extra={settled > 0 ? `${settled} settled — re-curate (make curate)` : undefined}
          >
            <WatchTable pairs={pairs} selected={activeKey} onSelect={setSelected} />
          </Panel>
          <Panel title="MARKET">
            <MarketPanel
              pair={activePair}
              item={activeItem}
              history={history}
              historyStats={historyStats}
              kalshiBook={kalshiBook}
              pmBook={pmBook}
              lock={lock}
            />
          </Panel>
          <div className="flex flex-col gap-1 min-h-0">
            <Panel title="DIVERGENCE · FEE-ADJUSTED LOCK EDGES">
              <DivergencePanel items={divergence} selected={activeKey} onSelect={setSelected} />
            </Panel>
            <Panel title="RISK · SELF-REPORTED BOOK">
              <RiskPanel
                report={risk}
                error={riskError}
                pairs={pairs}
                readonly={health?.readonly ?? false}
                onSaved={fetchRisk}
              />
            </Panel>
          </div>
        </main>
      )}
      <footer className="flex items-center gap-3 border border-line bg-panel rounded-sm px-3 h-7 shrink-0 text-[10px] text-muted">
        <span>TINLI v0 · cross-venue analytics for prediction markets</span>
        <span>read-only public market data · quotes may be delayed · not investment advice</span>
        <button
          onClick={() => setShowIntro(true)}
          className="ml-auto tracking-[0.15em] hover:text-hover"
        >
          HELP
        </button>
      </footer>
    </div>
  )
}
