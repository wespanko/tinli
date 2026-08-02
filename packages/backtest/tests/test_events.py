"""Event study — hand-computed synthetic series."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from tinli_backtest.events import (
    daily_edge_summary,
    find_reprice,
    venue_event_window,
)

T0 = datetime(2026, 7, 29, 17, 55, tzinfo=UTC)
EVENT = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)


def row(i, k_mid=None, p_mid=None, key="x", gap_s=60, edge=None, size=None):
    def sides(mid):
        if mid is None:
            return None, None
        m = Decimal(mid)
        return m - Decimal("0.005"), m + Decimal("0.005")

    kb, ka = sides(k_mid)
    pb, pa = sides(p_mid)
    return {
        "event_key": key, "ts": T0 + timedelta(seconds=i * gap_s),
        "k_bid": kb, "k_ask": ka, "p_bid": pb, "p_ask": pa,
        "edge_at_size": None if edge is None else Decimal(edge),
        "max_lock_size": None if size is None else Decimal(size),
    }


def test_venue_window_halted_venue_never_returns():
    # K quotes at t0..t2 (last 17:57), dark from t3 on; event is 18:00 (t5)
    rows = [row(0, "0.75", "0.76"), row(1, "0.75", "0.76"), row(2, "0.81", "0.76"),
            row(3, None, "0.80"), row(6, None, "0.99")]
    w = venue_event_window(rows, "x", "kalshi", EVENT)
    assert w.last_ts == T0 + timedelta(seconds=120)
    assert w.last_mid == Decimal("0.81")
    assert w.first_after_ts is None and w.first_after_mid is None


def test_venue_window_trading_through():
    rows = [row(0, "0.75", "0.76"), row(4, None, "0.80"), row(6, None, "0.99")]
    w = venue_event_window(rows, "x", "polymarket", EVENT)
    # t4 = 17:59 is at/before event; t6 = 18:01 is first after
    assert (w.last_ts, w.last_mid) == (T0 + timedelta(seconds=240), Decimal("0.80"))
    assert (w.first_after_ts, w.first_after_mid) == (T0 + timedelta(seconds=360), Decimal("0.99"))


def test_reprice_bracket_hand_computed():
    # PM mid 0.80 at t4 -> 0.995 at t5: jump 0.195 >= 0.10, bracket 60s wide;
    # landing tick t5 = T0+300s = 18:00:00 exactly — inside the window
    rows = [row(3, None, "0.80"), row(4, None, "0.80"), row(5, None, "0.995")]
    rp = find_reprice(rows, "x", "polymarket",
                      window=(EVENT - timedelta(minutes=2), EVENT + timedelta(minutes=10)))
    assert rp is not None
    assert (rp.prior_ts, rp.ts) == (T0 + timedelta(seconds=240), T0 + timedelta(seconds=300))
    assert rp.jump == Decimal("0.195")
    assert rp.interval_s == 60.0


def test_reprice_ignores_jumps_landing_outside_window():
    rows = [row(0, "0.50"), row(1, "0.80"), row(10, "0.80"), row(11, "0.99")]
    # t1 lands at 17:56, before the window opens at 17:58 -> skipped;
    # t11 (18:06) is the first landing inside
    rp = find_reprice(rows, "x", "kalshi",
                      window=(EVENT - timedelta(minutes=2), EVENT + timedelta(minutes=10)))
    assert rp.ts == T0 + timedelta(seconds=11 * 60)
    assert rp.jump == Decimal("0.19")


def test_reprice_none_when_no_jump():
    rows = [row(0, "0.50"), row(1, "0.51")]
    assert find_reprice(rows, "x", "kalshi", window=(T0, EVENT)) is None


def test_daily_edge_summary_hand_computed():
    # day 1: edges None, -0.01, +0.002x100 -> pos=1, max=0.002,
    #        best = 0.002 x 100 = $0.20 exactly
    # day 2: +0.0031x70 = 0.217 -> floors to $0.21; max edge 0.0031
    rows = [
        row(0, "0.5", "0.5"),
        row(1, "0.5", "0.5", edge="-0.01", size="100"),
        row(2, "0.5", "0.5", edge="0.002", size="100"),
        row(1441, "0.5", "0.5", edge="0.0031", size="70"),  # next UTC day
    ]
    d1, d2 = daily_edge_summary(rows, "x")
    assert (d1.day, d1.ticks, d1.pos_ticks) == (date(2026, 7, 29), 3, 1)
    assert (d1.max_edge, d1.best_profit) == (Decimal("0.002"), Decimal("0.20"))
    assert d1.best_ts == T0 + timedelta(seconds=120)  # the +0.002 tick
    assert (d2.day, d2.pos_ticks, d2.max_edge) == (date(2026, 7, 30), 1, Decimal("0.0031"))
    assert d2.best_profit == Decimal("0.21")  # 0.217 floored, never rounded up


def test_one_sided_books_excluded_per_venue_not_jointly():
    # K one-sided at t1 must drop t1 from K's series but NOT from PM's
    rows = [row(0, "0.50", "0.50"), row(1, None, "0.60"), row(2, "0.52", "0.60")]
    rows[1]["k_ask"] = Decimal("0.51")  # bid still None -> one-sided
    wk = venue_event_window(rows, "x", "kalshi", EVENT)
    wp = venue_event_window(rows, "x", "polymarket", EVENT)
    assert wk.last_ts == T0 + timedelta(seconds=120)
    assert wp.last_mid == Decimal("0.60")
