"""Model-free bounds on a digital from LISTED call quotes.

A call spread (Ka, Kb) scaled by 1/(Kb-Ka) pays exactly 1 above Kb, 0
below Ka, and a ramp in between. Placed against a digital 1{S > K}:

  super-replication  Ka < Kb <= K : spread payoff >= digital payoff
                     -> its ASK cost is an upper bound on the digital's
                        value, and buying it hedges a SHORT digital
  sub-replication    K <= Ka < Kb : spread payoff <= digital payoff
                     -> its BID proceeds are a lower bound, and selling
                        it hedges a LONG digital

The tightest bounds use the listed strikes adjacent to K. Quotes are in
coin (Deribit convention) and converted to USD at the index; Deribit fees
(taker to open + worst-case delivery, both legs) are charged inside the
bound so that `ask` is what the hedge really costs and `bid` what it
really returns, per $1 of digital. Decimal throughout, rounded against
the user: ask rounds up, bid rounds down.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from tinli_crypto.fees import round_trip_leg_fee_usd

SIX_DP = Decimal("0.000001")


@dataclass(frozen=True)
class CallQuote:
    instrument: str
    strike: Decimal
    bid_coin: Decimal | None
    ask_coin: Decimal | None


@dataclass(frozen=True)
class SpreadBound:
    lo: CallQuote
    hi: CallQuote
    per_dollar: Decimal  # USD per $1 of digital, fees included
    fees_per_dollar: Decimal

    @property
    def width(self) -> Decimal:
        return self.hi.strike - self.lo.strike


@dataclass(frozen=True)
class HedgeBounds:
    ask: SpreadBound | None  # cost to BUY the super-replicating spread
    bid: SpreadBound | None  # proceeds from SELLING the sub-replicating spread


def _sorted(quotes: list[CallQuote]) -> list[CallQuote]:
    return sorted(quotes, key=lambda q: q.strike)


def super_replication(quotes: list[CallQuote], strike: Decimal, index: Decimal) -> SpreadBound | None:
    """Buy call(Ka), sell call(Kb) with Ka < Kb <= K. Cost = ask(Ka) - bid(Kb)."""
    qs = [q for q in _sorted(quotes) if q.strike <= strike]
    if len(qs) < 2:
        return None
    hi, lo = qs[-1], qs[-2]
    if lo.ask_coin is None or hi.bid_coin is None:
        return None
    width = hi.strike - lo.strike
    contracts_per_dollar = 1 / width  # one coin of spread covers `width` dollars of digital
    premium = (lo.ask_coin - hi.bid_coin) * index
    fees = round_trip_leg_fee_usd(lo.ask_coin, index, Decimal(1)) + round_trip_leg_fee_usd(
        hi.bid_coin, index, Decimal(1)
    )
    per_dollar = ((premium + fees) * contracts_per_dollar).quantize(SIX_DP, rounding=ROUND_CEILING)
    fees_pd = (fees * contracts_per_dollar).quantize(SIX_DP, rounding=ROUND_CEILING)
    return SpreadBound(lo=lo, hi=hi, per_dollar=per_dollar, fees_per_dollar=fees_pd)


def sub_replication(quotes: list[CallQuote], strike: Decimal, index: Decimal) -> SpreadBound | None:
    """Sell call(Ka), buy call(Kb) with K <= Ka < Kb. Proceeds = bid(Ka) - ask(Kb)."""
    qs = [q for q in _sorted(quotes) if q.strike >= strike]
    if len(qs) < 2:
        return None
    lo, hi = qs[0], qs[1]
    if lo.bid_coin is None or hi.ask_coin is None:
        return None
    width = hi.strike - lo.strike
    contracts_per_dollar = 1 / width
    premium = (lo.bid_coin - hi.ask_coin) * index
    fees = round_trip_leg_fee_usd(lo.bid_coin, index, Decimal(1)) + round_trip_leg_fee_usd(
        hi.ask_coin, index, Decimal(1)
    )
    per_dollar = ((premium - fees) * contracts_per_dollar).quantize(SIX_DP, rounding=ROUND_FLOOR)
    fees_pd = (fees * contracts_per_dollar).quantize(SIX_DP, rounding=ROUND_CEILING)
    return SpreadBound(lo=lo, hi=hi, per_dollar=per_dollar, fees_per_dollar=fees_pd)


def hedge_bounds(quotes: list[CallQuote], strike: Decimal, index: Decimal) -> HedgeBounds:
    return HedgeBounds(
        ask=super_replication(quotes, strike, index),
        bid=sub_replication(quotes, strike, index),
    )
