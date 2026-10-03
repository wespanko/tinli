import type { DivergenceItem } from '../types'
import { cents, qty } from '../format'
import { positiveEdge } from '../pairs'

/** Banner shown while any verified pair has a positive fee-adjusted edge at
    executable size. Clicking an entry loads the pair. */

export function liveEdges(items: DivergenceItem[]): DivergenceItem[] {
  return items.filter((d) => d.criteria_verified && positiveEdge(d.edge_at_size))
}

export default function EdgeAlert({
  edges,
  onSelect,
}: {
  edges: DivergenceItem[]
  onSelect: (eventKey: string) => void
}) {
  if (!edges.length) return null
  return (
    <div className="flex items-center gap-4 border border-gold bg-panel rounded-sm px-3 py-1.5 shrink-0">
      <span className="label text-gold">Live edge</span>
      {edges.map((e) => (
        <button
          key={e.event_key}
          onClick={() => onSelect(e.event_key)}
          className="text-[12px] text-gold hover:underline"
        >
          {e.question}{' '}
          <span className="font-mono">
            +{cents(e.edge_at_size, 2)}¢ × {qty(e.max_lock_size)}
          </span>
        </button>
      ))}
    </div>
  )
}
