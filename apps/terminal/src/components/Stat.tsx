import type { ReactNode } from 'react'

/** Caption over a number, no box. A row of these is the summary strip a
    panel opens with. */
export default function Stat({
  label,
  value,
  sub,
  big = false,
  className = '',
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  big?: boolean
  className?: string
}) {
  return (
    <div className={`min-w-0 ${className}`}>
      <div className="label">{label}</div>
      <div className={`font-mono text-text ${big ? 'text-[22px] leading-7' : 'text-[15px] leading-6'}`}>
        {value}
      </div>
      {sub && <div className="font-mono text-[10px] text-muted leading-4">{sub}</div>}
    </div>
  )
}
