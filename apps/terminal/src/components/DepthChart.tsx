import { useState } from 'react'
import type { Orderbook } from '../types'
import { qty } from '../format'

/** Cumulative depth curve for one venue's YES book: bid depth (up hue)
    stepping down-left from the touch, ask depth (down hue) up-right.
    Area wash ~12% + 2px line per the mark specs; SVG carries shapes only,
    text lives in HTML so nothing distorts. Hover shows price/cum-size. */

const W = 400
const H = 96
const PAD_X = 0.01 // 1¢ of horizontal breathing room
const WINDOW = 0.15 // show ±15¢ around mid — books carry dust at 1¢/99¢ that would squash the touch

type Pt = { price: number; cum: number }

function cumulate(levels: { price: string; size: string }[]): Pt[] {
  // levels arrive best-first; accumulate outward from the touch
  let cum = 0
  return levels.map((l) => {
    cum += parseFloat(l.size)
    return { price: parseFloat(l.price), cum }
  })
}

function stepPath(pts: { x: number; y: number }[], baseY: number, close: boolean): string {
  if (!pts.length) return ''
  let d = `M ${pts[0].x} ${baseY} L ${pts[0].x} ${pts[0].y}`
  for (let i = 1; i < pts.length; i++) {
    d += ` H ${pts[i].x} V ${pts[i].y}` // vertical-then-horizontal steps
  }
  if (close) d += ` L ${pts[pts.length - 1].x} ${baseY} Z`
  return d
}

export default function DepthChart({ label, book }: { label: string; book: Orderbook | null }) {
  const [hover, setHover] = useState<{ x: number; side: 'bid' | 'ask'; pt: Pt } | null>(null)

  if (!book || (!book.bids.length && !book.asks.length)) {
    return (
      <div className="flex-1 min-w-0 border border-line rounded-sm p-2.5 text-muted text-[11px]">
        no depth
      </div>
    )
  }

  const bestBidP = book.bids[0] ? parseFloat(book.bids[0].price) : null
  const bestAskP = book.asks[0] ? parseFloat(book.asks[0].price) : null
  const center = bestBidP != null && bestAskP != null ? (bestBidP + bestAskP) / 2 : (bestBidP ?? bestAskP ?? 0.5)
  const bids = cumulate(book.bids.filter((l) => parseFloat(l.price) >= center - WINDOW))
  const asks = cumulate(book.asks.filter((l) => parseFloat(l.price) <= center + WINDOW))
  if (!bids.length && !asks.length) {
    return (
      <div className="flex-1 min-w-0 border border-line rounded-sm p-2.5 text-muted text-[11px]">
        no depth near mid
      </div>
    )
  }
  const lo = Math.min(...bids.map((p) => p.price), ...asks.map((p) => p.price)) - PAD_X
  const hi = Math.max(...bids.map((p) => p.price), ...asks.map((p) => p.price)) + PAD_X
  const maxCum = Math.max(1, bids.at(-1)?.cum ?? 0, asks.at(-1)?.cum ?? 0)
  const x = (price: number) => ((price - lo) / (hi - lo)) * W
  const y = (cum: number) => H - (cum / maxCum) * (H - 6) // 6px headroom
  const toXY = (pts: Pt[]) => pts.map((p) => ({ x: x(p.price), y: y(p.cum) }))

  const bidPts = toXY(bids)
  const askPts = toXY(asks)
  const mid = bestBidP != null && bestAskP != null ? center : null

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const price = lo + ((e.clientX - rect.left) / rect.width) * (hi - lo)
    // one-sided books hover whichever side exists; two-sided split at center
    const wantBid = asks.length === 0 || (bids.length > 0 && price <= center)
    if (wantBid) {
      // deepest bid level at or above this price (bids run best→worst downward)
      const pt = bids.filter((p) => p.price >= price).at(-1)
      setHover(pt ? { x: x(pt.price), side: 'bid', pt } : null)
    } else {
      const pt = asks.filter((p) => p.price <= price).at(-1)
      setHover(pt ? { x: x(pt.price), side: 'ask', pt } : null)
    }
  }

  return (
    <div className="flex-1 min-w-0 border border-line rounded-sm flex flex-col">
      <div className="flex items-center border-b border-line px-2.5 h-7">
        <span className="text-muted text-[10px] tracking-[0.15em]">{label}</span>
        <span className="ml-auto font-mono text-[10px] text-muted">
          {hover
            ? `${(hover.pt.price * 100).toFixed(1)}¢ · ${qty(String(hover.pt.cum))} cum`
            : `±15¢ depth ${qty(String(maxCum))}`}
        </span>
      </div>
      <div className="relative px-2.5 py-1.5">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="w-full h-24 block cursor-crosshair"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          <path d={stepPath(bidPts, H, true)} fill="var(--color-up)" opacity="0.12" />
          <path
            d={stepPath(bidPts, H, false)}
            fill="none"
            stroke="var(--color-up)"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
          <path d={stepPath(askPts, H, true)} fill="var(--color-down)" opacity="0.12" />
          <path
            d={stepPath(askPts, H, false)}
            fill="none"
            stroke="var(--color-down)"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
          {mid != null && (
            <line
              x1={x(mid)}
              x2={x(mid)}
              y1="0"
              y2={H}
              stroke="var(--color-line)"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          )}
          {hover && (
            <line
              x1={hover.x}
              x2={hover.x}
              y1="0"
              y2={H}
              stroke="var(--color-muted)"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
              opacity="0.6"
            />
          )}
        </svg>
        <div className="flex justify-between font-mono text-[10px] text-muted leading-4">
          <span>{(lo * 100).toFixed(0)}¢</span>
          <span>{mid == null ? '' : `mid ${(mid * 100).toFixed(1)}¢`}</span>
          <span>{(hi * 100).toFixed(0)}¢</span>
        </div>
      </div>
    </div>
  )
}
