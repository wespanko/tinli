import { useState } from 'react'
import type { DivergenceItem, LockReport, SizePoint } from '../types'
import { cents, money, qty, signedCents, signedMoney } from '../format'
import Stat from './Stat'

/** The lock, sized. Leads with what the reader's bankroll buys (or the
    profit-maximizing size without one), says plainly when the lock loses
    money and how far the gap must close, then the depth-walked curve and
    the book-level numbers. */

const W = 400
const H = 88

export function annualize(profit: string, capital: string, days: string | null): number | null {
  const c = parseFloat(capital)
  const d = days == null ? null : parseFloat(days)
  if (!c || d == null || d <= 0) return null
  return (parseFloat(profit) / c) * (365 / d)
}

function dirText(direction: string | null): string {
  return direction === 'buy_yes_kalshi_no_polymarket'
    ? 'YES on Kalshi, NO on Polymarket'
    : direction === 'buy_yes_polymarket_no_kalshi'
      ? 'YES on Polymarket, NO on Kalshi'
      : 'no executable lock'
}

function bindingText(b: 'bankroll' | 'depth' | 'edge'): string {
  return b === 'bankroll'
    ? 'limited by bankroll'
    : b === 'depth'
      ? 'limited by book depth'
      : 'stopped where the next contract loses money'
}

export default function LockSizing({
  lock,
  item,
  bankroll,
}: {
  lock: LockReport | null
  item: DivergenceItem | null
  bankroll: number | null
}) {
  const [hover, setHover] = useState<SizePoint | null>(null)

  if (!lock || lock.points.length === 0) {
    return (
      <div>
        <div className="label mb-2">Lock</div>
        <div className="text-[12px] text-muted">
          {lock ? 'No executable lock: one side of a book is empty.' : 'Loading the books…'}
        </div>
      </div>
    )
  }

  const pts = lock.points
  const first = pts[0]
  const opt = lock.optimal
  const fill = lock.for_bankroll
  const days = lock.days_to_resolution
  const daysText = days != null ? `${parseFloat(days).toFixed(1)}d to close` : 'no close time'
  const losing = parseFloat(first.per_contract_edge) < 0
  const breakEven = lock.break_even_cents != null ? parseFloat(lock.break_even_cents) : null
  const depthText = lock.depth_contracts != null ? qty(lock.depth_contracts) : `${qty(pts[pts.length - 1].size)}+`

  const maxSize = parseFloat(pts[pts.length - 1].size)
  const edges = pts.map((p) => parseFloat(p.per_contract_edge) * 100)
  const yLo = Math.min(0, ...edges)
  const yHi = Math.max(0.5, ...edges)
  const x = (size: number) => (size / Math.max(1, maxSize)) * W
  const y = (edgeC: number) => 4 + (1 - (edgeC - yLo) / (yHi - yLo)) * (H - 8)
  const line = pts
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(parseFloat(p.size))} ${y(parseFloat(p.per_contract_edge) * 100)}`)
    .join(' ')
  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const size = ((e.clientX - rect.left) / rect.width) * maxSize
    setHover(pts.find((p) => parseFloat(p.size) >= size) ?? pts[pts.length - 1])
  }

  const legs = (p: SizePoint) =>
    lock.direction === 'buy_yes_kalshi_no_polymarket'
      ? `YES ${cents(p.avg_yes)}¢ Kalshi · NO ${cents(p.avg_no)}¢ Polymarket`
      : `YES ${cents(p.avg_yes)}¢ Polymarket · NO ${cents(p.avg_no)}¢ Kalshi`

  const sized = fill ?? (bankroll == null ? opt : null)
  const sizedAnn = sized ? annualize(sized.total_profit, sized.capital, days) : null

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline gap-3">
        <span className="label">Lock</span>
        <span className="text-[12px] text-text">{dirText(lock.direction)}</span>
        {lock.fee_assumed_worst_case && (
          <span className="label text-gold" title="Polymarket fee category unknown; worst published rate assumed">
            worst-case fee
          </span>
        )}
        {!lock.criteria_verified && <span className="label text-gold">unverified</span>}
      </div>

      {losing && (
        <p className="text-[12px] leading-relaxed text-text">
          Not a lock at the current asks. The first contract is{' '}
          <span className="num text-gold">
            {(breakEven ?? Math.abs(parseFloat(first.per_contract_edge) * 100)).toFixed(2)}¢
          </span>{' '}
          short of breaking even after fees; the gap between the two asks has to close by that
          much before a lock exists. The books would absorb{' '}
          <span className="num">{depthText}</span> contracts at these prices.
        </p>
      )}

      {sized ? (
        <div className="flex flex-wrap gap-x-10 gap-y-3 items-end">
          <Stat
            label={fill ? `Your size at ${money(bankroll, 0)}` : 'Optimal size'}
            value={<>{qty(sized.size)} <span className="text-[12px] text-muted">contracts</span></>}
            sub={legs(sized)}
            size="lg"
          />
          <Stat
            label={parseFloat(sized.total_profit) >= 0 ? 'Locked at settlement' : 'Lost at settlement'}
            value={
              <span className={parseFloat(sized.total_profit) >= 0 ? 'text-gold' : 'text-down'}>
                {signedMoney(sized.total_profit)}
              </span>
            }
            sub={`${signedCents(sized.per_contract_edge)}¢ / contract`}
            size="lg"
          />
          <Stat
            label="Capital"
            value={money(sized.capital)}
            sub={fill ? bindingText(fill.binding) : 'both legs and fees'}
          />
          <Stat
            label="Annualized"
            value={sizedAnn == null ? '—' : `${(sizedAnn * 100).toFixed(1)}%`}
            sub={daysText}
          />
        </div>
      ) : bankroll != null ? (
        <p className="text-[12px] text-muted">
          {money(bankroll, 0)} does not cover one contract here; the first costs about{' '}
          <span className="num text-text">{money(parseFloat(first.capital) / parseFloat(first.size))}</span>.
        </p>
      ) : (
        <p className="text-[12px] text-muted">
          Enter a bankroll in the top bar to size this lock for your capital.
        </p>
      )}

      <div className="border border-line rounded-sm">
        <div className="flex items-center border-b border-line px-2.5 h-7">
          <span className="label">Edge per contract vs size</span>
          <span className="ml-auto num text-[10px] text-muted">
            {hover
              ? `${qty(hover.size)} → ${signedCents(hover.per_contract_edge)}¢ · ${signedMoney(hover.total_profit)} · ${money(hover.capital)}`
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
            <line x1="0" x2={W} y1={y(0)} y2={y(0)} stroke="var(--color-line)" strokeWidth="1" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
            <path d={line} fill="none" stroke="var(--color-primary)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
            {opt && (
              <line x1={x(parseFloat(opt.size))} x2={x(parseFloat(opt.size))} y1="0" y2={H} stroke="var(--color-gold)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            )}
            {fill && (
              <line x1={x(parseFloat(fill.size))} x2={x(parseFloat(fill.size))} y1="0" y2={H} stroke="var(--color-hover)" strokeWidth="1" strokeDasharray="2 2" vectorEffect="non-scaling-stroke" />
            )}
            {hover && (
              <line x1={x(parseFloat(hover.size))} x2={x(parseFloat(hover.size))} y1="0" y2={H} stroke="var(--color-muted)" strokeWidth="1" opacity="0.6" vectorEffect="non-scaling-stroke" />
            )}
          </svg>
          <div className="flex justify-between num text-[10px] text-muted leading-4">
            <span>0</span>
            <span>
              {opt && <span className="text-gold">optimal {qty(opt.size)}</span>}
              {opt && fill && ' · '}
              {fill && <span className="text-hover">yours {qty(fill.size)}</span>}
            </span>
            <span>{qty(String(maxSize))}</span>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-x-8 gap-y-3">
        <Stat label="Optimal size" value={opt ? qty(opt.size) : '—'} sub={opt ? `${money(opt.capital)} capital` : 'no profitable size'} size="sm" />
        <Stat
          label="Max locked"
          value={opt ? <span className="text-gold">{signedMoney(opt.total_profit)}</span> : '—'}
          sub={opt ? `${signedCents(opt.per_contract_edge)}¢ / contract` : undefined}
          size="sm"
        />
        <Stat label="Depth" value={depthText} sub="contracts both books fill" size="sm" />
        <Stat
          label="Legging cost"
          value={item?.legging_cost_per_contract != null ? `${cents(item.legging_cost_per_contract, 2)}¢` : '—'}
          sub="worst case, one leg missed"
          size="sm"
        />
        <Stat
          label="Annualized at optimal"
          value={lock.annualized_return != null ? `${(parseFloat(lock.annualized_return) * 100).toFixed(1)}%` : '—'}
          sub={daysText}
          size="sm"
        />
      </div>

      <details>
        <summary className="label cursor-pointer hover:text-hover">Assumptions ({lock.assumptions.length})</summary>
        <ul className="text-muted text-[11px] mt-1 space-y-0.5 list-disc list-inside">
          {lock.assumptions.map((a) => (
            <li key={a} className={a.startsWith('UNVERIFIED') ? 'text-gold' : undefined}>{a}</li>
          ))}
        </ul>
      </details>
    </div>
  )
}
