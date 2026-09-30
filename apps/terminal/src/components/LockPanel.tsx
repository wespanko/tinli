import { useState } from 'react'
import type { LockReport, SizePoint } from '../types.gen'
import { cents, qty, usd } from '../format'
import Stat from './Stat'

/** Depth-walked lock curve from /v1/lock: per-contract edge against
    cumulative size across the full books, exact per-level fees. The curve
    keeps going past the optimum so the decay is visible. Shapes in SVG,
    text in HTML. */

const W = 400
const H = 88

export default function LockPanel({ lock }: { lock: LockReport }) {
  const [hover, setHover] = useState<SizePoint | null>(null)

  const dir =
    lock.direction === 'buy_yes_kalshi_no_polymarket'
      ? 'YES on Kalshi, NO on Polymarket'
      : lock.direction === 'buy_yes_polymarket_no_kalshi'
        ? 'YES on Polymarket, NO on Kalshi'
        : 'no executable lock'

  const pts = lock.points
  const maxSize = pts.length ? parseFloat(pts[pts.length - 1].size) : 0
  const edges = pts.map((p) => parseFloat(p.per_contract_edge) * 100)
  const yLo = Math.min(0, ...edges)
  const yHi = Math.max(0.5, ...edges) // half a cent of headroom so a flat curve still reads
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

  const opt = lock.optimal
  const first = pts[0]
  const days =
    lock.days_to_resolution != null ? `${parseFloat(lock.days_to_resolution).toFixed(1)}d to close` : null

  return (
    <div>
      <div className="flex items-baseline gap-2 mb-2">
        <span className="label">Lock</span>
        <span className="text-text text-[12px]">{dir}</span>
        {lock.fee_assumed_worst_case && (
          <span className="label text-gold" title="Polymarket fee category unknown; worst published rate assumed">
            worst-case fee
          </span>
        )}
        {!lock.criteria_verified && <span className="label text-gold">unverified</span>}
      </div>

      {pts.length > 0 && (
        <div className="border border-line rounded-sm mb-2">
          <div className="flex items-center border-b border-line px-2.5 h-7">
            <span className="label">Edge per contract vs size</span>
            <span className="ml-auto font-mono text-[10px] text-muted">
              {hover
                ? `${qty(hover.size)} → ${cents(hover.per_contract_edge, 2)}¢ · ${usd(hover.total_profit)}`
                : lock.depth_exhausted
                  ? `full depth · ${qty(String(maxSize))} contracts`
                  : `first ${qty(String(maxSize))} contracts`}
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
              {/* zero-edge line: below it the lock loses money */}
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
              <span>{opt ? `optimal ${qty(opt.size)}` : ''}</span>
              <span>{qty(String(maxSize))}</span>
            </div>
          </div>
        </div>
      )}

      {opt ? (
        <div className="flex gap-8">
          <Stat
            label="Optimal size"
            value={qty(opt.size)}
            sub={`${cents(opt.avg_yes, 1)}¢ yes · ${cents(opt.avg_no, 1)}¢ no`}
          />
          <Stat
            label="Locked profit"
            value={<span className="text-gold">{usd(opt.total_profit)}</span>}
            sub={`${cents(opt.per_contract_edge, 2)}¢ / contract`}
          />
          <Stat label="Capital" value={usd(opt.capital)} sub="both legs and fees" />
          <Stat
            label="Annualized"
            value={
              lock.annualized_return != null
                ? `${(parseFloat(lock.annualized_return) * 100).toFixed(1)}%`
                : '—'
            }
            sub={days ?? 'no close time'}
          />
        </div>
      ) : (
        <div className="text-[12px] text-muted">
          No profitable size at the current books.
          {first && (
            <>
              {' '}The first contract clears{' '}
              <span className="font-mono text-text">{cents(first.per_contract_edge, 2)}¢</span> after
              fees.
            </>
          )}
          {days && <span className="font-mono"> · {days}</span>}
        </div>
      )}

      <details className="mt-2">
        <summary className="label cursor-pointer hover:text-hover">
          Assumptions ({lock.assumptions.length})
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
