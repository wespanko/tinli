import type { Pair } from '../types'
import { cents } from '../format'

function kalshiMid(p: Pair): number | null {
  const m = p.kalshi
  if (!m || m.best_bid == null || m.best_ask == null) return null
  return (parseFloat(m.best_bid) + parseFloat(m.best_ask)) / 2
}

export function basisCents(p: Pair): number | null {
  const mid = kalshiMid(p)
  if (mid == null || !p.polymarket) return null
  return (mid - parseFloat(p.polymarket.yes_price)) * 100
}

export function sortPairs(data: Pair[]): Pair[] {
  return [...data].sort((a, b) => {
    if (a.criteria_verified !== b.criteria_verified) return a.criteria_verified ? -1 : 1
    return Math.abs(basisCents(b) ?? 0) - Math.abs(basisCents(a) ?? 0)
  })
}

export default function WatchTable({
  pairs,
  selected,
  onSelect,
}: {
  pairs: Pair[]
  selected: string | null
  onSelect: (eventKey: string) => void
}) {
  return (
    <table className="w-full text-[12px] leading-5">
      <thead>
        <tr className="text-muted text-[10px] tracking-wider sticky top-0 bg-panel">
          <th className="text-left px-2 py-1 font-normal">PAIR</th>
          <th className="text-right px-1 py-1 font-normal">K BID</th>
          <th className="text-right px-1 py-1 font-normal">K ASK</th>
          <th className="text-right px-1 py-1 font-normal">PM</th>
          <th className="text-right px-2 py-1 font-normal">Δ¢</th>
        </tr>
      </thead>
      <tbody>
        {pairs.map((p) => {
          const basis = basisCents(p)
          const active = p.event_key === selected
          return (
            <tr
              key={p.event_key}
              onClick={() => onSelect(p.event_key)}
              className={`border-t border-line/50 text-text cursor-pointer ${
                active ? 'bg-line/30' : 'hover:bg-line/20'
              }`}
            >
              <td className="px-2 py-0.5 whitespace-nowrap overflow-hidden text-ellipsis max-w-44">
                <span className={active ? 'text-hover' : ''}>
                  {!p.criteria_verified && (
                    <span className="text-gold mr-1" title="resolution criteria not verified">
                      !
                    </span>
                  )}
                  {p.event_key}
                </span>
              </td>
              <td className="text-right px-1 tabular-nums">{cents(p.kalshi?.best_bid)}</td>
              <td className="text-right px-1 tabular-nums">{cents(p.kalshi?.best_ask)}</td>
              <td className="text-right px-1 tabular-nums">{cents(p.polymarket?.yes_price)}</td>
              <td
                className={`text-right px-2 tabular-nums ${
                  basis != null && Math.abs(basis) >= 1 ? 'text-gold' : 'text-muted'
                }`}
              >
                {basis == null ? '—' : basis.toFixed(1)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
