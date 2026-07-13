import type { RiskReport } from '../types'
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

export default function RiskPanel({ report }: { report: RiskReport | null }) {
  if (!report) return <div className="p-3 text-muted text-[12px]">loading risk…</div>
  const r = report
  return (
    <div className="p-3 flex flex-col gap-3 text-[13px]">
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

      {r.unmarked_positions > 0 && (
        <div className="text-gold text-[11px]">
          ! {r.unmarked_positions} position(s) not in the feed — excluded from all numbers above
        </div>
      )}

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
                title={row.question ?? row.position.market_id}
              >
                {row.mark == null && (
                  <span className="text-gold mr-1" title="not in market feed — unmarked">
                    !
                  </span>
                )}
                {row.event_id ?? row.position.market_id}
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

      {r.by_event.length > 0 && (
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
                  <td className="font-sans py-1.5 pr-1 whitespace-nowrap overflow-hidden text-ellipsis max-w-40 text-text">
                    {e.event_id}
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
