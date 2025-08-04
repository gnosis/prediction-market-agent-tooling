import typing as t

import cachetools
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    USD,
    ChecksumAddress,
    CollateralToken,
    HexBytes,
    OutcomeStr,
    OutcomeToken,
    Probability,
    Wei,
    xDai,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    ConditionalFilterType,
    FilterBy,
    MarketFees,
    QuestionType,
    SortBy,
    ProcessedMarket,
    ProcessedTradedMarket,
)
from prediction_market_agent_tooling.markets.data_models import (
    ExistingPosition,
    Resolution,
)
from prediction_market_agent_tooling.markets.polymarket.api import (
    PolymarketOrderByEnum,
    get_polymarkets_with_pagination,
    get_user_positions,
)
from prediction_market_agent_tooling.markets.polymarket.clob_manager import (
    ClobManager,
    PolymarketPriceSideEnum,
)
from prediction_market_agent_tooling.markets.polymarket.constants import (
    POLYMARKET_TINY_BET_AMOUNT,
)
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    POLYMARKET_BASE_URL,
    PolymarketGammaResponseDataItem,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    USDCContract,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    ConditionSubgraphModel,
    PolymarketSubgraphHandler,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.tokens.usd import get_token_in_usd
from prediction_market_agent_tooling.tools.utils import check_not_none

shared_cache: cachetools.TTLCache[t.Hashable, t.Any] = cachetools.TTLCache(
    maxsize=256, ttl=10 * 60
)


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
    condition_id: HexBytes
    liquidity_usd: USD
    token_ids: list[int]
    closed_flag_from_polymarket: bool
    active_flag_from_polymarket: bool

    @staticmethod
    def collateral_token_address() -> ChecksumAddress:
        return USDCContract().address

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
            # These cases involve multi-categorical resolution (to be implemented https://github.com/gnosis/prediction-market-agent-tooling/issues/770)
            logger.warning(
                f"Only binary markets are supported. Got payout numerators: {condition_model.payoutNumerators} for condition_id {condition_id.hex()}"
            )
            return Resolution(outcome=None, invalid=False)

        # we return the only payout numerator greater than 0 as resolution
        resolved_outcome = outcomes[payout_numerator_indices_gt_0[0]]
        return Resolution.from_answer(resolved_outcome)

    def get_token_id_for_outcome(self, outcome: OutcomeStr) -> int:
        outcome_idx = self.outcomes.index(outcome)
        return self.token_ids[outcome_idx]

    @staticmethod
    def from_data_model(
        model: PolymarketGammaResponseDataItem,
        condition_model_dict: dict[HexBytes, ConditionSubgraphModel],
    ) -> t.Optional["PolymarketAgentMarket"]:
        # If len(model.markets) > 0, this denotes a categorical market.
        markets = check_not_none(model.markets)
        outcomes = markets[0].outcomes_list
        outcome_prices = markets[0].outcome_prices
        if not outcome_prices:
            # We give random prices
            # ToDo - Filter out markets without prices, maybe use clob_client.get_price
            outcome_prices = [0.5, 0.5]
        probabilities = {o: Probability(op) for o, op in zip(outcomes, outcome_prices)}

        condition_id = markets[0].conditionId
        resolution = PolymarketAgentMarket.build_resolution_from_condition(
            condition_id=condition_id,
            condition_model_dict=condition_model_dict,
            outcomes=outcomes,
        )

        return PolymarketAgentMarket(
            id=model.id,
            condition_id=condition_id,
            question=model.title,
            description=model.description,
            outcomes=outcomes,
            resolution=resolution,
            created_time=model.startDate,
            close_time=model.endDate,
            closed_flag_from_polymarket=model.closed,
            active_flag_from_polymarket=model.active,
            url=model.url,
            volume=CollateralToken(model.volume) if model.volume else None,
            outcome_token_pool=None,
            probabilities=probabilities,
            liquidity_usd=USD(model.liquidity),
            token_ids=markets[0].token_ids,
        )

    def get_tiny_bet_amount(self) -> CollateralToken:
        return CollateralToken(POLYMARKET_TINY_BET_AMOUNT.value)

    def get_token_in_usd(self, x: CollateralToken) -> USD:
        return get_token_in_usd(x, self.collateral_token_address())

    @staticmethod
    def get_trade_balance(api_keys: APIKeys, web3: Web3 | None = None) -> USD:
        usdc_balance_wei = USDCContract().balanceOf(
            for_address=api_keys.public_key, web3=web3
        )
        return USD(usdc_balance_wei.value * 1e-6)

    def get_liquidity(self, web3: Web3 | None = None) -> CollateralToken:
        return CollateralToken(self.liquidity_usd.value)

    def place_bet(self, outcome: OutcomeStr, amount: USD) -> str:
        raise NotImplementedError("TODO: Implement to allow betting on Polymarket.")

    @staticmethod
    def get_markets(
        limit: int,
        sort_by: SortBy = SortBy.NONE,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[DatetimeUTC] = None,
        excluded_questions: set[str] | None = None,
        question_type: QuestionType = QuestionType.ALL,
        conditional_filter_type: ConditionalFilterType = ConditionalFilterType.ONLY_NOT_CONDITIONAL,
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
                order_by = PolymarketOrderByEnum.END_DATE
                ascending = True
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
            only_binary=question_type is not QuestionType.CATEGORICAL,
        )

        condition_models = PolymarketSubgraphHandler().get_conditions(
            condition_ids=[
                market.markets[0].conditionId
                for market in markets
                if market.markets is not None
            ]
        )
        condition_models_dict = {c.id: c for c in condition_models}

        markets = [
            market
            for m in markets
            if (
                market := PolymarketAgentMarket.from_data_model(
                    m, condition_models_dict
                )
            )
            is not None
        ]
        return markets

    def ensure_min_native_balance(
        self,
        min_required_balance: xDai,
        multiplier: float = 3.0,
        web3: Web3 | None = None,
    ) -> None:
        # ToDo - add decimals property to some contracts.
        balance_collateral = USDCContract().balanceOf(
            for_address=APIKeys().public_key, web3=web3
        )
        # USDC has 6 decimals, xDAI has 18. We convert from Wei into atomic units.
        balance_collateral_atomic = CollateralToken(balance_collateral / 1e6)
        if balance_collateral_atomic < min_required_balance.as_token:
            raise EnvironmentError(
                f"USDC balance {balance_collateral_atomic} < {min_required_balance.as_token=}"
            )

    @staticmethod
    def redeem_winnings(api_keys: APIKeys) -> None:
        # ToDo - get user positions (check Polymarket API or subgraph)
        # conditional_token_contract = PolymarketConditionalTokenContract()
        # redeem_event = conditional_token_contract.redeemPositions(
        #     api_keys=api_keys,
        #     collateral_token_address=user_position.position.collateral_token_contract_address_checksummed,
        #     condition_id=condition_id,
        #     index_sets=user_position.position.indexSets,
        #     web3=web3,
        # )
        pass

    @staticmethod
    def verify_operational_balance(api_keys: APIKeys) -> bool:
        # USDC is the only collateral token supported by Polymarket
        return USDCContract().balanceOf(for_address=api_keys.public_key) > Wei(
            0.001 * 10**6
        )

    def store_prediction(
        self,
        processed_market: ProcessedMarket | None,
        keys: APIKeys,
        agent_name: str,
    ) -> None:
        pass

    def store_trades(
        self,
        traded_market: ProcessedTradedMarket | None,
        keys: APIKeys,
        agent_name: str,
        web3: Web3 | None = None,
    ) -> None:
        logger.info("Storing trades deactivated for Polymarket.")
        # Understand how market_id can be represented. Condition_id could work but length doesn't seem to match.
        pass

    def get_user_url(cls, keys: APIKeys) -> str:
        return f"https://polymarket.com/{keys.public_key}"

    def get_position(
        self, user_id: str, web3: Web3 | None = None
    ) -> ExistingPosition | None:
        """
        Fetches position from the user in a given market.
        """
        # ToDo - make sure logic works with example market
        positions = get_user_positions(
            user_id=Web3.to_checksum_address(user_id), condition_ids=[self.condition_id]
        )
        if not positions:
            return None

        amounts_ot = {i: OutcomeToken(0) for i in self.outcomes}
        amounts_potential = {i: USD(0) for i in self.outcomes}
        amounts_current = {i: USD(0) for i in self.outcomes}

        for p in positions:
            if p.conditionId != self.condition_id.hex():
                continue

            amounts_potential[OutcomeStr(p.outcome)] = USD(p.size)
            amounts_ot[OutcomeStr(p.outcome)] = OutcomeToken(p.size * 1e6)
            amounts_current[OutcomeStr(p.outcome)] = USD(p.currentValue)

        return ExistingPosition(
            amounts_potential=amounts_potential,
            amounts_ot=amounts_ot,
            market_id=self.id,
            amounts_current=amounts_current,
        )

    def can_be_traded(self) -> bool:
        return self.active_flag_from_polymarket and not self.closed_flag_from_polymarket

    def get_buy_token_amount(
        self, bet_amount: USD | CollateralToken, outcome_str: OutcomeStr
    ) -> OutcomeToken:
        """Returns number of outcome tokens returned for a given bet expressed in collateral units."""

        if outcome_str not in self.outcomes:
            raise ValueError(
                f"Outcome {outcome_str} not found in market outcomes {self.outcomes}"
            )

        token_id = self.get_token_id_for_outcome(outcome_str)

        price = ClobManager(APIKeys()).get_token_price(
            token_id=token_id, side=PolymarketPriceSideEnum.BUY
        )
        if not price:
            raise ValueError(
                f"Could not get price for outcome {outcome_str} with token_id {token_id}"
            )

        # we work with floats since USD and Collateral are the same on Polymarket
        buy_token_amount = bet_amount.value / price.value
        return OutcomeToken(buy_token_amount)

    def buy_tokens(self, outcome: OutcomeStr, amount: USD) -> str:
        clob_manager = ClobManager(APIKeys())
        token_id = self.get_token_id_for_outcome(outcome)

        created_order = clob_manager.place_buy_market_order(
            token_id=token_id, usdc_amount=amount.value
        )
        if not created_order.success:
            raise ValueError(f"Error creating order: {created_order}")

        return created_order.transactionsHashes[0].hex()

    def sell_tokens(
        self,
        outcome: OutcomeStr,
        amount: USD | OutcomeToken,
        api_keys: APIKeys | None = None,
    ) -> str:
        """
        Polymarket's API expect shares to be sold. 1 share == 1 outcome token / 1e6.
        The number of outcome tokens matches the `balanceOf` of the conditionalTokens contract.
        In comparison, the number of shares match the position.size from the user position.
        """

        clob_manager = ClobManager(api_keys=api_keys or APIKeys())
        token_id = self.get_token_id_for_outcome(outcome)
        token_shares: float
        if isinstance(amount, OutcomeToken):
            token_shares = amount.value / 1e6
        elif isinstance(amount, USD):
            token_price = clob_manager.get_token_price(
                token_id=token_id, side=PolymarketPriceSideEnum.SELL
            )
            token_shares = amount.value / token_price.value
        else:
            raise ValueError(
                f"Amount must be of type OutcomeToken or USD, got {type(amount)}"
            )

        token_id = self.get_token_id_for_outcome(outcome)
        created_order = clob_manager.place_sell_market_order(
            token_id=token_id, token_shares=token_shares
        )
        if not created_order.success:
            raise ValueError(f"Error creating order: {created_order}")

        return created_order.transactionsHashes[0].hex()
