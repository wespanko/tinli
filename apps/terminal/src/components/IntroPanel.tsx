import { useState } from 'react'

/** First-run explainer and the help overlay. The short form is two
    paragraphs and the keys; the full guide unfolds on request. */

export default function IntroPanel({
  onClose,
  full = false,
}: {
  onClose: () => void
  full?: boolean
}) {
  const [expanded, setExpanded] = useState(full)
  const h = 'label mt-4 mb-1'
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
          <span className="text-muted text-[12px]">Kalshi and Polymarket on one screen.</span>
        </div>

        <p className="mt-3">
          The same event often trades on both venues. Buy YES on one and NO on the other and the
          position pays $1 at resolution either way. Tinli prices that lock for every mapped
          pair after both venues' fees, at the size the books can actually fill.
        </p>
        <p className="mt-2">
          Most gaps disappear once fees are counted. A <span className="text-gold">gold edge</span>{' '}
          is a real one. Pairs whose resolution rules have not been compared stay collapsed under
          Unverified, because a gap between two different contracts is not an edge.
        </p>

        <p className="font-mono text-[12px] text-muted mt-3">
          j k move · / filter · 1-4 views · ? help · esc close
        </p>

        {expanded && (
          <>
            <div className={h}>The lock</div>
            <p>
              Each pair is priced three ways: raw basis (Kalshi mid minus Polymarket mid), edge
              per contract after fees, and edge at executable size with each venue's fee
              rounding. Edges round down, never up. The market panel walks both books for the
              full lock curve and quotes legging risk and carry beside it. Alerts, in the top
              bar, sends a browser notification when a verified pair turns positive.
            </p>

            <div className={h}>Unverified</div>
            <p>
              Two venues can describe the same event with different tie-breakers, deadlines, or
              cancellation terms. Until someone has read both rulebooks and confirmed they match,
              a pair is unverified: it never alerts and stays collapsed. Verification happens in
              Curate and requires written notes on what was compared.
            </p>

            <div className={h}>Book</div>
            <p>
              Positions are self-reported and marked against the live feed: unrealized P&L, max
              loss, 95% VaR two ways (parametric and Monte Carlo, both capped at max loss), and
              half-Kelly sizing from your own probability estimates. Tinli never connects to an
              account and never places orders.
            </p>

            <div className={h}>Crypto</div>
            <p>
              Every Kalshi BTC and ETH strike is priced against the Deribit option chain. Fair
              is the digital's value off the mark-IV surface, a view on vol with nothing hedged.
              Hedge is model-free: the listed call spread that pays at least, or at most, what
              the binary pays. Edge is what is left after both venues' fees. Deribit expires at
              08:00 UTC and Kalshi at 5pm ET, so every hedge outlives its binary by the hours
              shown on the expiry tab. That gap, and the difference in settlement indices, is
              disclosed, not priced.
            </p>

            <div className={h}>Reading the screen</div>
            <p>
              <span className="text-up">Green</span> and <span className="text-down">red</span>{' '}
              are direction: bids and gains, asks and losses. Gold marks key numbers and warnings.{' '}
              <span className="text-up">Live</span> is venue data pushed on change, with a 3s
              polling fallback. <span className="text-gold">Simulated data</span> means recorded
              fixtures. Depth, in the market panel, opens the depth curves and raw ladders.
            </p>

            <div className={h}>Curate</div>
            <p>
              Pairs settle and the map needs tending. Curate scans both venues for candidate
              matches, shows their resolution rules side by side, and lets you add, verify, or
              retire pairs. Every addition starts unverified.
            </p>
          </>
        )}

        <p className="text-muted text-[11px] mt-4">
          Read-only public market data. Quotes can be delayed. Not investment advice.
        </p>

        <div className="flex items-center gap-4 mt-4">
          <button onClick={onClose} className="btn-gold px-4 py-1">
            Got it
          </button>
          <button onClick={() => setExpanded((v) => !v)} className="label hover:text-hover">
            {expanded ? 'Less' : 'Full guide'}
          </button>
        </div>
      </div>
    </div>
  )
}
