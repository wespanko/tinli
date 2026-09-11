import { useState } from 'react'

/** First-run explainer + HELP overlay. The short form is three paragraphs
    and the keys; the full guide (what every number means and does NOT mean)
    unfolds on request so a first screen is not a wall of text. */

export default function IntroPanel({
  onClose,
  full = false,
}: {
  onClose: () => void
  full?: boolean
}) {
  const [expanded, setExpanded] = useState(full)
  const h = 'text-muted text-[10px] font-sans font-medium tracking-[0.15em] mt-3 mb-1'
  return (
    <div
      className="fixed inset-0 z-50 bg-bg/85 flex items-center justify-center p-6"
      onClick={onClose}
    >
      <div
        className="bg-panel border border-line rounded-sm max-w-xl max-h-[85vh] overflow-y-auto p-5 text-[13px] leading-relaxed"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-gold font-bold tracking-[0.2em] text-[15px]">TINLI</span>
          <span className="text-muted text-[12px]">
            one screen across Kalshi and Polymarket, for quant-minded traders
          </span>
        </div>

        <p className="mt-3">
          The same event often trades on both venues. Buy YES on one and NO on the other and
          you collect $1 at resolution <em>whichever way it goes</em> — a lock.
        </p>
        <p className="mt-2">
          Tinli prices that lock for every mapped pair after each venue's exact fees, at
          executable size. Most edges are negative; fees eat small gaps and the screen shows
          that honestly. A <span className="text-gold">gold EDGE¢</span> is the rare real
          thing.
        </p>
        <p className="mt-2">
          Pairs whose resolution rules have not been compared sit collapsed under{' '}
          <span className="text-muted">UNVERIFIED</span>. A gap there is a trap, not an edge.
        </p>

        <p className="font-mono text-[12px] text-muted mt-3">
          j / k — move · / — filter · 1 2 3 4 — TERMINAL / BOOK / CARDS / CURATE · ? — help ·
          Esc — close
        </p>

        {expanded && (
          <>
            <div className={h}>THE LOCK, PRECISELY</div>
            <p>
              The list prices every pair three ways: raw basis (Kalshi mid − Polymarket mid),
              fee-adjusted edge per contract, and the edge at executable size with each
              venue's exact fee rounding. Edges are always rounded down, never up. Gold
              EDGE¢ means a fee-adjusted, size-aware positive edge on a verified pair; turn
              on ALERTS (top bar) for a browser notification when one appears. The selected
              pair's MARKET panel walks the full books for the depth-limited lock curve and
              quotes legging risk and carry next to it.
            </p>

            <div className={h}>UNVERIFIED PAIRS</div>
            <p>
              Unverified means the two venues' resolution criteria have not been confirmed
              equivalent — tie-breakers, extra time, cancellation tails can differ. The
              screener never alerts on them and keeps them collapsed on purpose. Verifying a
              pair happens in CURATE and requires your written comparison notes.
            </p>

            <div className={h}>BOOK · SELF-REPORTED RISK</div>
            <p>
              Tinli never touches your accounts. Positions are self-reported
              (data/positions.yaml) and marked against the live feed: unrealized P&L, max
              loss, 95% VaR computed two ways (parametric and Monte Carlo, both capped at max
              loss), and Kelly sizing from <em>your own</em> probability estimates. Every
              assumption ships next to the numbers — expand ASSUMPTIONS at the bottom of the
              BOOK view.
            </p>

            <div className={h}>READING THE SCREEN</div>
            <p>
              <span className="text-up">Green</span>/<span className="text-down">red</span> is
              direction (bids/positive, asks/negative). Gold is reserved for key numbers and
              warnings. <span className="text-up">● LIVE · STREAM</span> means real venue data
              pushed on change (Polymarket websocket + Kalshi fast-poll);{' '}
              <span className="text-up">● LIVE · POLL</span> is the 3s REST fallback;{' '}
              <span className="text-gold">SIMULATED DATA</span> means recorded fixtures and is
              never presented as live. DEPTH in the market panel reveals the depth curves and
              raw ladders for both venues.
            </p>

            <div className={h}>CURATE</div>
            <p>
              Pairs settle; the map needs tending. CURATE scans both venues for candidate
              matches, shows each one's resolution rules side by side, and lets you add,
              verify, or retire pairs without leaving the app. Every add lands{' '}
              <em>unverified</em> — a lock on mismatched contracts is a trap, not an arb.
            </p>
          </>
        )}

        <p className="text-muted text-[11px] mt-3">
          Read-only public market data. Quotes can be delayed or stale; nothing here is
          investment advice. Verify resolution criteria yourself before trading any edge.
        </p>

        <div className="flex items-center gap-3 mt-4">
          <button
            onClick={onClose}
            className="border border-gold text-gold rounded-sm px-4 py-1 text-[11px] tracking-[0.15em] hover:bg-gold/10"
          >
            GOT IT
          </button>
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-muted text-[11px] tracking-[0.15em] hover:text-hover"
          >
            {expanded ? 'LESS' : 'FULL GUIDE'}
          </button>
        </div>
      </div>
    </div>
  )
}
