import type { AccountReport, Pair } from '../types'
import { cents, qty, signedUsd, usd } from '../format'
import Signed from './Signed'

const th = 'py-1 font-sans font-medium text-[10px] tracking-[0.12em] text-muted'

/** Real Kalshi book via BYOK (M9). Read-only: GETs with the user's own key,
 * never merged with the self-reported book, never an order. */
export default function AccountPanel({
  report,
  pairs,
}: {
  report: AccountReport | null
  pairs: Pair[]
}) {
  if (!report) return <div className="p-3 text-muted text-[12px]">loading account…</div>

  if (!report.byok) {
    return (
      <div className="p-3 text-[11px] text-muted leading-snug">
        <span className="text-text">BYOK off.</span> Set{' '}
        <span className="font-mono">TINLI_KALSHI_KEY_ID</span> +{' '}
        <span className="font-mono">TINLI_KALSHI_PRIVATE_KEY_PATH</span> in .env to see your real
        Kalshi book here — read-only, your key never leaves this machine.
      </div>
    )
  }

  const eventName = (key: string | null) =>
    key == null ? null : pairs.find((p) => p.event_key === key)?.question ?? key

  return (
    <div className="p-3 flex flex-col gap-3 text-[13px]">
      <div className="grid grid-cols-3 gap-1.5">
        <div className="bg-panel-2 border border-line rounded-sm px-3 py-1.5">
          <div className="text-muted text-[10px] tracking-[0.12em]">MKT VALUE</div>
          <div className="font-mono text-[15px] text-text">{usd(report.total_market_value)}</div>
        </div>
        <div className="bg-panel-2 border border-line rounded-sm px-3 py-1.5">
          <div className="text-muted text-[10px] tracking-[0.12em]">COST BASIS</div>
          <div className="font-mono text-[15px] text-text">{usd(report.total_cost_basis)}</div>
        </div>
        <div className="bg-panel-2 border border-line rounded-sm px-3 py-1.5">
          <div className="text-muted text-[10px] tracking-[0.12em]">UNREALIZED P&L</div>
          <div className="font-mono text-[15px]">
            <Signed
              value={report.total_unrealized_pnl}
              text={signedUsd(report.total_unrealized_pnl)}
            />
          </div>
        </div>
      </div>

      {report.unmarked_positions > 0 && (
        <div className="text-gold text-[11px]">
          ! {report.unmarked_positions} position(s) without a live quote — excluded from totals
        </div>
      )}

      {report.positions.length === 0 ? (
        <div className="text-muted text-[12px]">no open positions in this account</div>
      ) : (
        <table className="w-full font-mono">
          <thead>
            <tr className="border-b border-line">
              <th className={`${th} text-left`}>MARKET</th>
              <th className={`${th} text-left px-1`}>SIDE</th>
              <th className={`${th} text-right px-1`}>QTY</th>
              <th className={`${th} text-right px-1`} title="venue-reported cost of the open position">
                COST
              </th>
              <th className={`${th} text-right px-1`}>MARK</th>
              <th className={`${th} text-right pl-1`}>P&L</th>
            </tr>
          </thead>
          <tbody>
            {report.positions.map((row, i) => (
              <tr key={i} className="border-b border-line/30">
                <td
                  className={`font-sans py-1.5 pr-1 whitespace-nowrap overflow-hidden text-ellipsis max-w-40 ${
                    row.mark == null ? 'text-muted' : 'text-text'
                  }`}
                  title={row.position.ticker}
                >
                  {row.mark == null && (
                    <span className="text-gold mr-1" title="no live quote — unmarked">
                      !
                    </span>
                  )}
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
        <summary className="cursor-pointer tracking-[0.12em] text-[10px]">ASSUMPTIONS</summary>
        <ul className="mt-1.5 flex flex-col gap-1 list-disc pl-4 leading-snug">
          {report.assumptions.map((a: string, i: number) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      </details>
    </div>
  )
}
