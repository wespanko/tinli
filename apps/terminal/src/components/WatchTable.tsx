import type { Pair } from '../types'
import { cents } from '../format'
import Signed from './Signed'

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

const th = 'py-1.5 font-sans font-medium text-[10px] tracking-[0.12em] text-muted'

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
    <table className="w-full font-mono text-[13px]">
      <thead>
        <tr className="sticky top-0 bg-panel border-b border-line">
          <th className={`${th} text-left pl-3`}>PAIR</th>
          <th className={`${th} text-right px-1`}>K BID</th>
          <th className={`${th} text-right px-1`}>K ASK</th>
          <th className={`${th} text-right px-1`}>PM</th>
          <th className={`${th} text-right px-3`}>Δ¢</th>
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
              className={`cursor-pointer border-b border-line/30 border-l-2 ${
                active
                  ? 'border-l-primary bg-primary/10'
                  : 'border-l-transparent hover:bg-line/20'
              }`}
            >
              {/* display names, not slugs — the slug lives in the tooltip */}
              <td
                className={`font-sans pl-3 pr-1 py-1.5 whitespace-nowrap overflow-hidden text-ellipsis max-w-52 ${
                  active ? 'text-hover' : p.criteria_verified ? 'text-text' : 'text-muted'
                }`}
                title={p.event_key}
              >
                {!p.criteria_verified && (
                  <span className="text-gold mr-1" title="resolution criteria not verified">
                    !
                  </span>
                )}
                {p.question}
              </td>
              <td className="text-right px-1 tabular-nums text-text">
                {cents(p.kalshi?.best_bid)}
              </td>
              <td className="text-right px-1 tabular-nums text-text">
                {cents(p.kalshi?.best_ask)}
              </td>
              <td className="text-right px-1 tabular-nums text-text">
                {cents(p.polymarket?.yes_price)}
              </td>
              <td className="text-right px-3">
                {/* |Δ| >= 1¢ is a KEY NUMBER: gold overrides the sign color */}
                {basis != null && Math.abs(basis) >= 1 ? (
                  <span className="tabular-nums text-gold">
                    {`${basis > 0 ? '+' : ''}${basis.toFixed(1)}`}
                  </span>
                ) : (
                  <Signed
                    value={basis}
                    text={basis == null ? '—' : `${basis > 0 ? '+' : ''}${basis.toFixed(1)}`}
                  />
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
