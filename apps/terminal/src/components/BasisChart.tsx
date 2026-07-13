import { useState } from 'react'
import type { HistoryPoint } from '../types'
import { clock } from '../format'

/** Basis-over-time line for the selected pair, from recorded snapshots
    (/v1/history). 2px line, hairline zero baseline, hover crosshair with
    the readout in the header. No history recorded -> say so; never fake a
    backfill. */

const W = 800
const H = 110

export default function BasisChart({ points }: { points: HistoryPoint[] }) {
  const [hover, setHover] = useState<number | null>(null)

  const pts = points
    .filter((p) => p.raw_basis_cents != null)
    .map((p) => ({ t: new Date(p.ts).getTime(), v: parseFloat(p.raw_basis_cents!) }))

  if (pts.length < 2) {
    return (
      <div className="border border-line rounded-sm">
        <div className="flex items-center border-b border-line px-2.5 h-7">
          <span className="text-muted text-[10px] tracking-[0.15em]">BASIS · 24H</span>
        </div>
        <div className="p-2.5 text-muted text-[11px]">
          {pts.length === 0
            ? 'no history recorded yet — run `make snapshot` (or scripts/snapshot.py --loop 30)'
            : 'one snapshot recorded — need at least two points to draw a line'}
        </div>
      </div>
    )
  }

  const t0 = pts[0].t
  const t1 = pts[pts.length - 1].t
  const vals = pts.map((p) => p.v)
  const lo = Math.min(0, ...vals)
  const hi = Math.max(0, ...vals)
  const pad = Math.max((hi - lo) * 0.1, 0.1)
  const yLo = lo - pad
  const yHi = hi + pad
  const x = (t: number) => ((t - t0) / Math.max(1, t1 - t0)) * W
  const y = (v: number) => H - ((v - yLo) / (yHi - yLo)) * H
  const line = pts.map((p, i) => `${i ? 'L' : 'M'} ${x(p.t)} ${y(p.v)}`).join(' ')

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const t = t0 + ((e.clientX - rect.left) / rect.width) * (t1 - t0)
    let best = 0
    for (let i = 1; i < pts.length; i++) {
      if (Math.abs(pts[i].t - t) < Math.abs(pts[best].t - t)) best = i
    }
    setHover(best)
  }

  const hovered = hover != null ? pts[hover] : null
  const last = pts[pts.length - 1]

  return (
    <div className="border border-line rounded-sm">
      <div className="flex items-center border-b border-line px-2.5 h-7">
        <span className="text-muted text-[10px] tracking-[0.15em]">
          BASIS · 24H · {pts.length} SNAPSHOTS
        </span>
        <span className="ml-auto font-mono text-[10px] text-muted">
          {hovered
            ? `${clock(new Date(hovered.t).toISOString())} · ${hovered.v > 0 ? '+' : ''}${hovered.v.toFixed(2)}¢`
            : `last ${last.v > 0 ? '+' : ''}${last.v.toFixed(2)}¢`}
        </span>
      </div>
      <div className="px-2.5 py-1.5">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="w-full h-24 block cursor-crosshair"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          {/* zero baseline: one hairline, solid, recessive */}
          <line
            x1="0"
            x2={W}
            y1={y(0)}
            y2={y(0)}
            stroke="var(--color-line)"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
          <path
            d={line}
            fill="none"
            stroke="var(--color-primary)"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
          {hovered && (
            <>
              <line
                x1={x(hovered.t)}
                x2={x(hovered.t)}
                y1="0"
                y2={H}
                stroke="var(--color-muted)"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
                opacity="0.6"
              />
              <circle cx={x(hovered.t)} cy={y(hovered.v)} r="4" fill="var(--color-primary)" stroke="var(--color-panel)" strokeWidth="2" />
            </>
          )}
        </svg>
        <div className="flex justify-between font-mono text-[10px] text-muted leading-4">
          <span>{clock(new Date(t0).toISOString())}</span>
          <span>kalshi mid − polymarket mid, ¢</span>
          <span>{clock(new Date(t1).toISOString())}</span>
        </div>
      </div>
    </div>
  )
}
