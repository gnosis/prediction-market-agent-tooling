import typing as t

from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from datetime import datetime
from prediction_market_agent_tooling.markets.data_models import Currency
from prediction_market_agent_tooling.markets.polymarket.api import (
    get_polymarket_binary_markets,
)
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketMarket,
)


class PolymarketAgentMarket(AgentMarket):
    """
    Polymarket's market class that can be used by agents to make predictions.
    """

    currency: t.ClassVar[Currency] = Currency.USDC

    @staticmethod
    def from_data_model(model: PolymarketMarket) -> "PolymarketAgentMarket":
        return PolymarketAgentMarket(
            id=model.id,
            question=model.question,
            outcomes=[x.outcome for x in model.tokens],
            resolution=model.resolution,
            created_time=model.createdTime,
            p_yes=Probability(model.probability),
        )

    @staticmethod
    def get_binary_markets(
        limit: int,
        sort_by: SortBy = SortBy.NONE,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[datetime] = None,
    ) -> list["AgentMarket"]:
        if sort_by != SortBy.NONE:
            raise ValueError(f"Unsuported sort_by {sort_by} for Polymarket.")

        closed: bool | None
        if filter_by == FilterBy.OPEN:
            closed = False
        elif filter_by == FilterBy.RESOLVED:
            closed = True
        else:
            raise ValueError(f"Unknown filter_by: {filter_by}")

        return [
            PolymarketAgentMarket.from_data_model(m)
            for m in get_polymarket_binary_markets(
                limit=limit,
                closed=closed,
                created_after=created_after,
            )
        ]
