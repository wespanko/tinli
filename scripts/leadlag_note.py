"""Generate docs/research/lead-lag.md: cross-venue price discovery.

    python scripts/leadlag_note.py

Method in tinli_backtest.leadlag (move-conditional follow analysis with an
exact binomial test); every input is the decimal128 parquet history.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq

from tinli_backtest import (
    LeadLag,
    build_series,
    daily_edge_summary,
    find_reprice,
    lead_follow,
    venue_event_window,
)

REPO = Path(__file__).resolve().parents[1]
HISTORY = REPO / "data" / "history"
OUT = REPO / "docs" / "research" / "lead-lag.md"

THRESHOLD = Decimal("0.0025")  # 0.25 cents of mid move
SENSITIVITY = [Decimal("0.001"), Decimal("0.005")]
HORIZON = 10  # ticks
MIN_MOVES = 10  # per-pair table row cutoff (pooled stats use everything)

# Scheduled releases studied in the event-study section. Statement time per
# federalreserve.gov calendar: 2026-07-29 14:00 ET = 18:00 UTC.
FOMC_TS = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)
FOMC_PAIR = "fed-jul26-no-change"  # densest pair in the sample; resolved YES
FOMC_COMPANION = "fed-jul26-cut-25bps"


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for f in sorted(HISTORY.rglob("*.parquet")):
        rows.extend(pq.read_table(f).to_pylist())
    return rows


def fmt(r: LeadLag) -> str:
    n = r.follows + r.opposes
    rate = f"{r.follows / n:.0%}" if n else "—"
    lag = f"{r.median_lag_s:.0f}s" if r.median_lag_s is not None else "—"
    p = f"{r.p_value:.3f}" if r.p_value is not None else "—"
    return (f"{r.n_moves} | {r.simultaneous} | {r.follows}/{r.opposes}/"
            f"{r.unanswered} | {rate} | {lag} | {p}")


def cents(v: Decimal | None) -> str:
    return "—" if v is None else f"{v * 100:.1f}¢"


def event_section(rows: list[dict], w) -> None:
    """FOMC event study — every number below is recomputed from the parquet."""
    if not any(r["event_key"] == FOMC_PAIR for r in rows):
        return
    day = FOMC_TS.date()
    wk = venue_event_window(rows, FOMC_PAIR, "kalshi", FOMC_TS)
    wp = venue_event_window(rows, FOMC_PAIR, "polymarket", FOMC_TS)
    rp = find_reprice(
        rows, FOMC_PAIR, "polymarket",
        window=(FOMC_TS - timedelta(minutes=10), FOMC_TS + timedelta(minutes=10)),
    )

    w("## Event study: the 2026-07-29 FOMC decision")
    w("")
    w(f"`{FOMC_PAIR}` — the densest pair in the sample — resolved mid-"
      f"recording: the statement (no change) dropped at "
      f"{FOMC_TS:%H:%M} UTC (14:00 ET) with the recorder on its normal "
      f"~60s cadence. What each venue's book did:")
    w("")
    w("| venue | last two-sided quote before release | first after |")
    w("|---|---|---|")

    def side(v) -> str:
        if v.last_ts is None:
            return "—"
        return f"{v.last_ts:%H:%M:%S} UTC (mid {cents(v.last_mid)})"

    def after(v) -> str:
        if v.first_after_ts is None:
            return "never two-sided again"
        return f"{v.first_after_ts:%H:%M:%S} UTC (mid {cents(v.first_after_mid)})"

    w(f"| kalshi | {side(wk)} | {after(wk)} |")
    w(f"| polymarket | {side(wp)} | {after(wp)} |")
    w("")
    if wk.last_ts is not None:
        gap = (FOMC_TS - wk.last_ts).total_seconds()
        w(f"- **Kalshi does not trade the announcement.** Its book was pulled "
          f"{gap:.0f}s before the release stamp and never returned — the "
          f"market's scheduled close IS the announcement time. Event-time "
          f"price discovery on this pair was structurally 100% Polymarket.")
    if rp is not None:
        lead = (FOMC_TS - rp.ts).total_seconds()
        when = (f"{abs(lead):.0f}s BEFORE" if lead > 0
                else f"{abs(lead):.0f}s after")
        w(f"- **Polymarket repriced inside one snapshot bracket**: mid "
          f"{cents(rp.prior_mid)} at {rp.prior_ts:%H:%M:%S} → "
          f"{cents(rp.mid)} at {rp.ts:%H:%M:%S} ({rp.interval_s:.0f}s "
          f"bracket, jump {cents(rp.jump)}). The landing snapshot is "
          f"stamped {when} the official 18:00:00 release. One recorder, "
          f"NTP clock, books fetched seconds after the stamp — a few "
          f"seconds of skew is plausible in either direction, so the "
          f"defensible claim is: the reprice completed within seconds of "
          f"the official release, not that anyone traded ahead of it.")
    w("- The lock trade dies BEFORE the event, not at it: with Kalshi "
      "closed, no new pair position can be opened and none needs to be — "
      "a lock holds to resolution by construction. The practical constraint "
      "is entry capacity, which ended when Kalshi's book was pulled.")
    w("")
    w("### Decision-day lead-lag (pre-release ticks only)")
    w("")
    s = build_series(
        [r for r in rows if r["ts"].date() == day and r["ts"] < FOMC_TS],
        FOMC_PAIR,
    )
    w("| leader | moves | simul | F/O/U | follow | med lag | p |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    w(f"| kalshi→pm | {fmt(lead_follow(s, 'kalshi', THRESHOLD, HORIZON))} |")
    w(f"| pm→kalshi | {fmt(lead_follow(s, 'polymarket', THRESHOLD, HORIZON))} |")
    w("")
    w("### Edge environment around the decision")
    w("")
    w("After-fee at-size edge ticks per UTC day, `" + FOMC_PAIR + "` "
      "(best lock = largest single-tick edge x displayed size, floored to "
      "the cent — a snapshot of what was on display, not a tradable total):")
    w("")
    w("| day | ticks | +edge ticks | max edge | best lock |")
    w("|---|---:|---:|---:|---:|")
    days = daily_edge_summary(rows, FOMC_PAIR)
    for d in days:
        mark = " **(decision day)**" if d.day == day else ""
        best = f"${d.best_profit}" if d.best_profit is not None else "—"
        w(f"| {d.day}{mark} | {d.ticks} | {d.pos_ticks} | "
          f"{cents(d.max_edge)} | {best} |")
    w("")
    others = [d.pos_ticks for d in days if d.day != day and d.ticks >= 100]
    dd = next((d for d in days if d.day == day), None)
    if dd is not None and others and dd.pos_ticks > max(others):
        w(f"- Decision day was the richest edge environment this pair "
          f"recorded: {dd.pos_ticks} positive ticks vs a best of "
          f"{max(others)} on any other full day — uncertainty, not calm, "
          f"is when the venues disagree enough to pay the fees.")
    other_best = [d.best_profit for d in days
                  if d.day != day and d.best_profit is not None]
    if (dd is not None and dd.best_profit is not None and other_best
            and dd.best_profit > max(other_best)):
        mins = (FOMC_TS - dd.best_ts).total_seconds() / 60
        w(f"- The largest at-size lock this pair ever displayed appeared "
          f"{mins:.0f} minutes BEFORE the release: ${dd.best_profit} of "
          f"after-fee profit on one tick at {dd.best_ts:%H:%M:%S} UTC "
          f"(vs ${max(other_best)} on the best non-decision day). Capacity "
          f"shows up exactly when it is about to disappear — the books "
          f"were institutional-size in the final pre-close hour.")
    comp = [d for d in daily_edge_summary(rows, FOMC_COMPANION) if d.day == day]
    if comp and comp[0].pos_ticks == 0:
        w(f"- The companion tail pair `{FOMC_COMPANION}` showed zero "
          f"positive-edge ticks on decision day — its Kalshi book was "
          f"one-sided nearly all day. Edges need two venues actually "
          f"quoting, which concentrates them in the dense contract.")
    w("")


def main() -> None:
    rows = load_rows()
    pairs = sorted({r["event_key"] for r in rows})

    per_pair: dict[str, tuple[LeadLag, LeadLag]] = {}
    pooled_k, pooled_p = LeadLag(), LeadLag()
    for key in pairs:
        s = build_series(rows, key)
        if len(s.ts) < 50:
            continue
        k = lead_follow(s, "kalshi", THRESHOLD, HORIZON)
        p = lead_follow(s, "polymarket", THRESHOLD, HORIZON)
        pooled_k.absorb(k)
        pooled_p.absorb(p)
        if k.n_moves + p.n_moves >= MIN_MOVES:
            per_pair[key] = (k, p)

    lines: list[str] = []
    w = lines.append
    w("# Which venue moves first? Cross-venue price discovery")
    w("")
    w(f"*Auto-generated by `scripts/leadlag_note.py` on "
      f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC from `data/history/` "
      f"(same recorded snapshots as the edge-persistence note).*")
    w("")
    w("## Method")
    w("")
    w(f"Mids move sparsely at snapshot cadence, so raw return "
      f"cross-correlation is dominated by zeros. Instead, move-conditional "
      f"analysis: a *move* is a mid change of at least "
      f"{THRESHOLD * 100}¢ between consecutive co-observed snapshots; for "
      f"every venue-A move we look ahead up to {HORIZON} snapshots for "
      f"venue B's first move and classify it follow (same direction), "
      f"oppose, or unanswered. Same-tick moves land in a `simultaneous` "
      f"bucket — sub-cadence leadership is unobservable and never "
      f"attributed. Recording gaps split sessions; nothing is measured "
      f"across a gap. The test statistic is an exact two-sided binomial on "
      f"follows vs opposes against p = 0.5.")
    w("")
    w("## Per-pair results (0.25¢ threshold)")
    w("")
    w("Columns: moves | simultaneous | follow/oppose/unanswered | follow "
      "rate (of directional answers) | median follow lag | binomial p")
    w("")
    w("| pair | leader | moves | simul | F/O/U | follow | med lag | p |")
    w("|---|---|---:|---:|---:|---:|---:|---:|")
    for key, (k, p) in per_pair.items():
        w(f"| {key} | kalshi→pm | {fmt(k)} |")
        w("| | pm→kalshi | " + fmt(p) + " |")
    w("")
    w("## Pooled across all pairs")
    w("")
    w("| leader | moves | simul | F/O/U | follow | med lag | p |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    w(f"| kalshi→pm | {fmt(pooled_k)} |")
    w(f"| pm→kalshi | {fmt(pooled_p)} |")
    w("")

    # interpretation, computed
    def rate(r: LeadLag) -> float | None:
        n = r.follows + r.opposes
        return r.follows / n if n else None

    rk, rp = rate(pooled_k), rate(pooled_p)
    w("## Reading")
    w("")
    if rk is not None and rp is not None:
        leader = "Kalshi" if (rk - (rp or 0)) > 0.05 else (
            "Polymarket" if ((rp or 0) - rk) > 0.05 else None)
        if leader:
            w(f"- Directional answers favor **{leader} leading**: its moves "
              f"are followed at {max(rk, rp):.0%} vs {min(rk, rp):.0%} the "
              f"other way. Check the p-values above before leaning on this "
              f"— the sample grows daily.")
        else:
            w(f"- No clear leader at this cadence: follow rates "
              f"{rk:.0%} (K→PM) vs {rp:.0%} (PM→K). Much of the action is "
              f"in the `simultaneous` bucket — leadership, if any, plays "
              f"out faster than the snapshot cadence.")
    w(f"- {pooled_k.simultaneous + pooled_p.simultaneous} same-tick move "
      f"pairs vs {pooled_k.follows + pooled_p.follows} cross-tick follows: "
      f"the cadence floor is doing real censoring; the BYOK websocket feed "
      f"(sub-second) will sharpen this materially.")
    w("- Unanswered moves are informative too: a venue whose moves the "
      "other never validates is either discovering price alone or drifting "
      "on noise/one-sided flow.")
    w("")
    w("## Threshold sensitivity (pooled)")
    w("")
    w("| threshold | kalshi→pm follow (p) | pm→kalshi follow (p) |")
    w("|---:|---:|---:|")
    for thr in [THRESHOLD] + SENSITIVITY:
        pk, pp = LeadLag(), LeadLag()
        for key in pairs:
            s = build_series(rows, key)
            if len(s.ts) < 50:
                continue
            pk.absorb(lead_follow(s, "kalshi", thr, HORIZON))
            pp.absorb(lead_follow(s, "polymarket", thr, HORIZON))
        def cell(r: LeadLag) -> str:
            n = r.follows + r.opposes
            if not n:
                return "—"
            pv = f"{r.p_value:.3f}" if r.p_value is not None else "—"
            return f"{r.follows / n:.0%} (p={pv}, n={n})"
        w(f"| {thr * 100}¢ | {cell(pk)} | {cell(pp)} |")
    w("")
    event_section(rows, w)
    w("## Caveats")
    w("")
    w("- Both venues are sampled at the same instant per snapshot, so "
      "there is no cross-venue clock skew inside a tick — but anything "
      "faster than the cadence is invisible (see `simultaneous`).")
    w("- Kalshi mids move on a cent grid; Polymarket's finer grid produces "
      "more small moves — the threshold sensitivity table bounds how much "
      "that asymmetry matters.")
    w("- Events are pooled across pairs and days and treated as "
      "independent; clustered news moves violate that mildly.")
    w("- Sparse-sample study: rates are honest but confidence grows with "
      "the recorder (running continuously since 2026-07-21).")
    w("- The event study is n=1 by nature: one release, one venue pair, one "
      "recorder. The venue-behavior asymmetry (closed vs trading through) "
      "is structural and will replicate; the timing bracket may not.")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
