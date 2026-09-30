import type { AccountReport, Pair } from '../types'
import { cents, qty, signedUsd, usd } from '../format'
import Signed from './Signed'
import Stat from './Stat'

/** Real Kalshi book via the user's own key. Read-only, never merged with
    the self-reported book, never an order. */
export default function AccountPanel({
  report,
  pairs,
}: {
  report: AccountReport | null
  pairs: Pair[]
}) {
  if (!report) return <div className="p-3 text-muted text-[12px]">loading…</div>

  if (!report.byok) {
    return (
      <div className="p-3 text-[11px] text-muted leading-snug">
        No Kalshi key configured. Set{' '}
        <span className="font-mono">TINLI_KALSHI_KEY_ID</span> and{' '}
        <span className="font-mono">TINLI_KALSHI_PRIVATE_KEY_PATH</span> in .env to see your
        account here. The key never leaves this machine.
      </div>
    )
  }

  const eventName = (key: string | null) =>
    key == null ? null : pairs.find((p) => p.event_key === key)?.question ?? key

  return (
    <div className="p-3 flex flex-col gap-4 text-[13px]">
      <div className="flex flex-wrap gap-x-10 gap-y-3">
        <Stat label="Market value" value={usd(report.total_market_value)} />
        <Stat label="Cost basis" value={usd(report.total_cost_basis)} />
        <Stat
          label="Unrealized P&L"
          value={<Signed value={report.total_unrealized_pnl} text={signedUsd(report.total_unrealized_pnl)} />}
        />
      </div>

      {report.unmarked_positions > 0 && (
        <div className="text-gold text-[11px]">
          {report.unmarked_positions} position{report.unmarked_positions === 1 ? '' : 's'} without a live quote, excluded from totals
        </div>
      )}

      {report.positions.length === 0 ? (
        <div className="text-muted text-[12px]">no open positions in this account</div>
      ) : (
        <table className="w-full font-mono">
          <thead>
            <tr className="border-b border-line">
              <th className="th text-left">Market</th>
              <th className="th text-left px-1">Side</th>
              <th className="th text-right px-1">Qty</th>
              <th className="th text-right px-1" title="venue-reported cost of the open position">
                Cost
              </th>
              <th className="th text-right px-1">Mark</th>
              <th className="th text-right pl-1">P&L</th>
            </tr>
          </thead>
          <tbody>
            {report.positions.map((row, i) => (
              <tr key={i} className="border-b border-line/30">
                <td
                  className={`font-sans py-1.5 pr-1 whitespace-nowrap overflow-hidden text-ellipsis max-w-40 ${
                    row.mark == null ? 'text-muted' : 'text-text'
                  }`}
                  title={row.mark == null ? 'no live quote' : row.position.ticker}
                >
                  {eventName(row.event_key) ?? row.position.ticker}
                </td>
                <td className="px-1 uppercase text-[11px] text-muted">{row.position.side}</td>
                <td className="text-right px-1 tabular-nums text-text">
                  {qty(row.position.contracts)}
                </td>
                <td className="text-right px-1 tabular-nums text-muted">
                  {usd(row.position.cost_basis)}
                </td>
                <td className="text-right px-1 tabular-nums text-text">{cents(row.mark)}</td>
                <td className="text-right pl-1">
                  <Signed value={row.unrealized_pnl} text={signedUsd(row.unrealized_pnl)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <details className="text-[11px] text-muted">
        <summary className="label cursor-pointer hover:text-hover">Assumptions</summary>
        <ul className="mt-1.5 flex flex-col gap-1 list-disc pl-4 leading-snug">
          {report.assumptions.map((a: string, i: number) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      </details>
    </div>
  )
}
