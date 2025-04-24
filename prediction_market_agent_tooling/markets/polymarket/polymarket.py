import typing as t

from prediction_market_agent_tooling.gtypes import USD, CollateralToken, OutcomeStr
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    MarketFees,
    SortBy,
)
from prediction_market_agent_tooling.markets.polymarket.api import (
    get_polymarket_binary_markets,
)
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketMarketWithPrices,
)
from prediction_market_agent_tooling.markets.polymarket.data_models_web import (
    POLYMARKET_BASE_URL,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


class PolymarketAgentMarket(AgentMarket):
    """
    Polymarket's market class that can be used by agents to make predictions.
    """

    base_url: t.ClassVar[str] = POLYMARKET_BASE_URL

    # Based on https://docs.polymarket.com/#fees, there are currently no fees, except for transactions fees.
    # However they do have `maker_fee_base_rate` and `taker_fee_base_rate`, but impossible to test out our implementation without them actually taking the fees.
    # But then in the new subgraph API, they have `fee: BigInt! (Percentage fee of trades taken by market maker. A 2% fee is represented as 2*10^16)`.
    # TODO: Check out the fees while integrating the subgraph API or if we implement placing of bets on Polymarket.
    fees: MarketFees = MarketFees.get_zero_fees()

    @staticmethod
    def from_data_model(model: PolymarketMarketWithPrices) -> "PolymarketAgentMarket":
        return PolymarketAgentMarket(
            id=model.id,
            question=model.question,
            description=model.description,
            outcomes=[x.outcome for x in model.tokens],
            resolution=model.resolution,
            created_time=None,
            close_time=model.end_date_iso,
            url=model.url,
            volume=None,
            outcome_token_pool=None,
            probability_map={},  # ToDo - Implement when fixing Polymarket
        )

    def get_tiny_bet_amount(self) -> CollateralToken:
        raise NotImplementedError("TODO: Implement to allow betting on Polymarket.")

    def place_bet(self, outcome: OutcomeStr, amount: USD) -> str:
        raise NotImplementedError("TODO: Implement to allow betting on Polymarket.")

    @staticmethod
    def get_binary_markets(
        limit: int,
        sort_by: SortBy = SortBy.NONE,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[DatetimeUTC] = None,
        excluded_questions: set[str] | None = None,
        fetch_categorical_markets: bool = False,
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
