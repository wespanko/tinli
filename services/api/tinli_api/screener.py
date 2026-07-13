"""Shared divergence computation — used by /v1/divergence and the snapshot job."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from tinli_divergence import DivergenceItem, compute_pair, sort_items
from tinli_schema import Orderbook, PairMapping

from tinli_api.datasource import DataSource, load_pairs


def compute_all(source: DataSource) -> list[DivergenceItem]:
    """One DivergenceItem per mapped pair, sorted; a failing leg yields an
    empty book (null edges), never a crash — a resolved/delisted market must
    not take down the screener or the recorder."""

    def one(pair: PairMapping) -> DivergenceItem:
        try:
            k_book = source.orderbook(pair, "kalshi")
            pm_book = source.orderbook(pair, "polymarket")
        except Exception:
            empty = {"bids": [], "asks": [], "fetched_at": datetime.now(UTC)}
            k_book = Orderbook(market_id=f"kalshi:{pair.kalshi_ticker}", venue="kalshi", **empty)
            pm_book = Orderbook(
                market_id=f"polymarket:{pair.pm_condition_id}", venue="polymarket", **empty
            )
        return compute_pair(
            pair, k_book, pm_book, fetched_at=max(k_book.fetched_at, pm_book.fetched_at)
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        items = list(pool.map(one, load_pairs()))
    return sort_items(items)
