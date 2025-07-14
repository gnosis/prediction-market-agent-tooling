import typing as t

from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    HexBytes,
    OutcomeStr,
    Probability,
)
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    MarketFees,
    MarketType,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import Resolution
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
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    ConditionSubgraphModel,
    PolymarketSubgraphHandler,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


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
    def build_resolution_from_condition(
        condition_id: HexBytes,
        condition_model_dict: dict[HexBytes, ConditionSubgraphModel],
        outcomes: list[OutcomeStr],
    ) -> Resolution | None:
        condition_model = condition_model_dict.get(condition_id)
        if (
            not condition_model
            or condition_model.resolutionTimestamp is None
            or not condition_model.payoutNumerators
            or not condition_model.payoutDenominator
        ):
            return None

        # Currently we only support binary markets, hence we throw an error if we get something else.
        payout_numerator_indices_gt_0 = [
            idx
            for idx, value in enumerate(condition_model.payoutNumerators)
            if value > 0
        ]
        # For a binary market, there should be exactly one payout numerator greater than 0.
        if len(payout_numerator_indices_gt_0) != 1:
            raise ValueError(
                f"Only binary markets are supported. Got payout numerators: {condition_model.payoutNumerators}"
            )

        # we return the only payout numerator greater than 0 as resolution
        resolved_outcome = outcomes[payout_numerator_indices_gt_0[0]]
        return Resolution.from_answer(resolved_outcome)

    @staticmethod
    def from_data_model(
        model: PolymarketGammaResponseDataItem,
        condition_model_dict: dict[HexBytes, ConditionSubgraphModel],
    ) -> "PolymarketAgentMarket":
        # If len(model.markets) > 0, this denotes a categorical market.

        outcomes = model.markets[0].outcomes_list
        outcome_prices = model.markets[0].outcome_prices
        if not outcome_prices:
            # We give random prices
            outcome_prices = [0.5, 0.5]
        probabilities = {o: Probability(op) for o, op in zip(outcomes, outcome_prices)}

        resolution = PolymarketAgentMarket.build_resolution_from_condition(
            condition_id=model.markets[0].conditionId,
            condition_model_dict=condition_model_dict,
            outcomes=outcomes,
        )

        return PolymarketAgentMarket(
            id=model.id,
            question=model.title,
            description=model.description,
            outcomes=outcomes,
            resolution=resolution,
            created_time=model.startDate,
            close_time=model.endDate,
            url=model.url,
            volume=CollateralToken(model.volume) if model.volume else None,
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
        market_type: MarketType = MarketType.ALL,
        include_conditional_markets: bool = False,
    ) -> t.Sequence["PolymarketAgentMarket"]:
        closed: bool | None

        if filter_by == FilterBy.OPEN:
            closed = False
        elif filter_by == FilterBy.RESOLVED:
            closed = True
        elif filter_by == FilterBy.NONE:
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

        # closed markets also have property active=True, hence ignoring active.
        markets = get_polymarkets_with_pagination(
            limit=limit,
            closed=closed,
            order_by=order_by,
            ascending=ascending,
            created_after=created_after,
            excluded_questions=excluded_questions,
            only_binary=not fetch_categorical_markets,
        )

        condition_models = PolymarketSubgraphHandler().get_conditions(
            condition_ids=[market.markets[0].conditionId for market in markets]
        )
        condition_models_dict = {c.id: c for c in condition_models}

        return [
            PolymarketAgentMarket.from_data_model(m, condition_models_dict)
            for m in markets
        ]
