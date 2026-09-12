"""Engine wiring on a synthetic chain: strike snapping, direction choice,
no-quote -> no edge, and the hedge/model relationship."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tinli_crypto import BinaryQuote, OptionQuote, compute_ladder

NOW = datetime(2026, 9, 12, 21, 0, tzinfo=UTC)
CLOSE = NOW + timedelta(hours=24)  # Kalshi 5pm ET next day
D_EXP = NOW + timedelta(hours=35)  # Deribit 08:00 UTC the day after
INDEX = Decimal("77000")


def opt(strike, kind, bid, ask, iv="0.40", expiry=D_EXP):
    return OptionQuote(
        instrument=f"BTC-X-{strike}-{'C' if kind == 'call' else 'P'}",
        strike=Decimal(strike),
        expiry=expiry,
        option_type=kind,
        bid_coin=Decimal(bid) if bid else None,
        ask_coin=Decimal(ask) if ask else None,
        mark_iv=Decimal(iv),
        underlying_price=INDEX,
    )


# a decreasing, convex call curve with 500-wide strikes around the index
CHAIN = [
    opt("76000", "call", "0.0200", "0.0210"),
    opt("76500", "call", "0.0140", "0.0150"),
    opt("77000", "call", "0.0095", "0.0105"),
    opt("77500", "call", "0.0060", "0.0070"),
    opt("78000", "call", "0.0038", "0.0046"),
    opt("78500", "call", "0.0022", "0.0030"),
    opt("77000", "put", "0.0090", "0.0100"),
]


def binary(strike, bid, ask, bid_size="100", ask_size="100"):
    return BinaryQuote(
        ticker=f"KXBTCD-T{strike}",
        question=f"${strike} or above",
        strike=Decimal(strike),
        close_ts=CLOSE,
        bid=Decimal(bid) if bid else None,
        bid_size=Decimal(bid_size) if bid else None,
        ask=Decimal(ask) if ask else None,
        ask_size=Decimal(ask_size) if ask else None,
        fetched_at=NOW,
    )


def test_strike_snaps_to_listed_dollar_strike():
    ladder = compute_ladder("BTC", [binary("77499.99", "0.40", "0.42")], CHAIN, INDEX, NOW, Decimal("0"))
    item = ladder.expiries[0].items[0]
    assert item.strike == Decimal("77499.99")  # displayed as listed on Kalshi
    # replication used 77,500 exactly: sub spread (77500, 78000), super (77000, 77500)
    assert item.hedge_legs is not None
    assert "77500" in item.hedge_legs
    assert "76500" not in item.hedge_legs
    assert ladder.expiries[0].hedge_expiry == D_EXP
    assert ladder.expiries[0].hedge_gap_hours == Decimal("11.00")


def test_no_quote_no_edge():
    ladder = compute_ladder("BTC", [binary("77500", None, None)], CHAIN, INDEX, NOW, Decimal("0"))
    item = ladder.expiries[0].items[0]
    assert item.fair_value is not None  # the model still prices it
    assert item.model_edge is None and item.hedge_edge is None and item.max_size is None


def test_direction_follows_the_cheap_side():
    # Kalshi far too cheap vs the model -> buy YES; far too rich -> buy NO
    cheap = compute_ladder("BTC", [binary("77000", "0.10", "0.11")], CHAIN, INDEX, NOW, Decimal("0"))
    rich = compute_ladder("BTC", [binary("77000", "0.90", "0.91")], CHAIN, INDEX, NOW, Decimal("0"))
    assert cheap.expiries[0].items[0].model_direction == "buy_yes"
    assert rich.expiries[0].items[0].model_direction == "buy_no"
    assert cheap.expiries[0].items[0].max_size == Decimal("100")  # ask side depth


def test_hedge_bounds_bracket_and_edge_is_conservative():
    ladder = compute_ladder("BTC", [binary("77500", "0.40", "0.42")], CHAIN, INDEX, NOW, Decimal("0"))
    it = ladder.expiries[0].items[0]
    assert it.hedge_bid is not None and it.hedge_ask is not None
    assert it.hedge_bid < it.hedge_ask
    # hand check, sub spread (77500, 78000): bid 0.0060 - ask 0.0046 = 0.0014 coin = 107.80 USD;
    # fees: (0.0003 + 0.00015) x 77000 = 34.65 per leg x 2 = 69.30 -> (107.80 - 69.30) / 500 = 0.077
    assert it.hedge_bid == Decimal("0.077000")
    # super spread (77000, 77500): ask 0.0105 - bid 0.0060 = 0.0045 = 346.50 + 69.30 -> 415.80 / 500
    assert it.hedge_ask == Decimal("0.831600")
    # both edges negative here (bounds are loose vs a 40-42c market), hedge below model
    assert it.hedge_edge is not None and it.model_edge is not None
    assert it.hedge_edge < it.model_edge


def test_expired_binaries_are_dropped_and_expiries_sorted():
    old = BinaryQuote("X", "x", Decimal("77000"), NOW - timedelta(hours=1), None, None, None, None, NOW)
    later = binary("77000", "0.5", "0.51")
    later2 = BinaryQuote("Y", "y", Decimal("77000"), CLOSE + timedelta(days=5), Decimal("0.5"),
                         Decimal("1"), Decimal("0.51"), Decimal("1"), NOW)
    ladder = compute_ladder("BTC", [later2, old, later], CHAIN, INDEX, NOW, Decimal("0"))
    assert [e.close_ts for e in ladder.expiries] == [CLOSE, CLOSE + timedelta(days=5)]
    # the 5-day binary has no Deribit expiry at or after it in this chain
    assert ladder.expiries[1].hedge_expiry is None
    assert ladder.expiries[1].items[0].hedge_edge is None
