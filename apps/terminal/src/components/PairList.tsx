import type { Groups, Row } from '../pairs'
import { basisCents, kalshiMid } from '../pairs'
import { cents, pct, qty } from '../format'
import Signed from './Signed'

/** The one pair list: each row is a pair joined with its fee-adjusted lock
    edge. Verified pairs on top; unverified and settled pairs sit under
    collapsible dividers so the default screen shows only what can be
    traded. */

function dirLabel(r: Row): string {
  const d = r.item?.direction
  if (!d) return 'no executable lock'
  return d === 'buy_yes_kalshi_no_polymarket'
    ? 'buy YES on Kalshi, NO on Polymarket'
    : 'buy YES on Polymarket, NO on Kalshi'
}

function Divider({
  label,
  hint,
  open,
  onToggle,
}: {
  label: string
  hint?: string
  open: boolean
  onToggle: () => void
}) {
  return (
    <tr className="bg-panel-2/60 border-b border-line/30">
      <td colSpan={5} className="px-3 py-1">
        <button onClick={onToggle} className="w-full flex items-center gap-2 label hover:text-hover">
          <span className="w-3 text-left font-mono">{open ? '−' : '+'}</span>
          <span>{label}</span>
          {hint && <span className="normal-case tracking-normal text-muted/80 truncate">{hint}</span>}
        </button>
      </td>
    </tr>
  )
}

function PairRow({
  row,
  active,
  muted,
  onSelect,
}: {
  row: Row
  active: boolean
  muted: boolean
  onSelect: (eventKey: string) => void
}) {
  const { pair: p, item } = row
  const basis = basisCents(p)
  const kMid = kalshiMid(p)
  const k = kMid == null ? null : kMid * 100 // dollars → cents, like PM below
  const pm = p.polymarket ? parseFloat(p.polymarket.yes_price) * 100 : null
  const edge = item?.edge_at_size == null ? null : parseFloat(item.edge_at_size)
  const executable = p.criteria_verified && edge != null && edge > 0
  const xs = item?.annualized_excess_return
  return (
    <tr
      onClick={() => onSelect(p.event_key)}
      className={`cursor-pointer border-b border-line/30 border-l-2 ${
        active ? 'border-l-primary bg-primary/10' : 'border-l-transparent hover:bg-line/20'
      }`}
      title={`${dirLabel(row)}${
        xs != null && executable ? ` · ${pct(xs)} excess/yr to later close` : ''
      }`}
    >
      <td
        className={`font-sans pl-3 pr-1 py-1.5 whitespace-nowrap overflow-hidden text-ellipsis max-w-56 ${
          active ? 'text-hover' : muted ? 'text-muted' : 'text-text'
        }`}
      >
        {p.question}
      </td>
      <td className="text-right px-1 tabular-nums text-muted text-[12px] whitespace-nowrap">
        {k == null ? '—' : k.toFixed(1)}
        <span className="mx-1 text-muted/60">·</span>
        {pm == null ? '—' : pm.toFixed(1)}
      </td>
      <td className="text-right px-1">
        {/* a gap of a cent or more is a key number: gold overrides the sign color */}
        {basis != null && Math.abs(basis) >= 1 ? (
          <span className="tabular-nums text-gold">{`${basis > 0 ? '+' : ''}${basis.toFixed(1)}`}</span>
        ) : (
          <Signed
            value={basis}
            text={basis == null ? '—' : `${basis > 0 ? '+' : ''}${basis.toFixed(1)}`}
          />
        )}
      </td>
      <td className={`text-right px-1 tabular-nums ${executable ? 'text-gold' : 'text-muted'}`}>
        {edge == null ? '—' : cents(item?.edge_at_size, 2)}
        {item?.fee_assumed_worst_case && (
          <span className="text-gold" title="Polymarket fee category unknown; worst-case rate assumed">
            *
          </span>
        )}
      </td>
      <td className="text-right px-3 tabular-nums text-muted">{qty(item?.max_lock_size)}</td>
    </tr>
  )
}

export default function PairList({
  groups,
  selected,
  onToggle,
  onSelect,
}: {
  groups: Groups
  selected: string | null
  onToggle: (group: 'unverified' | 'settled') => void
  onSelect: (eventKey: string) => void
}) {
  const { verified, unverified, settled, visible } = groups
  // `visible` already accounts for the toggles AND the filter override
  const unverifiedShown = unverified.length > 0 && visible.includes(unverified[0])
  const settledShown = settled.length > 0 && visible.includes(settled[0])
  const rows = (list: Row[], muted: boolean) =>
    list.map((r) => (
      <PairRow
        key={r.pair.event_key}
        row={r}
        active={r.pair.event_key === selected}
        muted={muted}
        onSelect={onSelect}
      />
    ))
  return (
    <table className="w-full font-mono text-[13px]">
      <thead>
        <tr className="sticky top-0 bg-panel border-b border-line z-10">
          <th className="th text-left pl-3">Pair</th>
          <th className="th text-right px-1" title="Kalshi mid · Polymarket yes, cents">
            K · PM
          </th>
          <th className="th text-right px-1" title="Kalshi mid minus Polymarket mid, cents">
            Δ¢
          </th>
          <th className="th text-right px-1" title="lock edge per contract after fees, at executable size">
            Edge¢
          </th>
          <th className="th text-right px-3" title="max lock size, contracts">
            Size
          </th>
        </tr>
      </thead>
      <tbody>
        {verified.length === 0 && (
          <tr>
            <td colSpan={5} className="px-3 py-3 text-[12px] text-muted font-sans">
              No verified pairs yet. Compare resolution rules in Curate to promote one.
            </td>
          </tr>
        )}
        {rows(verified, false)}
        {unverified.length > 0 && (
          <Divider
            label={`Unverified · ${unverified.length}`}
            hint="resolution rules not yet compared"
            open={unverifiedShown}
            onToggle={() => onToggle('unverified')}
          />
        )}
        {unverifiedShown && rows(unverified, true)}
        {settled.length > 0 && (
          <Divider
            label={`Settled · ${settled.length}`}
            open={settledShown}
            onToggle={() => onToggle('settled')}
          />
        )}
        {settledShown && rows(settled, true)}
      </tbody>
    </table>
  )
}
