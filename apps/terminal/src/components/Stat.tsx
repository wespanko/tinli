import type { ReactNode } from 'react'

/** Caption over a number, no box. A row of these is the summary strip a
    panel opens with. */
export default function Stat({
  label,
  value,
  sub,
  size = 'md',
  className = '',
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  const v =
    size === 'lg' ? 'text-[24px] leading-7' : size === 'sm' ? 'text-[13px] leading-5' : 'text-[16px] leading-6'
  return (
    <div className={`min-w-0 ${className}`}>
      <div className="label">{label}</div>
      <div className={`num text-text ${v}`}>{value}</div>
      {sub && <div className="num text-[10px] text-muted leading-4 whitespace-nowrap">{sub}</div>}
    </div>
  )
}
