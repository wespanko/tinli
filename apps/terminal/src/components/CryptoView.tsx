import { useEffect, useMemo, useState } from 'react'

import type { CryptoItem, CryptoLadder, ExpiryLadder } from '../types.gen'
import { cents, clock, pct, qty } from '../format'
import Panel from './Panel'
import Signed from './Signed'
import Skeleton from './Skeleton'

/** Every Kalshi BTC/ETH above/below strike priced against the Deribit
    option chain: a model fair value (an unhedged view on vol) and the
    hedge edge (a lock against listed call spreads, after both venues'
    fees). The hedge outlives the binary by the gap on the expiry tab. */

type Coin = 'BTC' | 'ETH'
const COINS: Coin[] = ['BTC', 'ETH']
const POLL_MS = 10_000

function usd0(v: string | number | null | undefined): string {
  if (v == null) return '—'
  return '$' + Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function usd2(v: string | null | undefined): string {
  if (v == null) return '—'
  return '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function expiryLabel(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'America/New_York',
  }) + ' ET'
}

function hedgeLabel(e: ExpiryLadder): string {
  if (!e.hedge_expiry) return 'no listed hedge'
  const d = new Date(e.hedge_expiry)
  const day = d.toLocaleString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
  return `hedge ${day} 08:00Z · +${Number(e.hedge_gap_hours).toFixed(0)}h`
}

function Row({ it }: { it: CryptoItem }) {
  const edge = it.hedge_edge == null ? null : parseFloat(it.hedge_edge)
  const executable = edge != null && edge > 0
  const quoted = it.kalshi.bid != null || it.kalshi.ask != null
  const dir =
    it.hedge_direction === 'buy_yes_sell_spread'
      ? 'buy YES on Kalshi, sell the spread on Deribit'
      : it.hedge_direction === 'buy_no_buy_spread'
        ? 'buy NO on Kalshi, buy the spread on Deribit'
        : 'no hedge quoted'
  return (
    <tr
      className={`border-b border-line/30 ${executable ? 'bg-gold/5' : ''}`}
      title={`${it.ticker} · ${dir}${it.hedge_legs ? ` · ${it.hedge_legs}` : ''}${
        it.hedge_width ? ` · 1 option = ${qty(it.hedge_width)} contracts` : ''
      } · model: ${it.model_direction ?? '—'} ${it.model_edge == null ? '' : cents(it.model_edge, 2) + '¢'}`}
    >
      <td className={`pl-3 pr-1 py-1 tabular-nums ${quoted ? 'text-text' : 'text-muted'}`}>
        {usd0(it.strike)}
      </td>
      <td className="text-right px-1 tabular-nums text-muted whitespace-nowrap">
        <span className={it.kalshi.bid ? 'text-up' : ''}>{cents(it.kalshi.bid)}</span>
        <span className="mx-1 text-muted/60">·</span>
        <span className={it.kalshi.ask ? 'text-down' : ''}>{cents(it.kalshi.ask)}</span>
      </td>
      <td className="text-right px-1 tabular-nums text-text">{cents(it.fair_value)}</td>
      <td className="text-right px-1">
        <Signed
          value={it.mispricing_cents}
          text={
            it.mispricing_cents == null
              ? '—'
              : `${parseFloat(it.mispricing_cents) > 0 ? '+' : ''}${parseFloat(it.mispricing_cents).toFixed(1)}`
          }
        />
      </td>
      <td className="text-right px-1 tabular-nums text-muted">
        {it.iv == null ? '—' : pct(it.iv, 0)}
      </td>
      <td className="text-right px-1 tabular-nums text-muted whitespace-nowrap">
        {cents(it.hedge_bid)}
        <span className="mx-1 text-muted/60">·</span>
        {cents(it.hedge_ask)}
      </td>
      <td className={`text-right px-1 tabular-nums ${executable ? 'text-gold' : 'text-muted'}`}>
        {edge == null ? '—' : cents(it.hedge_edge, 2)}
      </td>
      <td className="text-right px-3 tabular-nums text-muted">{qty(it.max_size)}</td>
    </tr>
  )
}

function CoinLadder({ coin, ladder }: { coin: Coin; ladder: CryptoLadder | undefined }) {
  const [expIdx, setExpIdx] = useState(0)
  const [showAll, setShowAll] = useState(false)

  const expiries = ladder?.expiries ?? []
  const exp = expiries[Math.min(expIdx, Math.max(0, expiries.length - 1))]
  // default: strikes the model prices strictly inside (0.5¢, 99.5¢). Deep
  // ITM/OTM rows (an hourly ladder lists ~190 strikes) wait behind the toggle.
  const rows = useMemo(() => {
    if (!exp) return []
    if (showAll) return exp.items
    return exp.items.filter((it) => {
      if (it.fair_value == null) return it.kalshi.bid != null || it.kalshi.ask != null
      const fv = parseFloat(it.fair_value)
      return fv > 0.005 && fv < 0.995
    })
  }, [exp, showAll])
  const locks = useMemo(
    () => (exp ? exp.items.filter((it) => it.hedge_edge != null && parseFloat(it.hedge_edge) > 0) : []),
    [exp],
  )
  const bestModel = useMemo(() => {
    if (!exp) return null
    return exp.items.reduce<CryptoItem | null>((best, it) => {
      if (it.model_edge == null) return best
      if (!best || parseFloat(it.model_edge) > parseFloat(best.model_edge!)) return it
      return best
    }, null)
  }, [exp])

  const summary = exp && (
    <span className="flex items-center gap-4">
      <span>
        ATM IV <span className="font-mono text-text">{exp.atm_iv == null ? '—' : pct(exp.atm_iv, 0)}</span>
      </span>
      <span>
        <span className={`font-mono ${locks.length ? 'text-gold' : 'text-text'}`}>{locks.length}</span>{' '}
        {locks.length === 1 ? 'lock' : 'locks'} after fees
      </span>
      {bestModel?.model_edge != null && (
        <span>
          best model edge{' '}
          <span className="font-mono text-text">{cents(bestModel.model_edge, 2)}¢</span> at{' '}
          <span className="font-mono">{usd0(bestModel.strike)}</span>
        </span>
      )}
      <button onClick={() => setShowAll((v) => !v)} className="hover:text-hover">
        {showAll ? 'live zone only' : 'all strikes'}
      </button>
    </span>
  )

  return (
    <Panel title={`${coin} strikes vs Deribit`} extra={summary}>
      {!ladder ? (
        <Skeleton rows={6} />
      ) : expiries.length === 0 ? (
        <div className="p-3 text-muted text-[12px]">no open {coin} strike ladders on Kalshi</div>
      ) : (
        <>
          <div className="flex gap-1 px-2 py-1.5 border-b border-line sticky top-0 bg-panel z-10 overflow-x-auto">
            {expiries.map((e, i) => (
              <button
                key={e.close_ts}
                onClick={() => setExpIdx(i)}
                className={`px-2 py-1 rounded-sm border text-[11px] whitespace-nowrap ${
                  i === expIdx
                    ? 'border-primary bg-primary/10 text-text'
                    : 'border-line text-muted hover:text-hover'
                }`}
                title={`Kalshi settles ${e.close_ts}; ${hedgeLabel(e)}`}
              >
                {expiryLabel(e.close_ts)}
                <span className="ml-2 text-[10px] text-muted">{hedgeLabel(e)}</span>
              </button>
            ))}
          </div>
          <table className="w-full font-mono text-[12px]">
            <thead>
              <tr className="border-b border-line">
                <th className="th text-left pl-3" title="at or above this price at settlement">
                  Strike
                </th>
                <th className="th text-right px-1" title="Kalshi YES bid · ask, cents">
                  K bid · ask
                </th>
                <th className="th text-right px-1" title="digital value off Deribit mark IVs, cents">
                  Fair
                </th>
                <th className="th text-right px-1" title="Kalshi mid minus fair value, cents; positive means Kalshi rich">
                  Mis¢
                </th>
                <th className="th text-right px-1" title="interpolated implied vol at this strike">
                  IV
                </th>
                <th
                  className="th text-right px-1"
                  title="Deribit call-spread bounds per $1: what selling the sub-replicating spread returns · what buying the super-replicating spread costs, after fees"
                >
                  Hedge bid · ask
                </th>
                <th className="th text-right px-1" title="locked profit per contract after both venues' fees">
                  Edge¢
                </th>
                <th className="th text-right px-3" title="Kalshi top-of-book depth on the traded side">
                  Size
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((it) => (
                <Row key={it.ticker} it={it} />
              ))}
            </tbody>
          </table>
          <details className="px-3 py-2 border-t border-line">
            <summary className="label cursor-pointer hover:text-hover">
              Assumptions ({ladder.assumptions.length + 1})
            </summary>
            <ol className="mt-1.5 pl-5 text-[11px] text-muted list-decimal flex flex-col gap-1">
              {ladder.assumptions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
              <li>
                risk-free rate <span className="font-mono">{pct(ladder.rf_rate, 1)}</span>
              </li>
            </ol>
          </details>
        </>
      )}
    </Panel>
  )
}

export default function CryptoView() {
  const [ladders, setLadders] = useState<Partial<Record<Coin, CryptoLadder>>>({})
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const load = () => {
      for (const c of COINS) {
        fetch(`/v1/crypto/${c}`)
          .then(async (r) => {
            if (!alive) return
            if (r.ok) {
              const body = (await r.json()) as CryptoLadder
              setLadders((prev) => ({ ...prev, [c]: body }))
              setError(null)
            } else {
              const body = await r.json().catch(() => null)
              setError(body?.detail ?? `HTTP ${r.status}`)
            }
          })
          .catch(() => alive && setError('API offline'))
      }
    }
    load()
    const id = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const asOf = ladders.BTC?.fetched_at ?? ladders.ETH?.fetched_at

  return (
    <main className="flex-1 flex flex-col gap-1 min-h-0">
      <div className="flex items-center gap-6 border border-line bg-panel rounded-sm px-3 h-9 shrink-0">
        {COINS.map((c) => (
          <span key={c} className="flex items-baseline gap-2">
            <span className="label">{c}</span>
            <span className="font-mono text-[14px] text-text">{usd2(ladders[c]?.index)}</span>
          </span>
        ))}
        <span className="label">Deribit index</span>
        {asOf && (
          <span className="ml-auto text-[11px] text-muted">
            as of <span className="font-mono">{clock(asOf)}</span>
          </span>
        )}
        {error && <span className="ml-auto text-gold text-[11px]">{error}</span>}
      </div>
      {COINS.map((c) => (
        <CoinLadder key={c} coin={c} ladder={ladders[c]} />
      ))}
    </main>
  )
}
