"""Lead-lag — hand-computed synthetic series."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tinli_backtest.leadlag import LeadLag, build_series, lead_follow, sessions

T0 = datetime(2026, 7, 14, tzinfo=UTC)
THR = Decimal("0.0025")  # 0.25 cents


def row(i, k_mid, p_mid, key="x", gap_s=30):
    k = Decimal(k_mid)
    p = Decimal(p_mid)
    return {
        "event_key": key, "ts": T0 + timedelta(seconds=i * gap_s),
        "k_bid": k - Decimal("0.005"), "k_ask": k + Decimal("0.005"),
        "p_bid": p - Decimal("0.005"), "p_ask": p + Decimal("0.005"),
    }


def test_kalshi_leads_polymarket_by_two_ticks():
    # kalshi steps 0.50 -> 0.53 at t1; polymarket follows at t3 (60s later)
    rows = [
        row(0, "0.50", "0.50"),
        row(1, "0.53", "0.50"),  # K move (+)
        row(2, "0.53", "0.50"),
        row(3, "0.53", "0.53"),  # P follows (+)
        row(4, "0.53", "0.53"),
    ]
    s = build_series(rows, "x")
    k_lead = lead_follow(s, "kalshi", THR)
    assert (k_lead.n_moves, k_lead.follows, k_lead.opposes, k_lead.unanswered) == (1, 1, 0, 0)
    assert k_lead.median_lag_s == 60.0
    # the reverse direction: P's move at t3 is never answered by K
    p_lead = lead_follow(s, "polymarket", THR)
    assert (p_lead.n_moves, p_lead.follows, p_lead.unanswered) == (1, 0, 1)


def test_same_tick_moves_are_simultaneous_not_leadership():
    rows = [row(0, "0.50", "0.50"), row(1, "0.53", "0.53")]
    s = build_series(rows, "x")
    r = lead_follow(s, "kalshi", THR)
    assert (r.n_moves, r.simultaneous, r.follows) == (1, 1, 0)


def test_opposite_direction_response_counts_as_oppose():
    rows = [row(0, "0.50", "0.50"), row(1, "0.53", "0.50"), row(2, "0.53", "0.47")]
    s = build_series(rows, "x")
    r = lead_follow(s, "kalshi", THR)
    assert (r.follows, r.opposes) == (0, 1)


def test_recording_gap_splits_sessions_and_blocks_follow():
    # K moves at t1; the only P move is AFTER a 10-minute recording gap —
    # it must not count as a follow, and the post-gap first tick must not
    # register as a move either (no prior tick in its session)
    rows = [row(0, "0.50", "0.50"), row(1, "0.53", "0.50")]
    late = row(21, "0.53", "0.53")  # 21*30s = 630s after t0 -> gap > 120s
    rows.append(late)
    s = build_series(rows, "x")
    assert [list(r) for r in sessions(s.ts, 120.0)] == [[0, 1]]  # lone tick dropped
    r = lead_follow(s, "kalshi", THR)
    assert (r.n_moves, r.follows, r.unanswered) == (1, 0, 1)


def test_binomial_p_value_hand_computed():
    # 8 follows, 2 opposes: two-sided exact binomial vs p=0.5 on n=10:
    # P(X >= 8) = (C(10,8)+C(10,9)+C(10,10))/2^10 = (45+10+1)/1024
    # two-sided = 2 x 56/1024 = 0.109375
    r = LeadLag(n_moves=10, follows=8, opposes=2)
    assert abs(r.p_value - 0.109375) < 1e-12
    assert LeadLag().p_value is None


def test_rows_with_one_sided_books_are_excluded():
    rows = [row(0, "0.50", "0.50"), row(1, "0.53", "0.50"), row(2, "0.56", "0.53")]
    rows[1]["p_bid"] = None  # polymarket book one-sided at t1
    s = build_series(rows, "x")
    assert len(s.ts) == 2  # t1 dropped entirely: mids must be co-observed
