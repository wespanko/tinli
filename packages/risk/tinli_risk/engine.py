"""Portfolio risk report: marks, exposure, VaR, Kelly.

Marks are top-of-book mids where both sides exist, else the venue's reported
YES price. A NO position's mark is 1 - yes_mark (complement identity). All
P&L deltas are relative to CURRENT MARKS: "what changes from here", not from
entry — entry shows up only in cost basis / unrealized P&L.

Positions whose market_id is not in the feed are UNMARKED: they appear in
the report with null risk fields and are EXCLUDED from every aggregate, and
the assumptions list says so out loud. Silently dropping a position from
VaR would understate risk, which is the one thing this module must not do.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from tinli_schema import Market, Position

from tinli_risk.kelly import half_kelly, kelly_fraction
from tinli_risk.var import EventPnl, max_loss, monte_carlo_var, parametric_var

ZERO = Decimal("0")
ONE = Decimal("1")

BASE_ASSUMPTIONS = [
    "Outcome probabilities are current venue mids (price ~ probability), not independent forecasts.",
    "Events are independent; positions sharing an event_key are perfectly correlated.",
    "VaR horizon is resolution of each event, not a fixed number of days.",
    "Parametric VaR is a normal approximation and is capped at max_loss; "
    "Monte Carlo samples the actual Bernoulli outcomes (seeded, reproducible).",
    "Kelly uses the user's est_prob against the mid, ignoring spread and fees; "
    "sizing guidance only.",
]


class PositionRisk(BaseModel):
    position: Position
    event_id: str | None = Field(description="event_key, or market_id if unmapped; None if unmarked")
    question: str | None
    mark: Decimal | None = Field(description="current mark of the HELD side; None if unmarked")
    market_value: Decimal | None
    cost_basis: Decimal
    unrealized_pnl: Decimal | None
    max_loss: Decimal | None = Field(description="loss from current mark if the event resolves against the side")
    kelly_full: Decimal | None = Field(description="requires est_prob; None otherwise")
    kelly_half: Decimal | None


class EventExposure(BaseModel):
    event_id: str
    prob_yes: Decimal
    delta_if_yes: Decimal
    delta_if_no: Decimal
    net_yes_contracts: Decimal = Field(description="yes minus no contracts across venues; ~0 for a lock")


class RiskReport(BaseModel):
    positions: list[PositionRisk]
    by_event: list[EventExposure]
    total_market_value: Decimal
    total_cost_basis: Decimal = Field(description="marked positions only, like every other aggregate")
    total_unrealized_pnl: Decimal
    max_loss: Decimal
    var_95_parametric: Decimal
    var_95_monte_carlo: Decimal
    mc_draws: int
    mc_seed: int
    unmarked_positions: int
    assumptions: list[str]
    fetched_at: datetime


def yes_mark(m: Market) -> Decimal:
    if m.best_bid is not None and m.best_ask is not None:
        return (m.best_bid + m.best_ask) / 2
    return m.yes_price


def build_report(
    positions: list[Position],
    markets_by_id: dict[str, Market],
    fetched_at: datetime,
    mc_draws: int = 20_000,
    mc_seed: int = 7,
) -> RiskReport:
    rows: list[PositionRisk] = []
    # per event: [prob_yes marks seen, delta_if_yes, delta_if_no, net yes contracts]
    events: dict[str, list] = {}
    unmarked = 0

    for pos in positions:
        market = markets_by_id.get(pos.market_id)
        cost = pos.contracts * pos.entry_price
        if market is None:
            unmarked += 1
            rows.append(
                PositionRisk(
                    position=pos, event_id=None, question=None, mark=None,
                    market_value=None, cost_basis=cost, unrealized_pnl=None,
                    max_loss=None, kelly_full=None, kelly_half=None,
                )
            )
            continue

        m_yes = yes_mark(market)
        mark = m_yes if pos.side == "yes" else ONE - m_yes
        value = pos.contracts * mark
        # settle-against loses the whole current value; settle-for gains the rest
        gain = pos.contracts * (ONE - mark)
        event_id = market.event_key or pos.market_id
        acc = events.setdefault(event_id, [[], ZERO, ZERO, ZERO])
        acc[0].append(m_yes)
        if pos.side == "yes":
            acc[1] += gain
            acc[2] -= value
            acc[3] += pos.contracts
        else:
            acc[1] -= value
            acc[2] += gain
            acc[3] -= pos.contracts

        p_win = None
        if pos.est_prob is not None:
            p_win = pos.est_prob if pos.side == "yes" else ONE - pos.est_prob
        rows.append(
            PositionRisk(
                position=pos,
                event_id=event_id,
                question=market.question,
                mark=mark,
                market_value=value,
                cost_basis=cost,
                unrealized_pnl=value - cost,
                max_loss=value,
                kelly_full=kelly_fraction(mark, p_win) if p_win is not None else None,
                kelly_half=half_kelly(mark, p_win) if p_win is not None else None,
            )
        )

    by_event = []
    event_pnls = []
    for event_id, (marks, d_yes, d_no, net) in events.items():
        # one probability per event: mean of the involved venues' YES mids
        prob = sum(marks, ZERO) / len(marks)
        by_event.append(
            EventExposure(
                event_id=event_id, prob_yes=prob,
                delta_if_yes=d_yes, delta_if_no=d_no, net_yes_contracts=net,
            )
        )
        event_pnls.append(
            EventPnl(event_id=event_id, prob_yes=prob, delta_if_yes=d_yes, delta_if_no=d_no)
        )

    marked = [r for r in rows if r.market_value is not None]
    assumptions = list(BASE_ASSUMPTIONS)
    if unmarked:
        assumptions.append(
            f"{unmarked} position(s) not found in the market feed: shown unmarked and "
            "EXCLUDED from all aggregates and VaR."
        )
    return RiskReport(
        positions=rows,
        by_event=by_event,
        total_market_value=sum((r.market_value for r in marked), ZERO),
        total_cost_basis=sum((r.cost_basis for r in marked), ZERO),
        total_unrealized_pnl=sum((r.unrealized_pnl for r in marked), ZERO),
        max_loss=max_loss(event_pnls),
        var_95_parametric=parametric_var(event_pnls),
        var_95_monte_carlo=monte_carlo_var(event_pnls, draws=mc_draws, seed=mc_seed),
        mc_draws=mc_draws,
        mc_seed=mc_seed,
        unmarked_positions=unmarked,
        assumptions=assumptions,
        fetched_at=fetched_at,
    )
