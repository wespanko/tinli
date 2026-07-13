import type { RiskReport } from '../types'
import { cents, pct, qty, shortId, signedUsd, usd } from '../format'

function Stat({ label, value, gold }: { label: string; value: string; gold?: boolean }) {
  return (
    <div className="border border-line rounded-sm px-2 py-1">
      <div className="text-muted text-[10px] tracking-wider">{label}</div>
      <div className={`tabular-nums text-[15px] ${gold ? 'text-gold' : 'text-text'}`}>{value}</div>
    </div>
  )
}

export default function RiskPanel({ report }: { report: RiskReport | null }) {
  if (!report) return <div className="p-2 text-muted text-[12px]">loading risk…</div>
  const r = report
  return (
    <div className="p-2 flex flex-col gap-2 text-[12px]">
      <div className="grid grid-cols-3 gap-1">
        <Stat label="MKT VALUE" value={usd(r.total_market_value)} />
        <Stat label="UNREAL P&L" value={signedUsd(r.total_unrealized_pnl)} />
        <Stat label="MAX LOSS" value={usd(r.max_loss)} />
        <Stat label="VAR95 PARAM" value={usd(r.var_95_parametric)} gold />
        <Stat label="VAR95 MC" value={usd(r.var_95_monte_carlo)} gold />
        <Stat label="COST BASIS" value={usd(r.total_cost_basis)} />
      </div>

      {r.unmarked_positions > 0 && (
        <div className="text-gold text-[11px]">
          ! {r.unmarked_positions} position(s) not in the feed — excluded from all numbers above
        </div>
      )}

      <table className="w-full leading-5">
        <thead>
          <tr className="text-muted text-[10px] tracking-wider">
            <th className="text-left px-1 py-0.5 font-normal">POSITION</th>
            <th className="text-left px-1 py-0.5 font-normal">SIDE</th>
            <th className="text-right px-1 py-0.5 font-normal">QTY</th>
            <th className="text-right px-1 py-0.5 font-normal">ENTRY</th>
            <th className="text-right px-1 py-0.5 font-normal">MARK</th>
            <th className="text-right px-1 py-0.5 font-normal">P&L</th>
            <th className="text-right px-1 py-0.5 font-normal" title="half-Kelly of bankroll, from your est_prob">
              K½
            </th>
          </tr>
        </thead>
        <tbody>
          {r.positions.map((row, i) => (
            <tr key={i} className={`border-t border-line/50 ${row.mark == null ? 'text-muted' : 'text-text'}`}>
              <td
                className="px-1 py-0.5 whitespace-nowrap overflow-hidden text-ellipsis max-w-36"
                title={row.question ?? row.position.market_id}
              >
                {row.mark == null && (
                  <span className="text-gold mr-1" title="not in market feed — unmarked">
                    !
                  </span>
                )}
                {row.event_id ?? shortId(row.position.market_id)}
              </td>
              <td className="px-1 uppercase text-[11px]">{row.position.side}</td>
              <td className="text-right px-1 tabular-nums">{qty(row.position.contracts)}</td>
              <td className="text-right px-1 tabular-nums">{cents(row.position.entry_price)}</td>
              <td className="text-right px-1 tabular-nums">{cents(row.mark)}</td>
              <td className="text-right px-1 tabular-nums">{signedUsd(row.unrealized_pnl)}</td>
              <td className="text-right px-1 tabular-nums">{pct(row.kelly_half)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {r.by_event.length > 0 && (
        <div>
          <div className="text-muted text-[10px] tracking-wider mb-0.5">EXPOSURE BY EVENT</div>
          <table className="w-full leading-5">
            <thead>
              <tr className="text-muted text-[10px] tracking-wider">
                <th className="text-left px-1 py-0.5 font-normal">EVENT</th>
                <th className="text-right px-1 py-0.5 font-normal" title="yes − no contracts">
                  NET
                </th>
                <th className="text-right px-1 py-0.5 font-normal" title="P&L if event resolves YES">
                  IF YES
                </th>
                <th className="text-right px-1 py-0.5 font-normal" title="P&L if event resolves NO">
                  IF NO
                </th>
              </tr>
            </thead>
            <tbody>
              {r.by_event.map((e) => (
                <tr key={e.event_id} className="border-t border-line/50 text-text">
                  <td className="px-1 py-0.5 whitespace-nowrap overflow-hidden text-ellipsis max-w-40">
                    {e.event_id}
                  </td>
                  <td className="text-right px-1 tabular-nums">{qty(e.net_yes_contracts)}</td>
                  <td className="text-right px-1 tabular-nums">{signedUsd(e.delta_if_yes)}</td>
                  <td className="text-right px-1 tabular-nums">{signedUsd(e.delta_if_no)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <details className="text-[11px] text-muted">
        <summary className="cursor-pointer tracking-wider text-[10px]">
          ASSUMPTIONS · VaR horizon = resolution · MC seed {r.mc_seed} / {r.mc_draws.toLocaleString('en-US')} draws
        </summary>
        <ul className="mt-1 flex flex-col gap-0.5 list-disc pl-4">
          {r.assumptions.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      </details>
    </div>
  )
}
