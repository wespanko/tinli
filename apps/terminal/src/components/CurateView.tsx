import { Fragment, useState } from 'react'
import type { Candidate, CandidatesResponse, Pair, PairMutationResponse } from '../types'

const FEE_CATEGORIES = [
  '', 'crypto', 'sports', 'finance', 'politics', 'mentions', 'tech',
  'economics', 'culture', 'weather', 'geopolitical', 'other',
]

async function mutate(
  url: string,
  method: string,
  body?: unknown,
): Promise<{ ok: true; data: PairMutationResponse } | { ok: false; error: string }> {
  try {
    const r = await fetch(url, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
    const data = await r.json().catch(() => null)
    if (!r.ok) {
      const detail = data?.detail
      return {
        ok: false,
        error: typeof detail === 'string' ? detail : JSON.stringify(detail ?? r.status),
      }
    }
    return { ok: true, data: data as PairMutationResponse }
  } catch {
    return { ok: false, error: 'network error, nothing changed' }
  }
}

/** The notes requirement is the audit trail: the server enforces 20+
    characters, mirrored here so the error is friendlier. */
function VerifyBox({
  pair,
  onDone,
  onError,
}: {
  pair: Pair
  onDone: (r: PairMutationResponse) => void
  onError: (e: string) => void
}) {
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const short = notes.trim().length < 20
  return (
    <div className="flex flex-col gap-1.5 bg-panel-2 border border-line rounded-sm p-2 my-1">
      <div className="text-[11px] text-muted leading-snug">
        What you compared across both rulebooks, and any differences in the tails. Saved with the pair.
      </div>
      <textarea
        className="field w-full h-16 resize-none font-sans"
        placeholder="e.g. both settle on the official result; Polymarket spells out tie-breakers, Kalshi is silent, tie risk accepted because…"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      <div className="flex gap-2 items-center">
        <button
          className="btn-gold"
          disabled={busy || short}
          onClick={async () => {
            setBusy(true)
            const r = await mutate(
              `/v1/curate/pairs/${encodeURIComponent(pair.event_key)}/verify`,
              'POST',
              { verified: true, notes },
            )
            setBusy(false)
            r.ok ? onDone(r.data) : onError(r.error)
          }}
        >
          Mark verified
        </button>
        {short && <span className="text-muted text-[10px]">20 characters minimum</span>}
      </div>
    </div>
  )
}

function CandidateCard({
  c,
  readonly,
  onDone,
  onError,
}: {
  c: Candidate
  readonly: boolean
  onDone: (r: PairMutationResponse) => void
  onError: (e: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [eventKey, setEventKey] = useState(c.suggested_event_key)
  const [yesToken, setYesToken] = useState<number | null>(c.pm_yes_token_guess)
  const [fee, setFee] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <div className="border border-line rounded-sm p-2 flex flex-col gap-1">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-gold text-[12px]">{c.score.toFixed(2)}</span>
        <span className="font-sans text-text text-[13px]">{c.kalshi_title}</span>
        <button className="btn ml-auto" onClick={() => setOpen(!open)}>
          {open ? 'Collapse' : 'Compare rules'}
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <div>
          <a className="text-hover underline" href={c.kalshi_url} target="_blank" rel="noreferrer">
            Kalshi <span className="font-mono">{c.kalshi_ticker}</span>
          </a>
          <span className="text-muted font-mono ml-2">
            vol {Math.round(c.kalshi_vol_24h).toLocaleString('en-US')}
          </span>
          <span className="text-muted ml-2">closes {c.kalshi_close?.slice(0, 10) ?? '—'}</span>
        </div>
        <div>
          <a className="text-hover underline" href={c.pm_url} target="_blank" rel="noreferrer">
            Polymarket
          </a>
          <span className="font-sans text-muted ml-2">{c.pm_question}</span>
        </div>
      </div>
      {open && (
        <div className="grid grid-cols-2 gap-2 text-[11px] leading-snug bg-panel-2 border border-line rounded-sm p-2">
          <div>
            <div className="label mb-1">Kalshi rules</div>
            <div className="font-sans text-text whitespace-pre-wrap">{c.kalshi_rules || '—'}</div>
          </div>
          <div>
            <div className="label mb-1">
              Polymarket description · outcomes {JSON.stringify(c.pm_outcomes)}
            </div>
            <div className="font-sans text-text whitespace-pre-wrap">
              {c.pm_description || '—'}
            </div>
          </div>
        </div>
      )}
      {!readonly && (
        <div className="flex gap-1.5 items-center flex-wrap">
          <input
            className="field w-52"
            value={eventKey}
            onChange={(e) => setEventKey(e.target.value)}
            title="stable id for this pair"
          />
          <select
            className="field"
            value={yesToken === null ? '' : String(yesToken)}
            onChange={(e) => setYesToken(e.target.value === '' ? null : Number(e.target.value))}
            title="which Polymarket outcome corresponds to Kalshi YES"
          >
            <option value="">YES token?</option>
            {c.pm_outcomes.map((o, i) => (
              <option key={i} value={i}>
                YES = {o}
              </option>
            ))}
          </select>
          <select
            className="field"
            value={fee}
            onChange={(e) => setFee(e.target.value)}
            title="Polymarket taker-fee category from their published schedule"
          >
            {FEE_CATEGORIES.map((f) => (
              <option key={f} value={f}>
                {f === '' ? 'fee category (worst case if unset)' : f}
              </option>
            ))}
          </select>
          <button
            className="btn-gold"
            disabled={busy || yesToken === null || !eventKey.trim()}
            onClick={async () => {
              setBusy(true)
              const r = await mutate('/v1/curate/pairs', 'POST', {
                event_key: eventKey.trim(),
                question: c.kalshi_title,
                kalshi_ticker: c.kalshi_ticker,
                pm_condition_id: c.pm_condition_id,
                pm_yes_token: yesToken,
                pm_fee_category: fee || null,
              })
              setBusy(false)
              r.ok ? onDone(r.data) : onError(r.error)
            }}
          >
            Add as unverified
          </button>
        </div>
      )}
    </div>
  )
}

export default function CurateView({
  pairs,
  readonly,
  onPairsChanged,
}: {
  pairs: Pair[]
  readonly: boolean
  onPairsChanged: (pairs: Pair[]) => void
}) {
  const [verifying, setVerifying] = useState<string | null>(null)
  const [retiring, setRetiring] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [candidates, setCandidates] = useState<Candidate[] | null>(null)
  const [cacheAge, setCacheAge] = useState<number | null>(null)
  const [scanning, setScanning] = useState(false)

  const applied = (r: PairMutationResponse) => {
    onPairsChanged(r.pairs)
    setVerifying(null)
    setRetiring(null)
    setError(null)
  }

  const scan = async (refresh: boolean) => {
    setScanning(true)
    setError(null)
    try {
      const r = await fetch(`/v1/curate/candidates${refresh ? '?refresh=true' : ''}`)
      if (!r.ok) {
        const body = await r.json().catch(() => null)
        setError(body?.detail ?? `HTTP ${r.status}`)
      } else {
        const body = (await r.json()) as CandidatesResponse
        setCandidates(body.candidates)
        setCacheAge(body.cache_age_s)
      }
    } catch {
      setError('network error during scan')
    } finally {
      setScanning(false)
    }
  }

  const settledish = (p: Pair) =>
    p.kalshi?.status !== 'open' || p.polymarket?.status !== 'open'
  const verifiedCount = pairs.filter((p) => p.criteria_verified).length

  return (
    <main className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-1">
      <section className="border border-line bg-panel rounded-sm p-3">
        <div className="flex items-baseline gap-3 mb-2">
          <span className="label">Map</span>
          <span className="text-[11px] text-muted">
            {pairs.length} pairs · {verifiedCount} verified
          </span>
        </div>
        {error && (
          <div className="border border-gold text-gold text-[11px] rounded-sm px-2 py-1.5 mb-2">
            {error}
          </div>
        )}
        <table className="w-full font-mono">
          <thead>
            <tr className="border-b border-line">
              <th className="th text-left">Pair</th>
              <th className="th text-left px-1">Status</th>
              <th className="th text-left px-1">Rules</th>
              {!readonly && <th className="th text-right"></th>}
            </tr>
          </thead>
          <tbody>
            {pairs.map((p) => (
              <Fragment key={p.event_key}>
                <tr className="border-b border-line/30">
                  <td className="font-sans py-1.5 pr-2 text-text">
                    {p.question}
                    <span className="text-muted font-mono text-[10px] ml-2">{p.event_key}</span>
                  </td>
                  <td className="px-1 text-[11px] whitespace-nowrap">
                    {settledish(p) ? (
                      <span className="text-gold">settled</span>
                    ) : (
                      <span className="text-up">open</span>
                    )}
                    <span className={`ml-2 ${p.criteria_verified ? 'text-muted' : 'text-gold'}`}>
                      {p.criteria_verified ? 'verified' : 'unverified'}
                    </span>
                  </td>
                  <td className="px-1 text-[11px] whitespace-nowrap">
                    {p.kalshi && (
                      <a className="text-hover underline mr-2" href={p.kalshi.resolution_url} target="_blank" rel="noreferrer">
                        K
                      </a>
                    )}
                    {p.polymarket && (
                      <a className="text-hover underline" href={p.polymarket.resolution_url} target="_blank" rel="noreferrer">
                        PM
                      </a>
                    )}
                  </td>
                  {!readonly && (
                    <td className="text-right py-1 whitespace-nowrap">
                      {p.criteria_verified ? (
                        <button
                          className="btn"
                          onClick={async () => {
                            const r = await mutate(
                              `/v1/curate/pairs/${encodeURIComponent(p.event_key)}/verify`,
                              'POST',
                              { verified: false, notes: '' },
                            )
                            r.ok ? applied(r.data) : setError(r.error)
                          }}
                        >
                          Unverify
                        </button>
                      ) : (
                        <button
                          className={`btn ${verifying === p.event_key ? 'border-gold text-gold' : ''}`}
                          onClick={() => setVerifying(verifying === p.event_key ? null : p.event_key)}
                        >
                          Verify
                        </button>
                      )}
                      <button
                        className={`btn ml-1 ${retiring === p.event_key ? 'border-down text-down' : ''}`}
                        onClick={async () => {
                          if (retiring !== p.event_key) {
                            setRetiring(p.event_key)
                            return
                          }
                          const r = await mutate(
                            `/v1/curate/pairs/${encodeURIComponent(p.event_key)}`,
                            'DELETE',
                          )
                          r.ok ? applied(r.data) : setError(r.error)
                        }}
                      >
                        {retiring === p.event_key ? 'Confirm retire' : 'Retire'}
                      </button>
                    </td>
                  )}
                </tr>
                {verifying === p.event_key && (
                  <tr>
                    <td colSpan={4}>
                      <VerifyBox pair={p} onDone={applied} onError={setError} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </section>

      <section className="border border-line bg-panel rounded-sm p-3">
        <div className="flex items-center gap-3 mb-2">
          <span className="label">Candidates</span>
          <span className="text-[11px] text-muted">
            unmapped markets that look like the same event on both venues
          </span>
          <button className="btn ml-auto" disabled={scanning} onClick={() => scan(candidates !== null)}>
            {scanning ? 'Scanning…' : candidates === null ? 'Scan venues' : 'Rescan'}
          </button>
        </div>
        {scanning && (
          <div className="text-muted text-[11px]">
            scanning both venues' top markets, 30–60s on a cold cache
          </div>
        )}
        {!scanning && candidates !== null && (
          <>
            {cacheAge !== null && cacheAge > 1 && (
              <div className="text-muted text-[10px] mb-1.5">
                cached scan from {Math.round(cacheAge)}s ago
              </div>
            )}
            {candidates.length === 0 ? (
              <div className="text-muted text-[11px]">
                no unmapped candidates above the match threshold right now
              </div>
            ) : (
              <div className="flex flex-col gap-1.5">
                {candidates.map((c) => (
                  <CandidateCard
                    key={c.kalshi_ticker}
                    c={c}
                    readonly={readonly}
                    onDone={(r) => {
                      applied(r)
                      // an added candidate leaves the pool immediately
                      setCandidates(
                        (cs) => cs?.filter((x) => x.kalshi_ticker !== c.kalshi_ticker) ?? null,
                      )
                    }}
                    onError={setError}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </main>
  )
}
