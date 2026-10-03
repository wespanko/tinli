import type { ReactNode } from 'react'

export default function Panel({
  title,
  extra,
  children,
  className = '',
}: {
  title?: ReactNode
  extra?: ReactNode
  children?: ReactNode
  className?: string
}) {
  return (
    <section className={`panel flex-1 ${className}`}>
      {(title || extra) && (
        <header className="section-head">
          {title && <span className="label">{title}</span>}
          {extra && <span className="ml-auto text-[11px] text-muted">{extra}</span>}
        </header>
      )}
      <div className="flex-1 overflow-y-auto min-h-0">{children}</div>
    </section>
  )
}
