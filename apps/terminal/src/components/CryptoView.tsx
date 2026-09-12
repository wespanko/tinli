import { useEffect, useMemo, useState } from 'react'

import type { CryptoItem, CryptoLadder, ExpiryLadder } from '../types.gen'
import { cents, clock, pct, qty } from '../format'
import Panel from './Panel'
import Signed from './Signed'
import Skeleton from './Skeleton'

/** M15 CRYPTO view: every Kalshi BTC/ETH above/below strike priced against
    the Deribit option chain. Two numbers per row — the model fair value
    (an unhedged view on vol) and the hedge edge (a lock against listed call
    spreads, after both venues' fees). Gold EDGE¢ = hedge edge > 0. The
    hedge outlives the binary by the gap shown in the expiry tab: that is
    disclosed on screen, never hidden. */

type Coin = 'BTC' | 'ETH'
const COINS: Coin[] = ['BTC', 'ETH']
const COIN_KEY = 'tinli-crypto-coin'
const POLL_MS = 10_000

const th = 'py-1.5 font-sans font-medium text-[10px] tracking-[0.12em] text-muted'

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

export default function CryptoView() {
  const [ladders, setLadders] = useState<Partial<Record<Coin, CryptoLadder>>>({})
  const [error, setError] = useState<string | null>(null)
  const [coin, setCoin] = useState<Coin>(() =>
    localStorage.getItem(COIN_KEY) === 'ETH' ? 'ETH' : 'BTC',
  )
  const [expIdx, setExpIdx] = useState(0)
  const [showUnquoted, setShowUnquoted] = useState(false)
  const [showAssumptions, setShowAssumptions] = useState(false)

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

  const ladder = ladders[coin]
  const expiries = ladder?.expiries ?? []
  const exp = expiries[Math.min(expIdx, Math.max(0, expiries.length - 1))]
  // default: the live zone — strikes the model prices strictly inside (0.5¢, 99.5¢).
  // Deep ITM/OTM rows (an hourly ladder lists ~190 strikes) wait behind the toggle.
  const rows = useMemo(() => {
    if (!exp) return []
    if (showUnquoted) return exp.items
    return exp.items.filter((it) => {
      if (it.fair_value == null) return it.kalshi.bid != null || it.kalshi.ask != null
      const fv = parseFloat(it.fair_value)
      return fv > 0.005 && fv < 0.995
    })
  }, [exp, showUnquoted])
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

  const pickCoin = (c: Coin) => {
    localStorage.setItem(COIN_KEY, c)
    setCoin(c)
    setExpIdx(0)
  }

  return (
    <main className="flex-1 flex flex-col gap-1 min-h-0">
      {/* spot strip: both coins' Deribit index, always visible */}
      <div className="flex items-center gap-4 border border-line bg-panel rounded-sm px-3 h-9 shrink-0">
        {COINS.map((c) => (
          <button
            key={c}
            onClick={() => pickCoin(c)}
            className={`flex items-baseline gap-2 px-2 py-0.5 rounded-sm border ${
              coin === c ? 'border-primary text-text' : 'border-transparent text-muted hover:text-hover'
            }`}
          >
            <span className="text-[10px] tracking-[0.15em]">{c}</span>
            <span className="font-mono text-[14px]">{usd2(ladders[c]?.index)}</span>
          </button>
        ))}
        <span className="text-muted text-[10px] tracking-[0.1em]">DERIBIT INDEX</span>
        {exp && (
          <span className="ml-auto text-[11px] text-muted">
            ATM IV <span className="font-mono text-text">{exp.atm_iv == null ? '—' : pct(exp.atm_iv, 0)}</span>
            <span className="mx-2">·</span>
            as of <span className="font-mono">{clock(ladder?.fetched_at)}</span>
          </span>
        )}
        {error && <span className="ml-auto text-gold text-[11px]">! {error}</span>}
      </div>

      <div className="flex-1 grid grid-cols-[minmax(560px,1fr)_minmax(300px,24rem)] gap-1 min-h-0">
        <Panel
          title={`${coin} · KALSHI ABOVE/BELOW vs DERIBIT`}
          extra={
            <button onClick={() => setShowUnquoted((v) => !v)} className="hover:text-hover">
              {showUnquoted ? 'live zone only' : 'show all strikes'}
            </button>
          }
        >
          {!ladder ? (
            <Skeleton rows={10} />
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
                    <th className={`${th} text-left pl-3`} title="at or above this price at settlement">
                      STRIKE
                    </th>
                    <th className={`${th} text-right px-1`} title="Kalshi YES bid · ask, cents">
                      K BID · ASK
                    </th>
                    <th className={`${th} text-right px-1`} title="model digital value off Deribit mark IVs, cents">
                      FAIR
                    </th>
                    <th className={`${th} text-right px-1`} title="Kalshi mid minus fair value, cents; + = Kalshi rich">
                      MIS¢
                    </th>
                    <th className={`${th} text-right px-1`} title="interpolated implied vol at this strike">
                      IV
                    </th>
                    <th
                      className={`${th} text-right px-1`}
                      title="Deribit call-spread bounds per $1: what selling the sub-replicating spread returns · what buying the super-replicating spread costs, after fees"
                    >
                      HEDGE BID · ASK
                    </th>
                    <th
                      className={`${th} text-right px-1`}
                      title="locked profit per contract after both venues' fees, floored — gold when positive"
                    >
                      EDGE¢
                    </th>
                    <th className={`${th} text-right px-3`} title="Kalshi top-of-book depth on the traded side">
                      SIZE
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((it) => (
                    <Row key={it.ticker} it={it} />
                  ))}
                </tbody>
              </table>
            </>
          )}
        </Panel>

        <div className="flex flex-col gap-1 min-h-0">
          <Panel title="READING THIS LADDER">
            <div className="p-3 text-[12px] leading-relaxed flex flex-col gap-2">
              {exp && (
                <div className="grid grid-cols-2 gap-1.5">
                  <div className="bg-panel-2 border border-line rounded-sm px-3 py-1.5">
                    <div className="text-muted text-[10px] tracking-[0.12em]">LOCKS QUOTED</div>
                    <div className={`font-mono text-[18px] ${locks.length ? 'text-gold' : 'text-text'}`}>
                      {locks.length}
                    </div>
                    <div className="text-muted text-[10px]">hedge edge &gt; 0 after fees</div>
                  </div>
                  <div className="bg-panel-2 border border-line rounded-sm px-3 py-1.5">
                    <div className="text-muted text-[10px] tracking-[0.12em]">BEST MODEL EDGE</div>
                    <div className="font-mono text-[18px] text-text">
                      {bestModel?.model_edge == null ? '—' : `${cents(bestModel.model_edge, 2)}¢`}
                    </div>
                    <div className="text-muted text-[10px]">
                      {bestModel ? `${usd0(bestModel.strike)} · ${bestModel.model_direction?.replace('_', ' ')}` : 'unhedged view'}
                    </div>
                  </div>
                </div>
              )}
              <p>
                <span className="text-text">FAIR</span> is the digital's value off Deribit's mark-IV
                surface: e<sup>−rT</sup> N(d₂). <span className="text-text">MIS¢</span> is how far
                Kalshi's mid sits from it. That is a view on vol, not a lock — nothing is hedged.
              </p>
              <p>
                <span className="text-text">HEDGE</span> is model-free: the call spread on Deribit
                that pays at least (ask) or at most (bid) what the binary pays. Buy the cheap side on
                Kalshi, take the opposite spread, and{' '}
                <span className="text-gold">EDGE¢</span> is locked after both venues' fees.
              </p>
              <p className="text-muted">
                Deribit settles 08:00 UTC, Kalshi 5pm ET: every hedge outlives its binary by the
                hours shown on the expiry tab. Kalshi settles on a 60s CF Benchmarks average,
                Deribit on its own index. Neither gap is priced — they are disclosed.
              </p>
              <p className="text-muted">
                SIZE is Kalshi depth only; Deribit depth and its 0.1-coin minimum are not modeled.
              </p>
            </div>
          </Panel>
          <Panel
            title={`ASSUMPTIONS${ladder ? ` (${ladder.assumptions.length})` : ''}`}
            extra={
              <button onClick={() => setShowAssumptions((v) => !v)} className="hover:text-hover">
                {showAssumptions ? 'HIDE' : 'SHOW'}
              </button>
            }
          >
            {showAssumptions && ladder && (
              <ol className="p-3 pl-7 text-[11px] text-muted list-decimal flex flex-col gap-1.5">
                {ladder.assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
                <li>
                  risk-free rate <span className="font-mono">{pct(ladder.rf_rate, 1)}</span> (TINLI_RF_RATE)
                </li>
              </ol>
            )}
          </Panel>
        </div>
      </div>
    </main>
  )
}
