import typing as t
from datetime import datetime

from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import BetAmount, Currency
from prediction_market_agent_tooling.markets.polymarket.api import (
    get_polymarket_binary_markets,
)
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketMarketWithPrices,
)
from prediction_market_agent_tooling.markets.polymarket.data_models_web import (
    POLYMARKET_BASE_URL,
)


class PolymarketAgentMarket(AgentMarket):
    """
    Polymarket's market class that can be used by agents to make predictions.
    """

    currency: t.ClassVar[Currency] = Currency.USDC
    base_url: t.ClassVar[str] = POLYMARKET_BASE_URL

    @staticmethod
    def from_data_model(model: PolymarketMarketWithPrices) -> "PolymarketAgentMarket":
        return PolymarketAgentMarket(
            id=model.id,
            question=model.question,
            outcomes=[x.outcome for x in model.tokens],
            resolution=model.resolution,
            current_p_yes=model.p_yes,
            created_time=None,
            close_time=model.end_date_iso,
            url=model.url,
            volume=None,
        )

    def get_tiny_bet_amount(self) -> BetAmount:
        raise NotImplementedError("TODO: Implement to allow betting on Polymarket.")

    def place_bet(self, outcome: bool, amount: BetAmount) -> None:
        raise NotImplementedError("TODO: Implement to allow betting on Polymarket.")

    @staticmethod
    def get_binary_markets(
        limit: int,
        sort_by: SortBy = SortBy.NONE,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[datetime] = None,
        excluded_questions: set[str] | None = None,
    ) -> t.Sequence["PolymarketAgentMarket"]:
        if sort_by != SortBy.NONE:
            raise ValueError(f"Unsuported sort_by {sort_by} for Polymarket.")

        if created_after is not None:
            raise ValueError(f"Unsuported created_after for Polymarket.")

        closed: bool | None
        if filter_by == FilterBy.OPEN:
            closed = False
        elif filter_by == FilterBy.RESOLVED:
            closed = True
        elif filter_by == FilterBy.NONE:
            closed = None
        else:
            raise ValueError(f"Unknown filter_by: {filter_by}")

        return [
            PolymarketAgentMarket.from_data_model(m)
            for m in get_polymarket_binary_markets(
                limit=limit,
                closed=closed,
                excluded_questions=excluded_questions,
            )
        ]
