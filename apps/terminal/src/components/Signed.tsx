/** A signed value colored by direction: up green, down red, zero/absent muted.
    Direction color rides the NUMBER only — labels stay in text tokens. */
export default function Signed({
  value,
  text,
  className = '',
}: {
  value: number | string | null | undefined
  text: string
  className?: string
}) {
  const n = value == null ? null : typeof value === 'number' ? value : parseFloat(value)
  const tone =
    n == null || n === 0 || Number.isNaN(n) ? 'text-muted' : n > 0 ? 'text-up' : 'text-down'
  return <span className={`tabular-nums ${tone} ${className}`}>{text}</span>
}
