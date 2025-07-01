import typing as t

from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    OutcomeStr,
    Probability,
)
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    MarketFees,
    SortBy,
)
from prediction_market_agent_tooling.markets.polymarket.api import (
    PolymarketOrderByEnum,
    get_polymarkets_with_pagination,
)
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketGammaResponseDataItem,
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
    def from_data_model(
        model: PolymarketGammaResponseDataItem,
    ) -> "PolymarketAgentMarket":
        # If len(model.markets) > 0, this denotes a categorical market.

        outcomes = model.markets[0].outcomes_list
        outcome_prices = model.markets[0].outcome_prices
        if not outcome_prices:
            # We give random prices
            outcome_prices = [0.5, 0.5]
        probabilities = {o: Probability(op) for o, op in zip(outcomes, outcome_prices)}

        return PolymarketAgentMarket(
            id=model.id,
            question=model.title,
            description=model.description,
            outcomes=outcomes,
            resolution=None,  # We don't fetch resolution properties
            created_time=model.startDate,
            close_time=model.endDate,
            url=model.url,
            volume=CollateralToken(model.volume),
            outcome_token_pool=None,
            probabilities=probabilities,
        )

    def get_tiny_bet_amount(self) -> CollateralToken:
        raise NotImplementedError("TODO: Implement to allow betting on Polymarket.")

    def place_bet(self, outcome: OutcomeStr, amount: USD) -> str:
        raise NotImplementedError("TODO: Implement to allow betting on Polymarket.")

    @staticmethod
    def get_markets(
        limit: int,
        sort_by: SortBy = SortBy.NONE,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[DatetimeUTC] = None,
        excluded_questions: set[str] | None = None,
        fetch_categorical_markets: bool = False,
    ) -> t.Sequence["PolymarketAgentMarket"]:
        closed: bool | None
        active: bool | None
        if filter_by == FilterBy.OPEN:
            active = True
            closed = False
        elif filter_by == FilterBy.RESOLVED:
            active = False
            closed = True
        elif filter_by == FilterBy.NONE:
            active = None
            closed = None
        else:
            raise ValueError(f"Unknown filter_by: {filter_by}")

        ascending: bool = False  # default value
        match sort_by:
            case SortBy.NEWEST:
                order_by = PolymarketOrderByEnum.START_DATE
            case SortBy.CLOSING_SOONEST:
                ascending = True
                order_by = PolymarketOrderByEnum.END_DATE
            case SortBy.HIGHEST_LIQUIDITY:
                order_by = PolymarketOrderByEnum.LIQUIDITY
            case SortBy.NONE:
                order_by = PolymarketOrderByEnum.VOLUME_24HR
            case _:
                raise ValueError(f"Unknown sort_by: {sort_by}")

        markets = get_polymarkets_with_pagination(
            limit=limit,
            closed=closed,
            active=active,
            order_by=order_by,
            ascending=ascending,
            created_after=created_after,
            excluded_questions=excluded_questions,
            only_binary=not fetch_categorical_markets,
        )

        return [PolymarketAgentMarket.from_data_model(m) for m in markets]
