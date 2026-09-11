import type { DivergenceItem, Pair } from './types'

/** Pair helpers shared by the terminal list, CARDS, and keyboard nav. */

export function kalshiMid(p: Pair): number | null {
  const m = p.kalshi
  if (!m || m.best_bid == null || m.best_ask == null) return null
  return (parseFloat(m.best_bid) + parseFloat(m.best_ask)) / 2
}

export function basisCents(p: Pair): number | null {
  const mid = kalshiMid(p)
  if (mid == null || !p.polymarket) return null
  return (mid - parseFloat(p.polymarket.yes_price)) * 100
}

export function isSettled(p: Pair): boolean {
  return p.kalshi?.status !== 'open' && p.polymarket?.status !== 'open'
}

export function sortPairs(data: Pair[]): Pair[] {
  return [...data].sort((a, b) => {
    if (a.criteria_verified !== b.criteria_verified) return a.criteria_verified ? -1 : 1
    return Math.abs(basisCents(b) ?? 0) - Math.abs(basisCents(a) ?? 0)
  })
}

export type Row = { pair: Pair; item: DivergenceItem | null }

export type Groups = {
  verified: Row[]
  unverified: Row[]
  settled: Row[]
  /** rows the reader can currently see, in screen order — drives j/k */
  visible: Row[]
}

function edgeOf(r: Row): number | null {
  const e = r.item?.edge_at_size
  return e == null ? null : parseFloat(e)
}

// best executable edge first, then the widest raw gap; pairs with no
// quotable edge sink to the bottom of their group
function byEdge(a: Row, b: Row): number {
  const ea = edgeOf(a)
  const eb = edgeOf(b)
  if (ea != null || eb != null) {
    if (ea == null) return 1
    if (eb == null) return -1
    if (ea !== eb) return eb - ea
  }
  return Math.abs(basisCents(b.pair) ?? 0) - Math.abs(basisCents(a.pair) ?? 0)
}

/** One ranked list instead of a watchlist AND a screener: every pair joined
    with its divergence row, split into verified / unverified / settled so the
    noise groups can collapse. `filter` narrows by display name and, being an
    explicit ask to see matches, overrides the collapse. */
export function groupRows(
  pairs: Pair[],
  divergence: DivergenceItem[],
  filter: string,
  show: { unverified: boolean; settled: boolean },
): Groups {
  const byKey = new Map(divergence.map((d) => [d.event_key, d]))
  const needle = filter.trim().toLowerCase()
  const rows: Row[] = pairs
    .filter((p) => !needle || p.question.toLowerCase().includes(needle))
    .map((p) => ({ pair: p, item: byKey.get(p.event_key) ?? null }))
  const settled = rows.filter((r) => isSettled(r.pair)).sort(byEdge)
  const live = rows.filter((r) => !isSettled(r.pair))
  const verified = live.filter((r) => r.pair.criteria_verified).sort(byEdge)
  const unverified = live.filter((r) => !r.pair.criteria_verified).sort(byEdge)
  const open = needle.length > 0
  const visible = [
    ...verified,
    ...(show.unverified || open ? unverified : []),
    ...(show.settled || open ? settled : []),
  ]
  return { verified, unverified, settled, visible }
}
