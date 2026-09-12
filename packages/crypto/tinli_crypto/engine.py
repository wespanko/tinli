"""Crypto digital screener: every Kalshi BTC/ETH above/below contract
priced two ways against the Deribit option chain.

  MODEL   fair value = e^(-rT) N(d2) off the interpolated mark-IV surface
          (tinli_crypto.model). model_edge is what a Kalshi taker earns
          versus that estimate after Kalshi's fee. It is a VIEW on vol, not
          a lock: nothing is hedged.
  HEDGE   model-free bounds from listed call spreads (tinli_crypto.
          replication) at the first Deribit expiry AT OR AFTER the Kalshi
          close. hedge_edge is the locked profit per contract from buying
          the cheap side on Kalshi and taking the opposite spread on
          Deribit, after both venues' fees. Because Deribit settles at
          08:00 UTC and Kalshi at 21:00 UTC, the hedge expires
          hedge_gap_hours AFTER the binary: the position is flat once the
          binary settles only if the spread is unwound then, and the gap is
          reported on every row rather than hidden.

Both edges report the better of the two directions and are floored
(rounded against the user). Missing quotes make fields None — no quote,
no claimed edge. Sizing: max_size is Kalshi top-of-book only; Deribit
depth is NOT modeled in this version (min trade 0.1 coin = width/10
contracts), and the ladder's assumptions say so.

Settlement basis: Kalshi settles on a 60-second average of CF Benchmarks'
real-time index (BRTI / ETHUSD_RTI); Deribit on its own index. Neither the
level difference nor the averaging is modeled — stated, not guessed.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, Field

from tinli_divergence import VenueTop
from tinli_divergence.fees import KalshiFees
from tinli_crypto.model import SECONDS_PER_YEAR, ExpirySlice, Surface, digital_fair_value
from tinli_crypto.replication import CallQuote, hedge_bounds

ONE = Decimal("1")
HUNDRED = Decimal("100")
SIX_DP = Decimal("0.000001")
FOUR_DP = Decimal("0.0001")
TWO_DP = Decimal("0.01")

Coin = Literal["BTC", "ETH"]


@dataclass(frozen=True)
class BinaryQuote:
    """A Kalshi above/below contract, YES-side, normalized (adapter output)."""

    ticker: str
    question: str
    strike: Decimal
    close_ts: datetime
    bid: Decimal | None
    bid_size: Decimal | None
    ask: Decimal | None
    ask_size: Decimal | None
    fetched_at: datetime


@dataclass(frozen=True)
class OptionQuote:
    """One Deribit option from the book summary (adapter output). Prices in
    coin; mark_iv as a FRACTION (0.45), not the venue's percent."""

    instrument: str
    strike: Decimal
    expiry: datetime
    option_type: Literal["call", "put"]
    bid_coin: Decimal | None
    ask_coin: Decimal | None
    mark_iv: Decimal | None
    underlying_price: Decimal | None


class CryptoItem(BaseModel):
    ticker: str
    question: str
    strike: Decimal
    close_ts: datetime
    kalshi: VenueTop
    fair_value: Decimal | None = Field(description="model digital value, dollars per $1 contract")
    iv: Decimal | None = Field(description="interpolated implied vol at this strike/expiry, fraction")
    mispricing_cents: Decimal | None = Field(
        description="100 x (kalshi mid - fair_value); positive = Kalshi rich vs the vol surface"
    )
    model_direction: Literal["buy_yes", "buy_no"] | None
    model_edge: Decimal | None = Field(
        description="per-contract edge vs fair value after Kalshi's taker fee, floored; UNHEDGED"
    )
    hedge_bid: Decimal | None = Field(
        description="proceeds per $1 from selling the sub-replicating Deribit call spread, after fees"
    )
    hedge_ask: Decimal | None = Field(
        description="cost per $1 of buying the super-replicating Deribit call spread, after fees"
    )
    hedge_legs: str | None = Field(description="Deribit instruments of the spread behind hedge_edge")
    hedge_width: Decimal | None = Field(description="spread width in USD = Kalshi contracts per option")
    hedge_direction: Literal["buy_yes_sell_spread", "buy_no_buy_spread"] | None
    hedge_edge: Decimal | None = Field(
        description="locked per-contract profit after BOTH venues' fees, floored; see hedge_gap_hours"
    )
    max_size: Decimal | None = Field(
        description="Kalshi top-of-book depth on the traded side, whole contracts; Deribit depth unmodeled"
    )
    fetched_at: datetime


class ExpiryLadder(BaseModel):
    close_ts: datetime
    hedge_expiry: datetime | None
    hedge_gap_hours: Decimal | None = Field(
        description="hours the Deribit hedge outlives the Kalshi binary; never zero in practice"
    )
    atm_iv: Decimal | None
    items: list[CryptoItem]


class CryptoLadder(BaseModel):
    coin: Coin
    index: Decimal = Field(description="Deribit index price, USD")
    rf_rate: Decimal
    expiries: list[ExpiryLadder]
    assumptions: list[str]
    fetched_at: datetime


ASSUMPTIONS = [
    "Fair value is e^(-rT) N(d2) under lognormal dynamics off Deribit mark IVs: "
    "IV linear in strike within an expiry, total variance linear in time across "
    "expiries, forward linear in time from the index. It is an estimate, not a price.",
    "Kalshi settles on a 60-second average of CF Benchmarks' real-time index; "
    "Deribit on its own index. The level difference and the averaging are not modeled.",
    "Deribit expiries are 08:00 UTC, Kalshi closes 21:00 UTC: every hedge outlives "
    "its binary by hedge_gap_hours. hedge_edge assumes the spread is unwound at "
    "intrinsic when the binary settles; residual vol exposure over the gap is not priced.",
    "Deribit fees: 0.0003 coin/contract taker + 0.00015 coin/contract delivery, each "
    "capped at 12.5% of premium, charged on BOTH spread legs (overstates). Kalshi: "
    "0.07 x P x (1-P) idealized per contract.",
    "max_size is Kalshi top-of-book only. Deribit depth and its 0.1-coin minimum "
    "trade (= width/10 contracts) are not modeled in this version.",
    "Kalshi strikes ending in .99 ('above 77,499.99') are priced as the whole-dollar "
    "strike ('at or above 77,500') — identical on a cent-resolved index, and it is the "
    "listed Deribit strike.",
    "Before the first listed Deribit expiry, vol is taken flat from that expiry: intraday "
    "(hourly) binaries inherit a daily option's IV. Intraday vol seasonality is not modeled.",
    "Edges round down; fair value rounds to nearest. Nothing here is investment advice.",
]


def _mid(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    if bid is None or ask is None:
        return None
    return (bid + ask) / 2


def build_surface(options: list[OptionQuote], index: Decimal, now: datetime) -> Surface:
    """Per expiry: one IV per strike (call and put marks averaged when both
    quote), the venue's underlying as the forward. Expiries with no IVs or
    already past are dropped."""
    by_exp: dict[datetime, list[OptionQuote]] = {}
    for o in options:
        if o.mark_iv is None or o.mark_iv <= 0:
            continue
        by_exp.setdefault(o.expiry, []).append(o)
    slices = []
    for exp in sorted(by_exp):
        t = (exp - now).total_seconds() / SECONDS_PER_YEAR
        if t <= 0:
            continue
        quotes = by_exp[exp]
        per_strike: dict[Decimal, list[Decimal]] = {}
        for o in quotes:
            per_strike.setdefault(o.strike, []).append(o.mark_iv)  # type: ignore[arg-type]
        strikes = sorted(per_strike)
        ivs = [float(sum(per_strike[k]) / len(per_strike[k])) for k in strikes]
        fwd_samples = [o.underlying_price for o in quotes if o.underlying_price]
        fwd = float(sum(fwd_samples) / len(fwd_samples)) if fwd_samples else float(index)
        slices.append(ExpirySlice(t_years=t, forward=fwd, strikes=tuple(float(k) for k in strikes), ivs=tuple(ivs)))
    return Surface(index=float(index), slices=tuple(slices))


def _hedge_expiry(options: list[OptionQuote], close_ts: datetime) -> datetime | None:
    later = sorted({o.expiry for o in options if o.expiry >= close_ts})
    return later[0] if later else None


def _kalshi_fee(price: Decimal) -> Decimal:
    return KalshiFees().taker_rate() * price * (ONE - price)


def compute_item(
    q: BinaryQuote,
    surface: Surface,
    calls_at_hedge: list[CallQuote],
    index: Decimal,
    now: datetime,
    rf_rate: Decimal,
) -> CryptoItem:
    t = (q.close_ts - now).total_seconds() / SECONDS_PER_YEAR
    # Kalshi lists "above 77,499.99" on a cent-resolved index: that is
    # "at or above 77,500", the listed Deribit strike. Snap to the dollar so
    # the replication uses the exact spread instead of the next one down.
    strike = q.strike.quantize(ONE, rounding=ROUND_HALF_UP)
    fair: Decimal | None = None
    iv: Decimal | None = None
    if t > 0 and surface.slices:
        fair, iv = digital_fair_value(surface, strike, t, rf_rate)

    mid = _mid(q.bid, q.ask)
    mispricing = ((mid - fair) * HUNDRED).quantize(TWO_DP) if mid is not None and fair is not None else None

    # model edge: both directions, best wins, floored
    model_dir: Literal["buy_yes", "buy_no"] | None = None
    model_edge: Decimal | None = None
    if fair is not None:
        cands: list[tuple[Decimal, Literal["buy_yes", "buy_no"]]] = []
        if q.ask is not None:
            cands.append((fair - q.ask - _kalshi_fee(q.ask), "buy_yes"))
        if q.bid is not None:
            no_price = ONE - q.bid
            cands.append(((ONE - fair) - no_price - _kalshi_fee(no_price), "buy_no"))
        if cands:
            best, model_dir = max(cands, key=lambda c: c[0])
            model_edge = best.quantize(SIX_DP, rounding=ROUND_FLOOR)

    # hedge edge: listed spread bounds at the first Deribit expiry after close
    bounds = hedge_bounds(calls_at_hedge, strike, index) if calls_at_hedge else None
    hedge_bid = bounds.bid.per_dollar if bounds and bounds.bid else None
    hedge_ask = bounds.ask.per_dollar if bounds and bounds.ask else None
    hedge_dir: Literal["buy_yes_sell_spread", "buy_no_buy_spread"] | None = None
    hedge_edge: Decimal | None = None
    legs: str | None = None
    width: Decimal | None = None
    hcands: list[tuple[Decimal, Literal["buy_yes_sell_spread", "buy_no_buy_spread"], str, Decimal]] = []
    if bounds and bounds.bid and q.ask is not None:
        hcands.append((
            hedge_bid - q.ask - _kalshi_fee(q.ask),  # type: ignore[operator]
            "buy_yes_sell_spread",
            f"sell {bounds.bid.lo.instrument} / buy {bounds.bid.hi.instrument}",
            bounds.bid.width,
        ))
    if bounds and bounds.ask and q.bid is not None:
        no_price = ONE - q.bid
        hcands.append((
            q.bid - hedge_ask - _kalshi_fee(no_price),  # type: ignore[operator]
            "buy_no_buy_spread",
            f"buy {bounds.ask.lo.instrument} / sell {bounds.ask.hi.instrument}",
            bounds.ask.width,
        ))
    if hcands:
        best_h = max(hcands, key=lambda c: c[0])
        hedge_edge = best_h[0].quantize(SIX_DP, rounding=ROUND_FLOOR)
        hedge_dir, legs, width = best_h[1], best_h[2], best_h[3]

    # size: the Kalshi side actually traded by the best hedge (or model) direction
    traded_dir = hedge_dir or model_dir
    size_src = None
    if traded_dir in ("buy_yes", "buy_yes_sell_spread"):
        size_src = q.ask_size
    elif traded_dir in ("buy_no", "buy_no_buy_spread"):
        size_src = q.bid_size
    max_size = size_src.quantize(ONE, rounding=ROUND_FLOOR) if size_src is not None else None

    return CryptoItem(
        ticker=q.ticker,
        question=q.question,
        strike=q.strike,
        close_ts=q.close_ts,
        kalshi=VenueTop(bid=q.bid, bid_size=q.bid_size, ask=q.ask, ask_size=q.ask_size),
        fair_value=fair,
        iv=iv,
        mispricing_cents=mispricing,
        model_direction=model_dir,
        model_edge=model_edge,
        hedge_bid=hedge_bid,
        hedge_ask=hedge_ask,
        hedge_legs=legs,
        hedge_width=width,
        hedge_direction=hedge_dir,
        hedge_edge=hedge_edge,
        max_size=max_size,
        fetched_at=q.fetched_at,
    )


def compute_ladder(
    coin: Coin,
    binaries: list[BinaryQuote],
    options: list[OptionQuote],
    index: Decimal,
    now: datetime,
    rf_rate: Decimal,
) -> CryptoLadder:
    surface = build_surface(options, index, now)
    by_close: dict[datetime, list[BinaryQuote]] = {}
    for b in binaries:
        if b.close_ts > now:
            by_close.setdefault(b.close_ts, []).append(b)
    expiries: list[ExpiryLadder] = []
    for close in sorted(by_close):
        hedge_exp = _hedge_expiry(options, close)
        calls = [
            CallQuote(instrument=o.instrument, strike=o.strike, bid_coin=o.bid_coin, ask_coin=o.ask_coin)
            for o in options
            if hedge_exp is not None and o.expiry == hedge_exp and o.option_type == "call"
        ]
        gap = (
            (Decimal(int((hedge_exp - close).total_seconds())) / Decimal(3600)).quantize(TWO_DP)
            if hedge_exp
            else None
        )
        t = (close - now).total_seconds() / SECONDS_PER_YEAR
        atm_iv: Decimal | None = None
        if surface.slices and t > 0:
            _, atm_iv = digital_fair_value(surface, index, t, rf_rate)
        items = [
            compute_item(b, surface, calls, index, now, rf_rate)
            for b in sorted(by_close[close], key=lambda b: b.strike)
        ]
        expiries.append(
            ExpiryLadder(close_ts=close, hedge_expiry=hedge_exp, hedge_gap_hours=gap, atm_iv=atm_iv, items=items)
        )
    fetched = max([b.fetched_at for b in binaries], default=now)
    return CryptoLadder(
        coin=coin,
        index=index,
        rf_rate=rf_rate,
        expiries=expiries,
        assumptions=list(ASSUMPTIONS),
        fetched_at=fetched,
    )
