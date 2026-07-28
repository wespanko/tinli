/** First-load placeholder rows: the layout appears at full size immediately
 * and quotes land into it, instead of panels popping in one by one. */
export default function Skeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="p-3 flex flex-col gap-2" aria-hidden>
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="h-4 rounded-sm bg-panel-2 animate-pulse"
          style={{ width: `${88 - (i % 3) * 14}%`, animationDelay: `${i * 90}ms` }}
        />
      ))}
    </div>
  )
}
