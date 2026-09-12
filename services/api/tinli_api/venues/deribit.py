"""Deribit public API v2 adapter — option chain + index, no auth.

Recon (verified live 2026-09-12, notes in docs/VENUES.md):
- GET /public/get_book_summary_by_currency?currency=BTC&kind=option — one
  call returns every listed option: bid_price / ask_price in COIN (null
  when the side is empty), mark_iv in PERCENT (48.81), underlying_price in
  USD (the expiry's futures/synthetic forward). No sizes.
- GET /public/get_index_price?index_name=btc_usd — index_price in USD.
- Instrument names encode expiry/strike/type: BTC-13SEP26-77000-C. Every
  option expires 08:00 UTC on its date. contract_size is 1 coin.
Prices cross into Decimal via str() of the JSON float — the venue's own
shortest representation, never a float multiplication.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from tinli_crypto import OptionQuote

from tinli_api.venues.client import get_json

BASE = "https://www.deribit.com/api/v2/public"
EXPIRY_HOUR_UTC = 8
HUNDRED = Decimal("100")

Coin = Literal["BTC", "ETH"]


def _dec(v) -> Decimal | None:
    if v is None:
        return None
    d = Decimal(str(v))
    return None if d == 0 else d


def parse_instrument(name: str) -> tuple[str, datetime, Decimal, Literal["call", "put"]]:
    coin, date, strike, kind = name.split("-")
    expiry = datetime.strptime(date, "%d%b%y").replace(hour=EXPIRY_HOUR_UTC, tzinfo=UTC)
    return coin, expiry, Decimal(strike), "call" if kind == "C" else "put"


def parse_summaries(raw: list[dict]) -> list[OptionQuote]:
    out: list[OptionQuote] = []
    for s in raw:
        name = s["instrument_name"]
        _, expiry, strike, kind = parse_instrument(name)
        iv = s.get("mark_iv")
        out.append(
            OptionQuote(
                instrument=name,
                strike=strike,
                expiry=expiry,
                option_type=kind,
                bid_coin=_dec(s.get("bid_price")),
                ask_coin=_dec(s.get("ask_price")),
                mark_iv=(Decimal(str(iv)) / HUNDRED) if iv is not None else None,
                underlying_price=_dec(s.get("underlying_price")),
            )
        )
    return out


def get_book_summaries(coin: Coin) -> list[dict]:
    raw = get_json(f"{BASE}/get_book_summary_by_currency", params={"currency": coin, "kind": "option"})
    return raw["result"]


def get_index(coin: Coin) -> dict:
    return get_json(f"{BASE}/get_index_price", params={"index_name": f"{coin.lower()}_usd"})


def parse_index(raw: dict) -> Decimal:
    return Decimal(str(raw["result"]["index_price"]))
