import { useState } from 'react'
import type { Pair, Position, RiskReport } from '../types'
import { cents, pct, qty, signedUsd, usd } from '../format'
import Signed from './Signed'

function Stat({
  label,
  value,
  tone = 'text-text',
  big = false,
}: {
  label: string
  value: React.ReactNode
  tone?: string
  big?: boolean
}) {
  return (
    <div className="bg-panel-2 border border-line rounded-sm px-3 py-1.5">
      <div className="text-muted text-[10px] tracking-[0.12em]">{label}</div>
      {/* standalone numbers: mono, proportional figures, not tabular */}
      <div className={`font-mono ${big ? 'text-[22px] leading-7' : 'text-[15px]'} ${tone}`}>
        {value}
      </div>
    </div>
  )
}

const th = 'py-1 font-sans font-medium text-[10px] tracking-[0.12em] text-muted'
const input =
  'bg-bg border border-line rounded-sm px-1.5 py-0.5 font-mono text-[12px] text-text w-full'

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

export default function RiskPanel({
  report,
  error,
  pairs,
  readonly,
  onSaved,
}: {
  report: RiskReport | null
  error: string | null
  pairs: Pair[]
  readonly: boolean
  onSaved: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Draft[]>([])
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  if (!report && !error) return <div className="p-3 text-muted text-[12px]">loading risk…</div>
  if (!report) return <div className="p-3 text-gold text-[12px]">! {error}</div>
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
        setSaveError(
          typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? resp.status),
        )
      } else {
        setEditing(false)
        onSaved()
      }
    } catch {
      setSaveError('network error — book not saved')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-3 flex flex-col gap-3 text-[13px]">
      {error && (
        <div className="border border-gold text-gold text-[11px] rounded-sm px-2 py-1.5">
          ! {error}
          <div className="text-muted mt-0.5">
            showing the last good report — numbers below are STALE
          </div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-1.5">
        <Stat label="VAR 95 · MONTE CARLO" value={usd(r.var_95_monte_carlo)} tone="text-gold" big />
        <Stat
          label="UNREALIZED P&L"
          value={<Signed value={r.total_unrealized_pnl} text={signedUsd(r.total_unrealized_pnl)} />}
          big
        />
      </div>
      <div className="grid grid-cols-4 gap-1.5">
        <Stat label="VAR PARAM" value={usd(r.var_95_parametric)} />
        <Stat label="MAX LOSS" value={usd(r.max_loss)} />
        <Stat label="MKT VALUE" value={usd(r.total_market_value)} />
        <Stat label="COST BASIS" value={usd(r.total_cost_basis)} />
      </div>

      {r.unmarked_positions > 0 && !editing && (
        <div className="text-gold text-[11px]">
          ! {r.unmarked_positions} position(s) not in the feed — excluded from all numbers above
        </div>
      )}

      {!editing ? (
        <>
          <table className="w-full font-mono">
            <thead>
              <tr className="border-b border-line">
                <th className={`${th} text-left`}>POSITION</th>
                <th className={`${th} text-left px-1`}>SIDE</th>
                <th className={`${th} text-right px-1`}>QTY</th>
                <th className={`${th} text-right px-1`}>ENTRY</th>
                <th className={`${th} text-right px-1`}>MARK</th>
                <th className={`${th} text-right px-1`}>P&L</th>
                <th
                  className={`${th} text-right pl-1`}
                  title="half-Kelly fraction of bankroll, from your est_prob"
                >
                  K½
                </th>
              </tr>
            </thead>
            <tbody>
              {r.positions.map((row, i) => (
                <tr key={i} className="border-b border-line/30">
                  <td
                    className={`font-sans py-1.5 pr-1 whitespace-nowrap overflow-hidden text-ellipsis max-w-36 ${
                      row.mark == null ? 'text-muted' : 'text-text'
                    }`}
                    title={`${row.event_id ?? ''} ${row.position.market_id}`.trim()}
                  >
                    {row.mark == null && (
                      <span className="text-gold mr-1" title="not in market feed — unmarked">
                        !
                      </span>
                    )}
                    {eventName(row.event_id) ?? row.position.market_id}
                  </td>
                  <td className="px-1 uppercase text-[11px] text-muted">{row.position.side}</td>
                  <td className="text-right px-1 tabular-nums text-text">
                    {qty(row.position.contracts)}
                  </td>
                  <td className="text-right px-1 tabular-nums text-muted">
                    {cents(row.position.entry_price)}
                  </td>
                  <td className="text-right px-1 tabular-nums text-text">{cents(row.mark)}</td>
                  <td className="text-right px-1">
                    <Signed value={row.unrealized_pnl} text={signedUsd(row.unrealized_pnl)} />
                  </td>
                  <td className="text-right pl-1 tabular-nums text-muted">{pct(row.kelly_half)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!readonly && (
            <button
              onClick={startEdit}
              className="self-start border border-line text-muted hover:text-hover rounded-sm px-2.5 py-0.5 text-[10px] tracking-[0.15em]"
            >
              EDIT BOOK
            </button>
          )}
        </>
      ) : (
        <div className="flex flex-col gap-1.5">
          {saveError && (
            <div className="border border-gold text-gold text-[11px] rounded-sm px-2 py-1.5">
              ! {saveError}
            </div>
          )}
          <table className="w-full font-mono">
            <thead>
              <tr className="border-b border-line">
                <th className={`${th} text-left`}>MARKET</th>
                <th className={`${th} text-left px-1`}>SIDE</th>
                <th className={`${th} text-right px-1`}>QTY</th>
                <th className={`${th} text-right px-1`} title="dollars 0-1, e.g. 0.55">
                  ENTRY $
                </th>
                <th className={`${th} text-right px-1`} title="your YES probability estimate, optional">
                  EST P
                </th>
                <th className={th}></th>
              </tr>
            </thead>
            <tbody>
              {draft.map((d, i) => (
                <tr key={i} className="border-b border-line/30">
                  <td className="py-1 pr-1 max-w-44">
                    <select
                      className={input}
                      value={d.market_id}
                      onChange={(e) => set(i, 'market_id', e.target.value)}
                    >
                      {!marketOptions.some((o) => o.id === d.market_id) && (
                        <option value={d.market_id}>{d.market_id}</option>
                      )}
                      {marketOptions.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-1 w-20">
                    <select
                      className={input}
                      value={d.side}
                      onChange={(e) => set(i, 'side', e.target.value)}
                    >
                      <option value="yes">YES</option>
                      <option value="no">NO</option>
                    </select>
                  </td>
                  <td className="px-1 w-20">
                    <input
                      className={`${input} text-right`}
                      value={d.contracts}
                      onChange={(e) => set(i, 'contracts', e.target.value)}
                    />
                  </td>
                  <td className="px-1 w-20">
                    <input
                      className={`${input} text-right`}
                      value={d.entry_price}
                      onChange={(e) => set(i, 'entry_price', e.target.value)}
                    />
                  </td>
                  <td className="px-1 w-20">
                    <input
                      className={`${input} text-right`}
                      placeholder="—"
                      value={d.est_prob}
                      onChange={(e) => set(i, 'est_prob', e.target.value)}
                    />
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
          <div className="flex gap-1.5">
            <button
              onClick={() =>
                setDraft((rows) => [
                  ...rows,
                  {
                    market_id: marketOptions[0]?.id ?? '',
                    side: 'yes',
                    contracts: '100',
                    entry_price: '0.50',
                    est_prob: '',
                    notes: '',
                  },
                ])
              }
              className="border border-line text-muted hover:text-hover rounded-sm px-2.5 py-0.5 text-[10px] tracking-[0.15em]"
            >
              + ADD
            </button>
            <button
              onClick={save}
              disabled={saving}
              className="border border-gold text-gold rounded-sm px-3 py-0.5 text-[10px] tracking-[0.15em] hover:bg-gold/10 disabled:opacity-50"
            >
              {saving ? 'SAVING…' : 'SAVE BOOK'}
            </button>
            <button
              onClick={() => setEditing(false)}
              className="border border-line text-muted hover:text-hover rounded-sm px-2.5 py-0.5 text-[10px] tracking-[0.15em]"
            >
              CANCEL
            </button>
            <span className="text-muted text-[10px] self-center">
              writes data/positions.yaml — hand-editing keeps working too
            </span>
          </div>
        </div>
      )}

      {r.by_event.length > 0 && !editing && (
        <div>
          <div className="text-muted text-[10px] tracking-[0.15em] mb-1">EXPOSURE BY EVENT</div>
          <table className="w-full font-mono">
            <thead>
              <tr className="border-b border-line">
                <th className={`${th} text-left`}>EVENT</th>
                <th className={`${th} text-right px-1`} title="yes − no contracts">
                  NET
                </th>
                <th className={`${th} text-right px-1`} title="P&L if event resolves YES">
                  IF YES
                </th>
                <th className={`${th} text-right pl-1`} title="P&L if event resolves NO">
                  IF NO
                </th>
              </tr>
            </thead>
            <tbody>
              {r.by_event.map((e) => (
                <tr key={e.event_id} className="border-b border-line/30">
                  <td
                    className="font-sans py-1.5 pr-1 whitespace-nowrap overflow-hidden text-ellipsis max-w-40 text-text"
                    title={e.event_id}
                  >
                    {eventName(e.event_id)}
                  </td>
                  <td className="text-right px-1 tabular-nums text-text">
                    {qty(e.net_yes_contracts)}
                  </td>
                  <td className="text-right px-1">
                    <Signed value={e.delta_if_yes} text={signedUsd(e.delta_if_yes)} />
                  </td>
                  <td className="text-right pl-1">
                    <Signed value={e.delta_if_no} text={signedUsd(e.delta_if_no)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <details className="text-[11px] text-muted">
        <summary className="cursor-pointer tracking-[0.12em] text-[10px]">
          ASSUMPTIONS · VAR HORIZON = RESOLUTION · MC SEED {r.mc_seed} /{' '}
          {r.mc_draws.toLocaleString('en-US')} DRAWS
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
