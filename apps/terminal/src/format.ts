// Formatting edge: the ONLY place decimal strings become numbers.

export function cents(v: string | null | undefined, dp = 1): string {
  if (v == null) return '—'
  return (parseFloat(v) * 100).toFixed(dp)
}

export function usd(v: string | null | undefined): string {
  if (v == null) return '—'
  const n = parseFloat(v)
  return `${n < 0 ? '-' : ''}$${Math.abs(n).toFixed(2)}`
}

export function signedUsd(v: string | null | undefined): string {
  if (v == null) return '—'
  const n = parseFloat(v)
  return `${n < 0 ? '-' : '+'}$${Math.abs(n).toFixed(2)}`
}

export function pct(v: string | null | undefined, dp = 1): string {
  if (v == null) return '—'
  return `${(parseFloat(v) * 100).toFixed(dp)}%`
}

export function qty(v: string | null | undefined): string {
  if (v == null) return '—'
  return parseFloat(v).toLocaleString('en-US', { maximumFractionDigits: 0 })
}

/** 'kalshi:KXFOO-BAR' -> 'KXFOO-BAR', 'polymarket:0xabcdef...' -> '0xabcd…' */
export function shortId(marketId: string): string {
  const native = marketId.split(':', 2)[1] ?? marketId
  return native.startsWith('0x') ? `${native.slice(0, 6)}…` : native
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('en-US', { hour12: false })
}

/** dollars with thousands separators: '$56,370.68'; dp=0 for a bankroll figure */
export function money(v: string | number | null | undefined, dp = 2): string {
  if (v == null) return '—'
  const n = typeof v === 'number' ? v : parseFloat(v)
  const abs = Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })
  return `${n < 0 ? '-' : ''}$${abs}`
}

export function signedMoney(v: string | number | null | undefined, dp = 2): string {
  if (v == null) return '—'
  const n = typeof v === 'number' ? v : parseFloat(v)
  return `${n < 0 ? '-' : '+'}${money(Math.abs(n), dp)}`
}

/** signed cents from a dollar string: '+0.68' */
export function signedCents(v: string | null | undefined, dp = 2): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n > 0 ? '+' : ''}${n.toFixed(dp)}`
}
