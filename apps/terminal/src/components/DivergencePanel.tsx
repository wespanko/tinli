import type { DivergenceItem } from '../types'
import { cents, qty } from '../format'

function dirLabel(item: DivergenceItem): string {
  if (!item.direction) return '—'
  return item.direction === 'buy_yes_kalshi_no_polymarket' ? 'Y@K N@P' : 'Y@P N@K'
}

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
    <table className="w-full text-[12px] leading-5">
      <thead>
        <tr className="text-muted text-[10px] tracking-wider sticky top-0 bg-panel">
          <th className="text-left px-2 py-1 font-normal">PAIR</th>
          <th className="text-left px-1 py-1 font-normal" title="lock legs: YES venue / NO venue">
            LOCK
          </th>
          <th className="text-right px-1 py-1 font-normal" title="kalshi mid − polymarket mid">
            Δ¢
          </th>
          <th className="text-right px-1 py-1 font-normal" title="fee-adjusted edge per contract">
            EDGE¢
          </th>
          <th className="text-right px-1 py-1 font-normal" title="min top-of-book depth">
            SIZE
          </th>
          <th
            className="text-right px-2 py-1 font-normal"
            title="edge per contract at max size, exact venue fee rounding"
          >
            @SIZE¢
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((it) => {
          const active = it.event_key === selected
          const executable = it.edge_at_size != null && parseFloat(it.edge_at_size) > 0
          return (
            <tr
              key={it.event_key}
              onClick={() => onSelect(it.event_key)}
              className={`border-t border-line/50 cursor-pointer ${
                it.criteria_verified ? 'text-text' : 'text-muted'
              } ${active ? 'bg-line/30' : 'hover:bg-line/20'}`}
            >
              <td className="px-2 py-0.5 whitespace-nowrap overflow-hidden text-ellipsis max-w-36">
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
              <td className="px-1 whitespace-nowrap text-[11px]">{dirLabel(it)}</td>
              {/* raw_basis_cents is ALREADY in cents — no ×100 */}
              <td className="text-right px-1 tabular-nums">
                {it.raw_basis_cents == null ? '—' : parseFloat(it.raw_basis_cents).toFixed(1)}
              </td>
              <td className="text-right px-1 tabular-nums">
                {it.fee_adjusted_edge == null ? '—' : cents(it.fee_adjusted_edge, 2)}
                {it.fee_assumed_worst_case && (
                  <span className="text-gold" title="PM fee category unknown — worst-case rate assumed">
                    *
                  </span>
                )}
              </td>
              <td className="text-right px-1 tabular-nums">{qty(it.max_lock_size)}</td>
              <td
                className={`text-right px-2 tabular-nums ${
                  executable && it.criteria_verified ? 'text-gold' : ''
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
