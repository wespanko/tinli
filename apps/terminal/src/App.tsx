import { useEffect, useMemo, useRef, useState } from 'react'

import type {
  AccountReport,
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
import AccountPanel from './components/AccountPanel'
import CryptoView from './components/CryptoView'
import CurateView from './components/CurateView'
import EdgeAlert, { liveEdges } from './components/EdgeAlert'
import IntroPanel from './components/IntroPanel'
import MarketPanel from './components/MarketPanel'
import Panel from './components/Panel'
import Skeleton from './components/Skeleton'
import RiskPanel from './components/RiskPanel'
import PairList from './components/PairList'
import { groupRows, sortPairs } from './pairs'

type View = 'terminal' | 'crypto' | 'book' | 'curate'
const VIEWS: View[] = ['terminal', 'crypto', 'book', 'curate']
type Intro = 'off' | 'short' | 'full'

const POLL_MS = 3000
const STREAM_RETRY_MS = 15_000
const INTRO_KEY = 'tinli-intro-seen'
const ALERTS_KEY = 'tinli-alerts-on'
const SHOW_UNVERIFIED_KEY = 'tinli-show-unverified'
const SHOW_SETTLED_KEY = 'tinli-show-settled'

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
  const [account, setAccount] = useState<AccountReport | null>(null)
  const [riskError, setRiskError] = useState<string | null>(null)
  const [kalshiBook, setKalshiBook] = useState<Orderbook | null>(null)
  const [pmBook, setPmBook] = useState<Orderbook | null>(null)
  const [lock, setLock] = useState<LockReport | null>(null)
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [historyStats, setHistoryStats] = useState<BasisStats | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [view, setView] = useState<View>('terminal')
  const [intro, setIntro] = useState<Intro>(() =>
    localStorage.getItem(INTRO_KEY) !== '1' ? 'short' : 'off',
  )
  // the noise groups (unverified, settled) start collapsed; the choice sticks
  const [show, setShow] = useState({
    unverified: localStorage.getItem(SHOW_UNVERIFIED_KEY) === '1',
    settled: localStorage.getItem(SHOW_SETTLED_KEY) === '1',
  })
  const toggleGroup = (g: 'unverified' | 'settled') =>
    setShow((prev) => {
      const next = { ...prev, [g]: !prev[g] }
      localStorage.setItem(
        g === 'unverified' ? SHOW_UNVERIFIED_KEY : SHOW_SETTLED_KEY,
        next[g] ? '1' : '0',
      )
      return next
    })
  const [alertsOn, setAlertsOn] = useState(() => localStorage.getItem(ALERTS_KEY) === '1')
  const [filter, setFilter] = useState('')
  const filterRef = useRef<HTMLInputElement>(null)
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

  // live mode subscribes to /v1/stream. Every failure path — demo 503, hub
  // down, proxy without SSE — lands back on the 3s polling above; the
  // stream is an upgrade, never a requirement.
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

  // one ranked list: pairs joined with their lock edges, grouped so the
  // noise can collapse. '/' filter narrows it; MARKET keeps the active pair
  // even when the filter or a collapsed group hides it (deliberate: don't
  // yank the reader)
  const groups = useMemo(
    () => groupRows(pairs, divergence, filter, show),
    [pairs, divergence, filter, show],
  )

  const activeKey = selected ?? pairs[0]?.event_key ?? null
  const activePair = pairs.find((p) => p.event_key === activeKey) ?? null
  const activeItem = divergence.find((d) => d.event_key === activeKey) ?? null

  // terminal-style keys: j/k or arrows drive the list, / filters, 1-4
  // switch views, ? help, Esc closes/clears. Never while typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName)
      if (e.key === 'Escape') {
        if (typing) {
          t.blur()
          if (t === filterRef.current) setFilter('')
        } else if (intro !== 'off') setIntro('off')
        return
      }
      if (typing) return
      if (e.key === '/') {
        e.preventDefault()
        filterRef.current?.focus()
        return
      }
      if (e.key === '?') {
        setIntro((v) => (v === 'off' ? 'full' : 'off'))
        return
      }
      const numbered = VIEWS[parseInt(e.key, 10) - 1]
      if (numbered) setView(numbered)
      else if (['j', 'k', 'ArrowDown', 'ArrowUp'].includes(e.key)) {
        e.preventDefault()
        const list = groups.visible
        if (!list.length) return
        const dir = e.key === 'j' || e.key === 'ArrowDown' ? 1 : -1
        const idx = list.findIndex((r) => r.pair.event_key === activeKey)
        const next = list[Math.min(Math.max(idx + dir, 0), list.length - 1)] ?? list[0]
        setSelected(next.pair.event_key)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [groups, activeKey, intro])

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

  // account book (BYOK) moves at fill cadence, not tick cadence: 30s
  useEffect(() => {
    let alive = true
    const load = () =>
      getJson<AccountReport>('/v1/account').then((a) => alive && a && setAccount(a))
    load()
    const id = setInterval(load, 30_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [health?.byok]) // eslint-disable-line react-hooks/exhaustive-deps

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
  // positive. Alert on ENTER into the positive set only; the banner
  // persists while the edge lives.
  const edges = liveEdges(divergence)
  const prevEdgeKeys = useRef<Set<string>>(new Set())
  useEffect(() => {
    const keys = new Set(edges.map((e) => e.event_key))
    if (alertsOn && 'Notification' in window && Notification.permission === 'granted') {
      for (const e of edges) {
        if (!prevEdgeKeys.current.has(e.event_key)) {
          new Notification('Tinli — lock edge', {
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

  const closeIntro = () => {
    localStorage.setItem(INTRO_KEY, '1')
    setIntro('off')
  }

  const status = (() => {
    if (health === null) return <span className="label text-down">API offline</span>
    if (health.mode === 'demo') {
      return (
        <span className="label border border-gold text-gold px-2 py-0.5 rounded-sm">
          Simulated data
        </span>
      )
    }
    const stale = Object.entries(streamed?.venues ?? {}).filter(([, v]) => v.state !== 'live')
    if (streamOn && stale.length > 0) {
      const [name, v] = stale[0]
      return (
        <span className="label text-gold" title="this venue's feed has not updated recently">
          {name} {v.age_s != null ? `stale ${Math.round(v.age_s)}s` : 'connecting'}
        </span>
      )
    }
    return (
      <span
        className="label text-up"
        title={streamOn ? 'pushed on change: Polymarket websocket, Kalshi fast-poll' : 'polling every 3s'}
      >
        ● Live{streamOn ? '' : ' · poll'}
      </span>
    )
  })()

  return (
    <div className="h-screen flex flex-col gap-1 p-1">
      {intro !== 'off' && <IntroPanel onClose={closeIntro} full={intro === 'full'} />}
      <header className="flex items-center gap-3 border border-line bg-panel rounded-sm px-3 h-9 shrink-0">
        <span className="font-mono text-gold font-bold tracking-[0.2em] text-[14px]">TINLI</span>
        <span className="text-muted text-[11px]">Kalshi · Polymarket</span>
        <nav className="ml-3 flex border border-line rounded-sm overflow-hidden">
          {VIEWS.map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`label px-2.5 py-1 ${view === v ? 'bg-primary text-text' : 'hover:text-hover'}`}
            >
              {v}
            </button>
          ))}
        </nav>
        <button
          onClick={toggleAlerts}
          title="browser notification when a verified pair turns positive"
          className={`label ml-2 ${alertsOn ? 'text-gold' : 'hover:text-hover'}`}
        >
          {alertsOn ? '● ' : '○ '}Alerts
        </button>
        {health?.byok && (
          <span className="label text-hover" title="Kalshi key configured: authenticated feed and account, read-only">
            BYOK
          </span>
        )}
        <input
          ref={filterRef}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="/ filter"
          className="field ml-3 w-28 text-[11px] placeholder:text-muted"
        />
        <span className="ml-auto">{status}</span>
      </header>
      <EdgeAlert edges={edges} onSelect={setSelected} />
      {view === 'curate' ? (
        <CurateView
          pairs={pairs}
          readonly={health?.readonly ?? false}
          onPairsChanged={(next) => setPairs(sortPairs(next))}
        />
      ) : view === 'crypto' ? (
        <CryptoView />
      ) : view === 'book' ? (
        <main className="flex-1 flex gap-1 min-h-0">
          <Panel title="Book" extra="self-reported positions">
            <RiskPanel
              report={risk}
              error={riskError}
              pairs={pairs}
              readonly={health?.readonly ?? false}
              onSaved={fetchRisk}
            />
          </Panel>
          {(account?.byok || health?.byok) && (
            <Panel title="Kalshi account" extra="read-only">
              <AccountPanel report={account} pairs={pairs} />
            </Panel>
          )}
        </main>
      ) : (
        <main className="flex-1 grid grid-cols-[minmax(360px,34rem)_minmax(420px,1fr)] gap-1 min-h-0">
          <Panel
            title="Pairs"
            extra={
              filter
                ? `${groups.visible.length} match`
                : `${groups.verified.length} verified · edges after fees, at size`
            }
          >
            {pairs.length === 0 || divergence.length === 0 ? (
              <Skeleton rows={8} />
            ) : (
              <PairList
                groups={groups}
                selected={activeKey}
                onToggle={toggleGroup}
                onSelect={setSelected}
              />
            )}
          </Panel>
          <Panel title="Market">
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
        </main>
      )}
      <footer className="flex items-center border border-line bg-panel rounded-sm px-3 h-7 shrink-0 text-[10px] text-muted">
        <span>Public market data, read-only. Quotes may be delayed. Not investment advice.</span>
        <button onClick={() => setIntro('full')} className="label ml-auto hover:text-hover">
          Help
        </button>
      </footer>
    </div>
  )
}
