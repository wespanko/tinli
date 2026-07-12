from datetime import UTC, datetime
from decimal import Decimal

from tinli_schema import Market, Position

from tinli_risk import build_report

D = Decimal
NOW = datetime(2026, 7, 6, tzinfo=UTC)


def mk_market(id: str, venue: str, event_key: str | None, bid: str, ask: str) -> Market:
    return Market(
        id=id,
        venue=venue,
        event_key=event_key,
        question=f"q:{event_key}",
        status="open",
        yes_price=D(bid),  # deliberately NOT the mid: tests prove mid wins
        no_price=D("1") - D(bid),
        best_bid=D(bid),
        best_ask=D(ask),
        volume_24h=D("1000"),
        liquidity=None,
        close_ts=NOW,
        resolution_url="https://example.test",
        icon_url=None,
        fetched_at=NOW,
    )


def test_yes_position_exposure_hand_computed():
    # mark = mid(0.48, 0.52) = 0.50; mv = 100*0.5 = 50; cost = 40; pnl = +10
    market = mk_market("kalshi:T", "kalshi", "e1", "0.48", "0.52")
    pos = Position(market_id="kalshi:T", side="yes", contracts=D("100"),
                   entry_price=D("0.40"), est_prob=D("0.6"))
    report = build_report([pos], {"kalshi:T": market}, fetched_at=NOW)
    row = report.positions[0]
    assert row.mark == D("0.50")
    assert row.market_value == D("50.00")
    assert row.cost_basis == D("40.00")
    assert row.unrealized_pnl == D("10.00")
    assert row.max_loss == D("50.00")
    # Kelly at the mid with user est 0.6: (0.6-0.5)/0.5 = 0.2
    assert row.kelly_full == D("0.2")
    assert row.kelly_half == D("0.1")


def test_no_position_marks_at_complement():
    # yes mid 0.50 -> NO mark 0.50; cost 55 -> pnl -5
    market = mk_market("kalshi:T", "kalshi", "e1", "0.48", "0.52")
    pos = Position(market_id="kalshi:T", side="no", contracts=D("100"), entry_price=D("0.55"))
    row = build_report([pos], {"kalshi:T": market}, fetched_at=NOW).positions[0]
    assert row.mark == D("0.50")
    assert row.unrealized_pnl == D("-5.00")
    assert row.kelly_full is None  # no est_prob, no Kelly


def test_cross_venue_lock_has_zero_var_and_flat_net():
    # YES 100 on kalshi (mid .50) + NO 100 on polymarket (yes mid .52):
    # if YES: +100*.50 - 100*.48 = +2 ; if NO: -100*.50 + 100*.52 = +2
    # Same P&L both branches -> the engine must report ZERO risk.
    k = mk_market("kalshi:T", "kalshi", "lock", "0.48", "0.52")
    p = mk_market("polymarket:0xabc", "polymarket", "lock", "0.50", "0.54")
    book = [
        Position(market_id="kalshi:T", side="yes", contracts=D("100"), entry_price=D("0.61")),
        Position(market_id="polymarket:0xabc", side="no", contracts=D("100"), entry_price=D("0.37")),
    ]
    report = build_report(book, {m.id: m for m in (k, p)}, fetched_at=NOW)
    assert report.max_loss == 0
    assert report.var_95_parametric == 0
    assert report.var_95_monte_carlo == 0
    (event,) = report.by_event
    assert event.event_id == "lock"
    assert event.net_yes_contracts == 0
    assert event.delta_if_yes == event.delta_if_no == D("2.00")
    assert event.prob_yes == D("0.51")  # mean of the two venue mids


def test_unmarked_position_reported_but_excluded():
    market = mk_market("kalshi:T", "kalshi", "e1", "0.48", "0.52")
    book = [
        Position(market_id="kalshi:T", side="yes", contracts=D("100"), entry_price=D("0.40")),
        Position(market_id="kalshi:GONE", side="yes", contracts=D("100"), entry_price=D("0.40")),
    ]
    report = build_report(book, {"kalshi:T": market}, fetched_at=NOW)
    assert report.unmarked_positions == 1
    ghost = report.positions[1]
    assert ghost.mark is None and ghost.market_value is None
    # aggregates count ONLY the marked leg
    assert report.total_market_value == D("50.00")
    assert report.total_cost_basis == D("40.00")
    assert report.max_loss == D("50.00")
    assert any("EXCLUDED" in a for a in report.assumptions)


def test_unmapped_markets_are_independent_events():
    a = mk_market("kalshi:A", "kalshi", None, "0.48", "0.52")
    b = mk_market("kalshi:B", "kalshi", None, "0.48", "0.52")
    book = [
        Position(market_id="kalshi:A", side="yes", contracts=D("100"), entry_price=D("0.5")),
        Position(market_id="kalshi:B", side="yes", contracts=D("100"), entry_price=D("0.5")),
    ]
    report = build_report(book, {m.id: m for m in (a, b)}, fetched_at=NOW)
    assert {e.event_id for e in report.by_event} == {"kalshi:A", "kalshi:B"}
