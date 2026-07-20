import { useState } from 'react'
import type { LockReport, SizePoint } from '../types.gen'
import { cents, qty, usd } from '../format'

/** Depth-walked lock curve from /v1/lock: per-contract edge vs cumulative
    size across the FULL books, exact per-level fees. The curve keeps going
    past the optimal so the decay (and the moment the lock turns into a
    donation) is visible. Marks follow DepthChart: 2px line, thin gold
    markers, text in HTML never SVG. */

const W = 400
const H = 88

export default function LockPanel({ lock }: { lock: LockReport }) {
  const [hover, setHover] = useState<SizePoint | null>(null)

  const dir =
    lock.direction === 'buy_yes_kalshi_no_polymarket'
      ? 'YES @ KALSHI + NO @ POLYMARKET'
      : lock.direction === 'buy_yes_polymarket_no_kalshi'
        ? 'YES @ POLYMARKET + NO @ KALSHI'
        : 'no executable lock (missing book side)'

  const pts = lock.points
  const maxSize = pts.length ? parseFloat(pts[pts.length - 1].size) : 0
  const edges = pts.map((p) => parseFloat(p.per_contract_edge) * 100)
  const yLo = Math.min(0, ...edges)
  const yHi = Math.max(0.5, ...edges) // ≥0.5¢ of headroom so a flat curve still reads
  const x = (size: number) => (size / Math.max(1, maxSize)) * W
  const y = (edgeC: number) => 4 + (1 - (edgeC - yLo) / (yHi - yLo)) * (H - 8)
  const line = pts
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(parseFloat(p.size))} ${y(parseFloat(p.per_contract_edge) * 100)}`)
    .join(' ')

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!pts.length) return
    const rect = e.currentTarget.getBoundingClientRect()
    const size = ((e.clientX - rect.left) / rect.width) * maxSize
    // first breakpoint covering this size — the walk fills levels in order
    setHover(pts.find((p) => parseFloat(p.size) >= size) ?? pts[pts.length - 1])
  }

  const stat = (label: string, node: React.ReactNode, sub?: string) => (
    <div className="bg-panel-2 border border-line rounded-sm px-3 py-1.5">
      <div className="text-muted text-[10px] tracking-[0.12em]">{label}</div>
      <div className="font-mono text-[15px]">{node}</div>
      {sub && <div className="font-mono text-[10px] text-muted">{sub}</div>}
    </div>
  )

  const opt = lock.optimal
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1.5">
        <span className="text-muted text-[10px] tracking-[0.15em]">LOCK · DEPTH-WALKED</span>
        <span className="text-text text-[12px]">{dir}</span>
        {lock.fee_assumed_worst_case && (
          <span className="text-gold text-[10px]" title="PM fee category unknown — worst published rate assumed">
            WORST-CASE FEE
          </span>
        )}
        {!lock.criteria_verified && (
          <span className="text-gold text-[10px]">! UNVERIFIED</span>
        )}
      </div>

      {pts.length > 0 && (
        <div className="border border-line rounded-sm mb-1.5">
          <div className="flex items-center border-b border-line px-2.5 h-7">
            <span className="text-muted text-[10px] tracking-[0.15em]">EDGE / CONTRACT vs SIZE</span>
            <span className="ml-auto font-mono text-[10px] text-muted">
              {hover
                ? `${qty(hover.size)} → ${cents(hover.per_contract_edge, 2)}¢ · ${usd(hover.total_profit)} profit`
                : lock.depth_exhausted
                  ? `full depth · ${qty(String(maxSize))} contracts`
                  : `first ${qty(String(maxSize))} contracts (curve capped)`}
            </span>
          </div>
          <div className="px-2.5 py-1.5">
            <svg
              viewBox={`0 0 ${W} ${H}`}
              preserveAspectRatio="none"
              className="w-full h-[88px] block cursor-crosshair"
              onMouseMove={onMove}
              onMouseLeave={() => setHover(null)}
            >
              {/* zero-edge line: below this the lock loses money */}
              <line
                x1="0" x2={W} y1={y(0)} y2={y(0)}
                stroke="var(--color-line)" strokeWidth="1"
                strokeDasharray="3 3" vectorEffect="non-scaling-stroke"
              />
              <path
                d={line} fill="none" stroke="var(--color-primary)"
                strokeWidth="2" vectorEffect="non-scaling-stroke"
              />
              {opt && (
                <line
                  x1={x(parseFloat(opt.size))} x2={x(parseFloat(opt.size))} y1="0" y2={H}
                  stroke="var(--color-gold)" strokeWidth="1" vectorEffect="non-scaling-stroke"
                />
              )}
              {hover && (
                <line
                  x1={x(parseFloat(hover.size))} x2={x(parseFloat(hover.size))} y1="0" y2={H}
                  stroke="var(--color-muted)" strokeWidth="1" opacity="0.6"
                  vectorEffect="non-scaling-stroke"
                />
              )}
            </svg>
            <div className="flex justify-between font-mono text-[10px] text-muted leading-4">
              <span>0</span>
              <span>{opt ? `optimal ${qty(opt.size)}` : 'no profitable size'}</span>
              <span>{qty(String(maxSize))}</span>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-4 gap-1.5">
        {stat(
          'OPTIMAL SIZE',
          opt ? <span className="tabular-nums text-text">{qty(opt.size)}</span> : <span className="text-muted">—</span>,
          opt ? `avg ${cents(opt.avg_yes, 1)}¢ yes / ${cents(opt.avg_no, 1)}¢ no` : undefined,
        )}
        {stat(
          'LOCKED PROFIT',
          opt ? <span className="tabular-nums text-gold">{usd(opt.total_profit)}</span> : <span className="text-muted">—</span>,
          opt ? `${cents(opt.per_contract_edge, 2)}¢ / contract` : undefined,
        )}
        {stat(
          'CAPITAL REQUIRED',
          opt ? <span className="tabular-nums text-text">{usd(opt.capital)}</span> : <span className="text-muted">—</span>,
          'both legs + all fees',
        )}
        {stat(
          'ANNUALIZED',
          lock.annualized_return != null ? (
            <span className="tabular-nums text-text">
              {(parseFloat(lock.annualized_return) * 100).toFixed(1)}%
            </span>
          ) : (
            <span className="text-muted">—</span>
          ),
          lock.days_to_resolution != null
            ? `${parseFloat(lock.days_to_resolution).toFixed(1)}d to close`
            : 'no close time',
        )}
      </div>

      <details className="mt-1.5">
        <summary className="text-muted text-[10px] tracking-[0.12em] cursor-pointer hover:text-hover">
          ASSUMPTIONS ({lock.assumptions.length})
        </summary>
        <ul className="text-muted text-[11px] mt-1 space-y-0.5 list-disc list-inside">
          {lock.assumptions.map((a) => (
            <li key={a} className={a.startsWith('UNVERIFIED') ? 'text-gold' : undefined}>{a}</li>
          ))}
        </ul>
      </details>
    </div>
  )
}
