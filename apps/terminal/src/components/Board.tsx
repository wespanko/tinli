import type { Groups, Row } from '../pairs'
import { positiveEdge } from '../pairs'
import type { DivergenceItem, LockReport } from '../types'
import { cents, money, pct, qty, signedCents, signedMoney } from '../format'
import { annualize } from './LockSizing'
import Signed from './Signed'
import Stat from './Stat'

/** The first screen: live edges on top, sized for the reader's bankroll,
    and one dense grid of every pair underneath. Clicking anything opens
    the market page. */

function EdgeCard({
  item,
  lock,
  bankroll,
  onOpen,
}: {
  item: DivergenceItem
  lock: LockReport | undefined
  bankroll: number | null
  onOpen: () => void
}) {
  const fill = bankroll != null ? lock?.for_bankroll : lock?.optimal
  const ann = fill ? annualize(fill.total_profit, fill.capital, lock?.days_to_resolution ?? null) : null
  const days = lock?.days_to_resolution
  return (
    <button onClick={onOpen} className="bg-panel hover:bg-panel-2 text-left p-3 flex flex-col gap-3 min-w-[22rem] max-w-[30rem] flex-1">
      <div className="text-[13px] text-text leading-snug truncate w-full">{item.question}</div>
      <div className="flex items-end gap-6">
        <Stat
          label="Edge / contract"
          value={<span className="text-gold">{signedCents(item.edge_at_size)}¢</span>}
          size="lg"
        />
        {fill ? (
          <>
            <Stat
              label={bankroll != null ? 'Your size' : 'Optimal'}
              value={qty(fill.size)}
              sub={`${money(fill.capital)} capital`}
            />
            <Stat
              label="Locks"
              value={<span className="text-gold">{signedMoney(fill.total_profit)}</span>}
              sub={
                ann != null && days != null
                  ? `${(ann * 100).toFixed(1)}% / yr · ${parseFloat(days).toFixed(0)}d`
                  : days != null
                    ? `${parseFloat(days).toFixed(0)}d to close`
                    : undefined
              }
            />
          </>
        ) : lock && bankroll != null ? (
          <Stat label="Your size" value="—" sub="bankroll below one contract" />
        ) : (
          <Stat label="Size" value={qty(item.max_lock_size)} sub="top of book" />
        )}
      </div>
    </button>
  )
}

function Divider({
  label,
  hint,
  open,
  onToggle,
  cols,
}: {
  label: string
  hint?: string
  open: boolean
  onToggle: () => void
  cols: number
}) {
  return (
    <tr className="bg-panel-2/50">
      <td colSpan={cols} className="px-3 py-1">
        <button onClick={onToggle} className="w-full flex items-center gap-2 label hover:text-hover">
          <span className="w-3 text-left num">{open ? '−' : '+'}</span>
          <span>{label}</span>
          {hint && <span className="normal-case tracking-normal text-dim truncate">{hint}</span>}
        </button>
      </td>
    </tr>
  )
}

const COLS = 9

function top(v: string | null): string {
  return v == null ? '—' : cents(v)
}

function GridRow({
  row,
  active,
  muted,
  onOpen,
}: {
  row: Row
  active: boolean
  muted: boolean
  onOpen: () => void
}) {
  const { pair: p, item } = row
  const executable = p.criteria_verified && positiveEdge(item?.edge_at_size)
  const basis = item?.raw_basis_cents != null ? parseFloat(item.raw_basis_cents) : null
  const xs = item?.annualized_excess_return
  return (
    <tr
      onClick={onOpen}
      className={`cursor-pointer border-b border-line/40 border-l-2 h-7 ${
        active ? 'border-l-primary bg-primary/10' : 'border-l-transparent hover:bg-panel-2'
      }`}
    >
      <td className={`font-sans pl-3 pr-2 whitespace-nowrap overflow-hidden text-ellipsis max-w-72 ${muted ? 'text-muted' : 'text-text'}`}>
        {p.question}
      </td>
      <td className="num text-right px-2 text-muted whitespace-nowrap">
        <span className={item?.kalshi.bid ? 'text-up' : ''}>{top(item?.kalshi.bid ?? null)}</span>
        <span className="mx-1 text-dim">·</span>
        <span className={item?.kalshi.ask ? 'text-down' : ''}>{top(item?.kalshi.ask ?? null)}</span>
      </td>
      <td className="num text-right px-2 text-muted whitespace-nowrap">
        <span className={item?.polymarket.bid ? 'text-up' : ''}>{top(item?.polymarket.bid ?? null)}</span>
        <span className="mx-1 text-dim">·</span>
        <span className={item?.polymarket.ask ? 'text-down' : ''}>{top(item?.polymarket.ask ?? null)}</span>
      </td>
      <td className="num text-right px-2">
        {basis != null && Math.abs(basis) >= 1 ? (
          <span className="text-gold">{`${basis > 0 ? '+' : ''}${basis.toFixed(1)}`}</span>
        ) : (
          <Signed value={basis} text={basis == null ? '—' : `${basis > 0 ? '+' : ''}${basis.toFixed(1)}`} />
        )}
      </td>
      <td className="num text-right px-2">
        <Signed value={item?.fee_adjusted_edge} text={signedCents(item?.fee_adjusted_edge)} />
      </td>
      <td className={`num text-right px-2 ${executable ? 'text-gold' : 'text-muted'}`}>
        {signedCents(item?.edge_at_size)}
        {item?.fee_assumed_worst_case && (
          <span className="text-gold" title="Polymarket fee category unknown; worst-case rate assumed">*</span>
        )}
      </td>
      <td className="num text-right px-2 text-muted">{qty(item?.max_lock_size)}</td>
      <td className="num text-right px-2 text-muted">
        {item?.horizon_days != null ? parseFloat(item.horizon_days).toFixed(0) : '—'}
      </td>
      <td className={`num text-right pr-3 pl-2 ${executable ? 'text-text' : 'text-dim'}`}>
        {xs != null && executable ? pct(xs) : '—'}
      </td>
    </tr>
  )
}

export default function Board({
  groups,
  edges,
  locks,
  bankroll,
  selected,
  filter,
  onOpen,
  onToggle,
}: {
  groups: Groups
  edges: DivergenceItem[]
  locks: Record<string, LockReport>
  bankroll: number | null
  selected: string | null
  filter: string
  onOpen: (eventKey: string) => void
  onToggle: (group: 'unverified' | 'settled') => void
}) {
  const { verified, unverified, settled, visible } = groups
  const unverifiedShown = unverified.length > 0 && visible.includes(unverified[0])
  const settledShown = settled.length > 0 && visible.includes(settled[0])
  const rows = (list: Row[], muted: boolean) =>
    list.map((r) => (
      <GridRow
        key={r.pair.event_key}
        row={r}
        active={r.pair.event_key === selected}
        muted={muted}
        onOpen={() => onOpen(r.pair.event_key)}
      />
    ))

  return (
    <main className="flex-1 flex flex-col gap-px min-h-0">
      {edges.length > 0 ? (
        <section className="panel shrink-0">
          <header className="section-head">
            <span className="label text-gold">Live edges</span>
            <span className="text-[11px] text-muted">
              after both venues' fees, at executable size
              {bankroll != null ? ` · sized for ${money(bankroll, 0)}` : ' · enter a bankroll to size them'}
            </span>
          </header>
          <div className="flex flex-wrap gap-px bg-line">
            {edges.map((e) => (
              <EdgeCard
                key={e.event_key}
                item={e}
                lock={locks[e.event_key]}
                bankroll={bankroll}
                onOpen={() => onOpen(e.event_key)}
              />
            ))}
          </div>
        </section>
      ) : (
        <div className="panel shrink-0 h-9 px-3 flex items-center gap-3">
          <span className="label">Live edges</span>
          <span className="text-[11px] text-muted">
            none after fees right now · watching {verified.length} verified pairs
          </span>
        </div>
      )}

      <section className="panel flex-1">
        <header className="section-head">
          <span className="label">Pairs</span>
          <span className="text-[11px] text-muted">
            {filter ? `${visible.length} match` : `${verified.length} verified · ${unverified.length} unverified · ${settled.length} settled`}
          </span>
          <span className="ml-auto text-[10px] text-dim">click a row to open · j k move · enter opens</span>
        </header>
        <div className="flex-1 overflow-y-auto min-h-0">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="sticky top-0 bg-panel border-b border-line z-10">
                <th className="th text-left pl-3">Pair</th>
                <th className="th text-right px-2" title="Kalshi YES bid · ask, cents">Kalshi</th>
                <th className="th text-right px-2" title="Polymarket YES bid · ask, cents">Polymarket</th>
                <th className="th text-right px-2" title="Kalshi mid minus Polymarket mid, cents">Δ¢</th>
                <th className="th text-right px-2" title="lock edge per contract at top of book, after fees">Edge¢</th>
                <th className="th text-right px-2" title="edge per contract at the full top-of-book size, exact fee rounding">@ size</th>
                <th className="th text-right px-2" title="contracts both tops of book fill">Size</th>
                <th className="th text-right px-2" title="days to the later venue close">Days</th>
                <th className="th text-right pr-3 pl-2" title="annualized return over the risk-free rate, executable locks only">Excess / yr</th>
              </tr>
            </thead>
            <tbody>
              {verified.length === 0 && (
                <tr>
                  <td colSpan={COLS} className="px-3 py-3 text-[12px] text-muted font-sans">
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
                  cols={COLS}
                />
              )}
              {unverifiedShown && rows(unverified, true)}
              {settled.length > 0 && (
                <Divider
                  label={`Settled · ${settled.length}`}
                  open={settledShown}
                  onToggle={() => onToggle('settled')}
                  cols={COLS}
                />
              )}
              {settledShown && rows(settled, true)}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  )
}
