import type { DivergenceItem } from '../types'
import { cents, qty } from '../format'

/** Banner shown while any VERIFIED pair has a positive fee-adjusted edge at
    executable size — the one signal this product exists to catch. Clicking
    an entry loads the pair in the market panel. */

export function liveEdges(items: DivergenceItem[]): DivergenceItem[] {
  return items.filter(
    (d) => d.criteria_verified && d.edge_at_size != null && parseFloat(d.edge_at_size) > 0,
  )
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
    <div className="flex items-center gap-3 border border-gold bg-panel rounded-sm px-3 py-1.5 shrink-0">
      <span className="text-gold text-[10px] font-sans font-medium tracking-[0.2em]">
        LIVE EDGE
      </span>
      {edges.map((e) => (
        <button
          key={e.event_key}
          onClick={() => onSelect(e.event_key)}
          className="font-mono text-[12px] text-gold hover:underline"
          title={`${e.question} — click to load`}
        >
          {e.event_key} +{cents(e.edge_at_size, 2)}¢ × {qty(e.max_lock_size)}
        </button>
      ))}
      <span className="ml-auto text-muted text-[10px]">
        fee-adjusted, at executable size — verify criteria before trading
      </span>
    </div>
  )
}
