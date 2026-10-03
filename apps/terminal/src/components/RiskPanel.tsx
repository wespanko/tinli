import { useEffect, useState } from 'react'
import type { KellyQuote, Pair, Position, PositionRisk, RiskReport } from '../types'
import { cents, money, pct, qty, signedUsd, usd } from '../format'
import Signed from './Signed'
import Stat from './Stat'

const EST_KEY = 'tinli-est-prob'

type Draft = {
  market_id: string
  side: string // 'yes' | 'no' — constrained by the select; validated server-side
  contracts: string
  entry_price: string
  est_prob: string
  notes: string
}

function toDraft(p: Position): Draft {
  return {
    market_id: p.market_id,
    side: p.side,
    contracts: p.contracts,
    entry_price: p.entry_price,
    est_prob: p.est_prob ?? '',
    notes: p.notes ?? '',
  }
}

function loadEstimates(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(EST_KEY) ?? '{}') as Record<string, string>
  } catch {
    return {}
  }
}

/** Kelly for one row: the user's YES probability (from the positions file,
    or typed here and kept in this browser) against the current mark. The
    math runs server-side through /v1/kelly so read-only instances size too. */
function KellyCells({
  row,
  estimate,
  bankroll,
  onEstimate,
}: {
  row: PositionRisk
  estimate: string
  bankroll: number | null
  onEstimate: (v: string) => void
}) {
  const [quote, setQuote] = useState<KellyQuote | null>(null)
  const p = parseFloat(estimate)
  const valid = Number.isFinite(p) && p >= 0 && p <= 1 && row.mark != null
  useEffect(() => {
    if (!valid) {
      setQuote(null)
      return
    }
    let alive = true
    const id = setTimeout(() => {
      const params = new URLSearchParams({
        price: row.mark!,
        est_prob: String(p),
        bankroll: String(bankroll ?? 1),
        side: row.position.side,
      })
      fetch(`/v1/kelly?${params}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((q) => alive && setQuote(q))
        .catch(() => {})
    }, 250)
    return () => {
      alive = false
      clearTimeout(id)
    }
  }, [valid, p, row.mark, row.position.side, bankroll])
  return (
    <>
      <td className="px-1 w-16">
        <input
          className="field w-full h-6 text-right"
          value={estimate}
          placeholder="p"
          inputMode="decimal"
          title="your own YES probability, 0-1; kept in this browser"
          onChange={(e) => onEstimate(e.target.value)}
        />
      </td>
      <td className="num text-right px-2 text-muted">
        {quote?.kelly_half != null ? pct(quote.kelly_half) : '—'}
      </td>
      <td className={`num text-right pl-2 ${quote?.contracts_half ? 'text-text' : 'text-muted'}`}>
        {bankroll == null ? (
          <span title="enter a bankroll in the top bar">—</span>
        ) : quote?.contracts_half != null ? (
          <span title={`${money(quote.stake_half)} at half Kelly · ${quote.contracts_full} at full`}>
            {qty(quote.contracts_half)}
          </span>
        ) : (
          '—'
        )}
      </td>
    </>
  )
}

export default function RiskPanel({
  report,
  error,
  pairs,
  readonly,
  bankroll,
  onSaved,
}: {
  report: RiskReport | null
  error: string | null
  pairs: Pair[]
  readonly: boolean
  bankroll: number | null
  onSaved: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Draft[]>([])
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [estimates, setEstimates] = useState<Record<string, string>>(loadEstimates)
  const setEstimate = (marketId: string, v: string) =>
    setEstimates((prev) => {
      const next = { ...prev, [marketId]: v }
      if (v.trim() === '') delete next[marketId]
      localStorage.setItem(EST_KEY, JSON.stringify(next))
      return next
    })

  if (!report && !error) return <div className="p-3 text-muted text-[12px]">loading…</div>
  if (!report) return <div className="p-3 text-gold text-[12px]">{error}</div>
  const r = report

  const marketOptions = pairs.flatMap((p) =>
    [
      p.kalshi && { id: p.kalshi.id, label: `${p.question} · K` },
      p.polymarket && { id: p.polymarket.id, label: `${p.question} · PM` },
    ].filter(Boolean) as { id: string; label: string }[],
  )

  // display names, not slugs: event_id -> the pair's curated question
  const eventName = (eventId: string | null) => {
    if (eventId == null) return null
    return pairs.find((p) => p.event_key === eventId)?.question ?? eventId
  }

  const startEdit = () => {
    setDraft(r.positions.map((row) => toDraft(row.position)))
    setSaveError(null)
    setEditing(true)
  }

  const set = (i: number, field: keyof Draft, value: string) =>
    setDraft((d) => d.map((row, j) => (j === i ? { ...row, [field]: value } : row)))

  const save = async () => {
    setSaving(true)
    setSaveError(null)
    const positions = draft.map((d) => ({
      market_id: d.market_id,
      side: d.side,
      contracts: d.contracts,
      entry_price: d.entry_price,
      est_prob: d.est_prob.trim() === '' ? null : d.est_prob,
      notes: d.notes,
    }))
    try {
      const resp = await fetch('/v1/positions', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ positions }),
      })
      if (!resp.ok) {
        const body = await resp.json().catch(() => null)
        setSaveError(typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? resp.status))
      } else {
        setEditing(false)
        onSaved()
      }
    } catch {
      setSaveError('network error, book not saved')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-4 flex flex-col gap-5 text-[12px]">
      {error && (
        <div className="border border-gold text-gold text-[11px] rounded-sm px-2 py-1.5">
          {error}
          <div className="text-muted mt-0.5">showing the last good report; these numbers are stale</div>
        </div>
      )}

      <div className="flex flex-wrap gap-x-10 gap-y-3 items-end">
        <Stat label="VaR 95 · Monte Carlo" value={<span className="text-gold">{usd(r.var_95_monte_carlo)}</span>} size="lg" />
        <Stat
          label="Unrealized P&L"
          value={<Signed value={r.total_unrealized_pnl} text={signedUsd(r.total_unrealized_pnl)} />}
          size="lg"
        />
        <Stat label="VaR 95 · parametric" value={usd(r.var_95_parametric)} />
        <Stat label="Max loss" value={usd(r.max_loss)} />
        <Stat label="Market value" value={usd(r.total_market_value)} />
        <Stat label="Cost basis" value={usd(r.total_cost_basis)} />
        {bankroll != null && <Stat label="Bankroll" value={money(bankroll, 0)} sub="sizes the Kelly column" />}
      </div>

      {r.unmarked_positions > 0 && !editing && (
        <div className="text-gold text-[11px]">
          {r.unmarked_positions} position{r.unmarked_positions === 1 ? '' : 's'} not in the feed, excluded from the numbers above
        </div>
      )}

      {!editing ? (
        <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_minmax(280px,26rem)] gap-8 items-start">
          <div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-line">
                  <th className="th text-left">Position</th>
                  <th className="th text-left px-1">Side</th>
                  <th className="th text-right px-2">Qty</th>
                  <th className="th text-right px-2">Entry</th>
                  <th className="th text-right px-2">Mark</th>
                  <th className="th text-right px-2">P&L</th>
                  <th className="th text-right px-1" title="your own YES probability; Kelly is zero edge against the market's own price">
                    Your p
                  </th>
                  <th className="th text-right px-2" title="half-Kelly fraction of bankroll at the current mark">
                    K½
                  </th>
                  <th className="th text-right pl-2" title="contracts half Kelly buys with your bankroll">
                    K½ size
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.positions.map((row, i) => (
                  <tr key={i} className="border-b border-line/40 h-8">
                    <td
                      className={`font-sans py-1 pr-2 whitespace-nowrap overflow-hidden text-ellipsis max-w-64 ${
                        row.mark == null ? 'text-muted' : 'text-text'
                      }`}
                      title={row.mark == null ? 'not in the market feed' : undefined}
                    >
                      {eventName(row.event_id) ?? row.position.market_id}
                    </td>
                    <td className="px-1 uppercase text-[11px] text-muted">{row.position.side}</td>
                    <td className="num text-right px-2 text-text">{qty(row.position.contracts)}</td>
                    <td className="num text-right px-2 text-muted">{cents(row.position.entry_price)}</td>
                    <td className="num text-right px-2 text-text">{cents(row.mark)}</td>
                    <td className="text-right px-2">
                      <Signed value={row.unrealized_pnl} text={signedUsd(row.unrealized_pnl)} />
                    </td>
                    <KellyCells
                      row={row}
                      estimate={estimates[row.position.market_id] ?? row.position.est_prob ?? ''}
                      bankroll={bankroll}
                      onEstimate={(v) => setEstimate(row.position.market_id, v)}
                    />
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex items-center gap-3 mt-3">
              {!readonly && (
                <button onClick={startEdit} className="btn">
                  Edit book
                </button>
              )}
              <span className="text-[10px] text-dim">
                Your p stays in this browser. Kelly is sized against the mark, before spread and fees.
              </span>
            </div>
          </div>

          {r.by_event.length > 0 && (
            <table className="w-full">
              <thead>
                <tr className="border-b border-line">
                  <th className="th text-left">Exposure by event</th>
                  <th className="th text-right px-2" title="yes minus no contracts">Net</th>
                  <th className="th text-right px-2" title="P&L if the event resolves YES">If yes</th>
                  <th className="th text-right pl-2" title="P&L if the event resolves NO">If no</th>
                </tr>
              </thead>
              <tbody>
                {r.by_event.map((e) => (
                  <tr key={e.event_id} className="border-b border-line/40 h-8">
                    <td className="font-sans py-1 pr-2 whitespace-nowrap overflow-hidden text-ellipsis max-w-48 text-text">
                      {eventName(e.event_id)}
                    </td>
                    <td className="num text-right px-2 text-text">{qty(e.net_yes_contracts)}</td>
                    <td className="text-right px-2">
                      <Signed value={e.delta_if_yes} text={signedUsd(e.delta_if_yes)} />
                    </td>
                    <td className="text-right pl-2">
                      <Signed value={e.delta_if_no} text={signedUsd(e.delta_if_no)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-2 max-w-3xl">
          {saveError && (
            <div className="border border-gold text-gold text-[11px] rounded-sm px-2 py-1.5">{saveError}</div>
          )}
          <table className="w-full">
            <thead>
              <tr className="border-b border-line">
                <th className="th text-left">Market</th>
                <th className="th text-left px-1">Side</th>
                <th className="th text-right px-1">Qty</th>
                <th className="th text-right px-1" title="dollars 0-1, e.g. 0.55">Entry $</th>
                <th className="th text-right px-1" title="your YES probability estimate, optional">Est p</th>
                <th className="th"></th>
              </tr>
            </thead>
            <tbody>
              {draft.map((d, i) => (
                <tr key={i} className="border-b border-line/40">
                  <td className="py-1 pr-1 max-w-44">
                    <select className="field w-full" value={d.market_id} onChange={(e) => set(i, 'market_id', e.target.value)}>
                      {!marketOptions.some((o) => o.id === d.market_id) && <option value={d.market_id}>{d.market_id}</option>}
                      {marketOptions.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-1 w-20">
                    <select className="field w-full" value={d.side} onChange={(e) => set(i, 'side', e.target.value)}>
                      <option value="yes">YES</option>
                      <option value="no">NO</option>
                    </select>
                  </td>
                  <td className="px-1 w-20">
                    <input className="field w-full text-right" value={d.contracts} onChange={(e) => set(i, 'contracts', e.target.value)} />
                  </td>
                  <td className="px-1 w-20">
                    <input className="field w-full text-right" value={d.entry_price} onChange={(e) => set(i, 'entry_price', e.target.value)} />
                  </td>
                  <td className="px-1 w-20">
                    <input className="field w-full text-right" placeholder="—" value={d.est_prob} onChange={(e) => set(i, 'est_prob', e.target.value)} />
                  </td>
                  <td className="pl-1 w-8 text-right">
                    <button
                      onClick={() => setDraft((rows) => rows.filter((_, j) => j !== i))}
                      className="text-muted hover:text-down text-[12px]"
                      title="remove position"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex gap-2 items-center">
            <button
              onClick={() =>
                setDraft((rows) => [
                  ...rows,
                  { market_id: marketOptions[0]?.id ?? '', side: 'yes', contracts: '100', entry_price: '0.50', est_prob: '', notes: '' },
                ])
              }
              className="btn"
            >
              + Add
            </button>
            <button onClick={save} disabled={saving} className="btn-gold">
              {saving ? 'Saving…' : 'Save book'}
            </button>
            <button onClick={() => setEditing(false)} className="btn">
              Cancel
            </button>
            <span className="text-dim text-[10px] ml-2">writes your positions file</span>
          </div>
        </div>
      )}

      <details className="text-[11px] text-muted">
        <summary className="label cursor-pointer hover:text-hover">
          Assumptions · VaR to resolution · MC seed {r.mc_seed}, {r.mc_draws.toLocaleString('en-US')} draws
        </summary>
        <ul className="mt-1.5 flex flex-col gap-1 list-disc pl-4 leading-snug">
          {r.assumptions.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      </details>
    </div>
  )
}
