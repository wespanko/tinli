import type { DivergenceItem } from '../types'
import { cents, qty } from '../format'
import Signed from './Signed'

function dirLabel(item: DivergenceItem): string {
  if (!item.direction) return '—'
  return item.direction === 'buy_yes_kalshi_no_polymarket' ? 'K→P' : 'P→K'
}

const th = 'py-1.5 font-sans font-medium text-[10px] tracking-[0.12em] text-muted'

export default function DivergencePanel({
  items,
  selected,
  onSelect,
}: {
  items: DivergenceItem[]
  selected: string | null
  onSelect: (eventKey: string) => void
}) {
  return (
    <table className="w-full font-mono text-[12px]">
      <thead>
        <tr className="sticky top-0 bg-panel border-b border-line">
          <th className={`${th} text-left pl-3`}>PAIR</th>
          <th className={`${th} text-left px-1`} title="lock legs: YES venue → NO venue">
            LOCK
          </th>
          <th className={`${th} text-right px-1`} title="kalshi mid − polymarket mid, cents">
            Δ¢
          </th>
          <th className={`${th} text-right px-1`} title="fee-adjusted edge per contract, cents">
            EDGE¢
          </th>
          <th className={`${th} text-right px-1`} title="min top-of-book depth">
            SIZE
          </th>
          <th
            className={`${th} text-right px-3`}
            title="edge per contract at max size, exact venue fee rounding"
          >
            @SIZE¢
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((it) => {
          const active = it.event_key === selected
          const executable =
            it.criteria_verified && it.edge_at_size != null && parseFloat(it.edge_at_size) > 0
          return (
            <tr
              key={it.event_key}
              onClick={() => onSelect(it.event_key)}
              className={`cursor-pointer border-b border-line/30 border-l-2 ${
                active
                  ? 'border-l-primary bg-primary/10'
                  : 'border-l-transparent hover:bg-line/20'
              }`}
            >
              <td
                className={`pl-3 pr-1 py-[5px] whitespace-nowrap overflow-hidden text-ellipsis max-w-36 ${
                  active ? 'text-hover' : it.criteria_verified ? 'text-text' : 'text-muted'
                }`}
              >
                {!it.criteria_verified && (
                  <span
                    className="text-gold mr-1"
                    title="resolution criteria not verified — gap is not edge"
                  >
                    !
                  </span>
                )}
                {it.event_key}
              </td>
              <td
                className="px-1 text-[11px] text-muted whitespace-nowrap"
                title={
                  it.direction == null
                    ? 'no executable lock'
                    : it.direction === 'buy_yes_kalshi_no_polymarket'
                      ? 'buy YES on Kalshi, NO on Polymarket'
                      : 'buy YES on Polymarket, NO on Kalshi'
                }
              >
                {dirLabel(it)}
              </td>
              {/* raw_basis_cents is ALREADY in cents — no ×100 */}
              <td className="text-right px-1">
                <Signed
                  value={it.raw_basis_cents}
                  text={
                    it.raw_basis_cents == null
                      ? '—'
                      : `${parseFloat(it.raw_basis_cents) > 0 ? '+' : ''}${parseFloat(
                          it.raw_basis_cents,
                        ).toFixed(1)}`
                  }
                />
              </td>
              <td className="text-right px-1 tabular-nums text-muted">
                {it.fee_adjusted_edge == null ? '—' : cents(it.fee_adjusted_edge, 2)}
                {it.fee_assumed_worst_case && (
                  <span
                    className="text-gold"
                    title="PM fee category unknown — worst-case rate assumed"
                  >
                    *
                  </span>
                )}
              </td>
              <td className="text-right px-1 tabular-nums text-muted">{qty(it.max_lock_size)}</td>
              <td
                className={`text-right px-3 tabular-nums ${
                  executable ? 'text-gold' : 'text-muted'
                }`}
              >
                {it.edge_at_size == null ? '—' : cents(it.edge_at_size, 2)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
