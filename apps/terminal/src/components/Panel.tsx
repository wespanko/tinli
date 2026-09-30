import type { ReactNode } from 'react'

export default function Panel({
  title,
  extra,
  children,
}: {
  title: string
  extra?: ReactNode
  children?: ReactNode
}) {
  return (
    <section className="flex flex-col border border-line bg-panel rounded-sm min-h-0 flex-1">
      <header className="flex items-center border-b border-line px-3 h-8 shrink-0">
        <span className="label">{title}</span>
        {extra && <span className="ml-auto text-[11px] text-muted">{extra}</span>}
      </header>
      <div className="flex-1 overflow-y-auto min-h-0">{children}</div>
    </section>
  )
}
