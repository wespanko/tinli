/** First-run explainer + HELP overlay. Dense and honest, like the product:
    what the numbers mean and what they do NOT mean. */

export default function IntroPanel({ onClose }: { onClose: () => void }) {
  const h = 'text-muted text-[10px] font-sans font-medium tracking-[0.15em] mt-3 mb-1'
  return (
    <div
      className="fixed inset-0 z-50 bg-bg/85 flex items-center justify-center p-6"
      onClick={onClose}
    >
      <div
        className="bg-panel border border-line rounded-sm max-w-2xl max-h-[85vh] overflow-y-auto p-5 text-[13px] leading-relaxed"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-gold font-bold tracking-[0.2em] text-[15px]">TINLI</span>
          <span className="text-muted text-[12px]">
            one screen across Kalshi and Polymarket, for quant-minded traders
          </span>
        </div>

        <div className={h}>THE LOCK</div>
        <p>
          The same real-world event often trades on both venues. Buy YES on one and NO on the
          other and you collect $1 at resolution <em>whichever way it goes</em> — a lock. The
          DIVERGENCE panel prices that lock for every mapped pair: raw basis, then fee-adjusted
          edge per contract, then the edge at executable size with each venue's exact fee
          rounding. Edges are always rounded down, never up.
        </p>

        <div className={h}>WHY MOST EDGES ARE NEGATIVE</div>
        <p>
          Fees eat small dislocations — that is normal and the screen shows it honestly. A{' '}
          <span className="text-gold">gold</span> @SIZE¢ value is the rare real thing: a
          fee-adjusted, size-aware positive edge on a verified pair. Turn on ALERTS (top right)
          to get a browser notification when one appears.
        </p>

        <div className={h}>! UNVERIFIED PAIRS</div>
        <p>
          <span className="text-gold">!</span> means the two venues' resolution criteria have not
          been confirmed equivalent — tie-breakers, extra time, cancellation tails can differ. A
          big gap on an unverified pair is a trap, not an edge; the screener sorts them last on
          purpose.
        </p>

        <div className={h}>RISK · SELF-REPORTED BOOK</div>
        <p>
          Tinli never touches your accounts. Positions are self-reported (data/positions.yaml)
          and marked against the live feed: unrealized P&L, max loss, 95% VaR computed two ways
          (parametric and Monte Carlo, both capped at max loss), and Kelly sizing from{' '}
          <em>your own</em> probability estimates. Every assumption ships next to the numbers —
          expand ASSUMPTIONS at the bottom of the panel.
        </p>

        <div className={h}>READING THE SCREEN</div>
        <p>
          <span className="text-up">Green</span>/<span className="text-down">red</span> is
          direction (bids/positive, asks/negative). Gold is reserved for key numbers and
          warnings. <span className="text-up">● LIVE · STREAM</span> means real venue data pushed
          on change (Polymarket websocket + Kalshi fast-poll); <span className="text-up">● LIVE
          · POLL</span> is the 3s REST fallback;{' '}
          <span className="text-gold">SIMULATED DATA</span> means recorded fixtures and is never
          presented as live. Click any watchlist or divergence row to load it in the market
          panel.
        </p>

        <p className="text-muted text-[11px] mt-3">
          Read-only public market data. Quotes can be delayed or stale; nothing here is
          investment advice. Verify resolution criteria yourself before trading any edge.
        </p>

        <button
          onClick={onClose}
          className="mt-4 border border-gold text-gold rounded-sm px-4 py-1 text-[11px] tracking-[0.15em] hover:bg-gold/10"
        >
          GOT IT
        </button>
      </div>
    </div>
  )
}
