import { useState } from 'react'
import type { BasisStats, HistoryPoint } from '../types'
import { clock } from '../format'

/** Basis over time for the selected pair, from recorded snapshots. 2px
    line, hairline zero baseline, hover crosshair with the readout in the
    header. No history means saying so, never a fake backfill. Window stats
    (mean, σ, z, AR(1) half-life) arrive pre-rounded against the signal; a
    missing statistic renders as a dash with the reason in the tooltip. */

const W = 800
const H = 110

// stats values are already in cents
const c = (v: string, dp = 2) => {
  const n = parseFloat(v)
  return `${n > 0 ? '+' : ''}${n.toFixed(dp)}`
}

export default function BasisChart({
  points,
  stats,
}: {
  points: HistoryPoint[]
  stats: BasisStats | null
}) {
  const [hover, setHover] = useState<number | null>(null)

  const pts = points
    .filter((p) => p.raw_basis_cents != null)
    .map((p) => ({ t: new Date(p.ts).getTime(), v: parseFloat(p.raw_basis_cents!) }))

  if (pts.length < 2) {
    return (
      <div className="border border-line rounded-sm">
        <div className="flex items-center border-b border-line px-2.5 h-7">
          <span className="label">Basis · 24h</span>
        </div>
        <div className="p-2.5 text-muted text-[11px]">
          {pts.length === 0 ? 'No history recorded yet.' : 'One snapshot so far.'}
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
        <span className="label">Basis · 24h</span>
        <span className="ml-auto font-mono text-[10px] text-muted">
          {hovered
            ? `${clock(new Date(hovered.t).toISOString())} · ${hovered.v > 0 ? '+' : ''}${hovered.v.toFixed(2)}¢`
            : `${pts.length} snapshots · last ${last.v > 0 ? '+' : ''}${last.v.toFixed(2)}¢`}
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
          <span>Kalshi mid − Polymarket mid, ¢</span>
          <span>{clock(new Date(t1).toISOString())}</span>
        </div>
      </div>
      {stats && stats.n >= 2 && stats.mean_cents != null && stats.stdev_cents != null && (
        <div className="flex items-center gap-4 border-t border-line px-2.5 h-6 font-mono text-[10px]">
          <span>
            <span className="text-muted">μ </span>
            <span className="text-text">{c(stats.mean_cents)}¢</span>
          </span>
          <span>
            <span className="text-muted">σ </span>
            <span className="text-text">{parseFloat(stats.stdev_cents).toFixed(2)}¢</span>
          </span>
          <span title="latest basis minus the window mean, in σ, rounded toward zero">
            <span className="text-muted">z </span>
            {stats.z_last != null ? (
              <span className="text-text">{c(stats.z_last)}</span>
            ) : (
              <span className="text-muted">—</span>
            )}
          </span>
          <span
            title={
              stats.half_life_hours != null
                ? `AR(1) φ=${parseFloat(stats.ar1_phi!).toFixed(2)}; hours via the median snapshot spacing, rounded up`
                : 'no measurable mean reversion in the window (needs 30+ snapshots and 0 < φ < 1)'
            }
          >
            <span className="text-muted">t½ </span>
            {stats.half_life_hours != null ? (
              <span className="text-text">≈{parseFloat(stats.half_life_hours).toFixed(1)}h</span>
            ) : (
              <span className="text-muted">—</span>
            )}
          </span>
        </div>
      )}
    </div>
  )
}
