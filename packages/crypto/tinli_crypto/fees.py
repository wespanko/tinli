"""Deribit option taker fees, from the published schedule.

Source: https://www.deribit.com/kb/fees (read 2026-09-12) and the
`taker_commission` field on every instrument from
/public/get_instruments (0.0003 for BTC and ETH options, verified live
2026-09-12):

  taker fee     = 0.0003 coin per contract, but never more than 12.5% of
                  the option's price
  delivery fee  = 0.00015 coin per contract on options settled in the
                  money, never more than 12.5% of the option's price

One Deribit option contract is ONE coin (contract_size 1.0 on every BTC
and ETH option, verified live 2026-09-12). Quotes are in coin; a USD
amount is coin x index. All money in Decimal; every fee rounds UP (the
user pays more, never less).
"""

from decimal import ROUND_CEILING, Decimal

TAKER_PER_CONTRACT_COIN = Decimal("0.0003")
DELIVERY_PER_CONTRACT_COIN = Decimal("0.00015")
FEE_CAP_OF_PREMIUM = Decimal("0.125")
CENT = Decimal("0.01")


def taker_fee_usd(premium_coin: Decimal, index_usd: Decimal, contracts: Decimal) -> Decimal:
    """Fee in USD for a taker fill of `contracts` at `premium_coin` per contract."""
    per_contract = min(TAKER_PER_CONTRACT_COIN, FEE_CAP_OF_PREMIUM * premium_coin)
    return (per_contract * index_usd * contracts).quantize(CENT, rounding=ROUND_CEILING)


def delivery_fee_usd(premium_coin: Decimal, index_usd: Decimal, contracts: Decimal) -> Decimal:
    """Worst case: the leg settles in the money and pays the delivery fee."""
    per_contract = min(DELIVERY_PER_CONTRACT_COIN, FEE_CAP_OF_PREMIUM * premium_coin)
    return (per_contract * index_usd * contracts).quantize(CENT, rounding=ROUND_CEILING)


def round_trip_leg_fee_usd(premium_coin: Decimal, index_usd: Decimal, contracts: Decimal) -> Decimal:
    """Everything one option leg can cost in fees between entry and expiry:
    the taker fee to open plus the delivery fee as if it settles ITM.
    Charging delivery on EVERY leg overstates (a spread has at most one
    ITM leg at expiry when the other expires worthless) — deliberate."""
    return taker_fee_usd(premium_coin, index_usd, contracts) + delivery_fee_usd(
        premium_coin, index_usd, contracts
    )
