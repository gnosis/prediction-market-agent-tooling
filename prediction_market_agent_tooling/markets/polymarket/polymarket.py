import typing as t
from collections import defaultdict
from datetime import timedelta

from cowdao_cowpy.common.chains import Chain
from web3 import Web3
from web3.constants import HASH_ZERO

from prediction_market_agent_tooling.config import APIKeys, RPCConfig
from prediction_market_agent_tooling.gtypes import (
    POL,
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
    ProcessedMarket,
    QuestionType,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import (
    Bet,
    ExistingPosition,
    Resolution,
    ResolvedBet,
)
from prediction_market_agent_tooling.markets.polymarket.api import (
    PolymarketOrderByEnum,
    get_gamma_event_by_condition_id,
    get_gamma_event_by_slug,
    get_last_trade_price_from_clob,
    get_polymarkets_with_pagination,
    get_trades_for_market,
    get_user_positions,
    get_user_trades,
)
from prediction_market_agent_tooling.markets.polymarket.clob_manager import ClobManager
from prediction_market_agent_tooling.markets.polymarket.constants import (
    POLYMARKET_BASE_URL,
    POLYMARKET_MIN_LIQUIDITY_USD,
    POLYMARKET_TINY_BET_AMOUNT,
)
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    POLYMARKET_FALSE_OUTCOME,
    POLYMARKET_TRUE_OUTCOME,
    PolymarketGammaResponseDataItem,
    PolymarketPositionResponse,
    PolymarketSideEnum,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
    USDCeContract,
    WPOLContract,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    ConditionSubgraphModel,
    PolymarketSubgraphHandler,
)
from prediction_market_agent_tooling.tools.custom_exceptions import OutOfFundsError
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.tokens.auto_deposit import (
    auto_deposit_collateral_token,
)
from prediction_market_agent_tooling.tools.tokens.usd import (
    get_token_in_usd,
    get_usd_in_token,
)
from prediction_market_agent_tooling.tools.utils import check_not_none, utcnow


class PolymarketAgentMarket(AgentMarket):
    """
    Polymarket's market class that can be used by agents to make predictions.
    """

    base_url: t.ClassVar[str] = POLYMARKET_BASE_URL

    fees: MarketFees
    event_id: str
    condition_id: HexBytes
    liquidity_usd: USD
    token_ids: list[int]
    closed_flag_from_polymarket: bool
    active_flag_from_polymarket: bool

    @staticmethod
    def collateral_token_address() -> ChecksumAddress:
        return USDCeContract().address

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
                f"Only binary markets are supported. Got payout numerators: {condition_model.payoutNumerators} for condition_id {condition_id.to_0x_hex()}"
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
        trading_fee_rate: float,
        condition_id: HexBytes | None = None,
    ) -> t.Optional["PolymarketAgentMarket"]:
        if condition_id is not None:
            target_market = next(
                (m for m in model.markets if m.conditionId == condition_id), None
            )
            if target_market is None:
                logger.warning(
                    f"condition_id {condition_id.to_0x_hex()} not found in event {model.id}"
                )
                return None
        else:
            target_market = model.markets[0]

        outcomes = target_market.outcomes_list
        outcome_prices = target_market.outcome_prices
        if not outcome_prices:
            logger.info(f"Market has no outcome prices. Skipping. {model=}")
            return None

        probabilities = {o: Probability(op) for o, op in zip(outcomes, outcome_prices)}

        cid = target_market.conditionId
        resolution = PolymarketAgentMarket.build_resolution_from_condition(
            condition_id=cid,
            condition_model_dict=condition_model_dict,
            outcomes=outcomes,
        )

        # https://docs.polymarket.com/trading/fees
        fees = MarketFees(
            bet_proportion=0,
            absolute=0,
            trading_fee_rate=trading_fee_rate,
        )
        question = model.title
        if len(model.markets) > 1 and target_market.question:
            question = target_market.question

        return PolymarketAgentMarket(
            id=cid.to_0x_hex(),
            event_id=model.id,
            condition_id=cid,
            question=question,
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
            liquidity_usd=(
                USD(model.liquidity) if model.liquidity is not None else USD(0)
            ),
            fees=fees,
            token_ids=target_market.token_ids,
        )

    @staticmethod
    def from_data_model_all(
        model: PolymarketGammaResponseDataItem,
        condition_model_dict: dict[HexBytes, ConditionSubgraphModel],
        trading_fee_rate: float,
    ) -> list["PolymarketAgentMarket"]:
        """Convert all inner markets of a Gamma event into PolymarketAgentMarkets."""
        markets_list = check_not_none(model.markets)
        results = []
        for inner in markets_list:
            market = PolymarketAgentMarket.from_data_model(
                model,
                condition_model_dict,
                condition_id=inner.conditionId,
                trading_fee_rate=trading_fee_rate,
            )
            if market is not None:
                results.append(market)
        return results

    def get_tiny_bet_amount(self) -> CollateralToken:
        return CollateralToken(POLYMARKET_TINY_BET_AMOUNT.value)

    def get_token_in_usd(self, x: CollateralToken) -> USD:
        return get_token_in_usd(x, self.collateral_token_address())

    def get_usd_in_token(self, x: USD) -> CollateralToken:
        return get_usd_in_token(x, self.collateral_token_address())

    @staticmethod
    def get_trade_balance(api_keys: APIKeys, web3: Web3 | None = None) -> USD:
        usdc_balance_wei = USDCeContract().balanceOf(
            for_address=api_keys.public_key, web3=web3
        )
        return USD(usdc_balance_wei.value * 1e-6)

    def get_liquidity(self, web3: Web3 | None = None) -> CollateralToken:
        return CollateralToken(self.liquidity_usd.value)

    def place_bet(
        self,
        outcome: OutcomeStr,
        amount: USD,
        auto_deposit: bool = True,
        web3: Web3 | None = None,
        api_keys: APIKeys | None = None,
    ) -> str:
        api_keys = api_keys if api_keys is not None else APIKeys()
        web3 = web3 or RPCConfig().get_polygon_web3()

        if auto_deposit:
            need_usdce_wei = Wei(int(amount.value * 1e6))
            auto_deposit_collateral_token(
                collateral_token_contract=USDCeContract(),
                collateral_amount_wei_or_usd=need_usdce_wei,
                api_keys=api_keys,
                web3=web3,
                surplus=0,
                chain=Chain.POLYGON,
                keeping_erc20_token=WPOLContract(),
            )

        clob_manager = ClobManager(api_keys)
        token_id = self.get_token_id_for_outcome(outcome)
        created_order = clob_manager.place_buy_market_order(
            token_id=token_id, usdc_amount=amount
        )
        if not created_order.success:
            raise ValueError(f"Error creating order: {created_order}")
        return created_order.transactionsHashes[0].to_0x_hex()

    @staticmethod
    def _fetch_gamma_markets_with_conditions_and_fees(
        limit: int,
        sort_by: SortBy = SortBy.NONE,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[DatetimeUTC] = None,
        excluded_questions: set[str] | None = None,
        only_binary: bool = True,
    ) -> tuple[
        list[PolymarketGammaResponseDataItem],
        dict[HexBytes, ConditionSubgraphModel],
        dict[str, float],
    ]:
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
                ascending = False
            case SortBy.CLOSING_SOONEST:
                ascending = True
                order_by = PolymarketOrderByEnum.END_DATE
            case SortBy.HIGHEST_LIQUIDITY:
                order_by = PolymarketOrderByEnum.LIQUIDITY
            case SortBy.LOWEST_LIQUIDITY:
                order_by = PolymarketOrderByEnum.LIQUIDITY
                ascending = True
            case SortBy.NONE:
                order_by = PolymarketOrderByEnum.VOLUME_24HR
            case _:
                raise ValueError(f"Unknown sort_by: {sort_by}")

        # closed markets also have property active=True, hence ignoring active.
        gamma_items = get_polymarkets_with_pagination(
            limit=limit,
            closed=closed,
            order_by=order_by,
            ascending=ascending,
            created_after=created_after,
            excluded_questions=excluded_questions,
            only_binary=only_binary,
        )

        all_condition_ids: set[HexBytes] = set()
        for market in gamma_items:
            for inner in market.markets:
                all_condition_ids.add(inner.conditionId)

        condition_models = PolymarketSubgraphHandler().get_conditions(
            condition_ids=list(all_condition_ids)
        )
        condition_dict = {c.id: c for c in condition_models}

        gamma_id_to_trading_fee = {
            # Fee is dependent only on market category, so we can get it just for one market/token.
            item.id: ClobManager().get_token_fee_rate(item.markets[0].token_ids[0])
            for item in gamma_items
        }

        return gamma_items, condition_dict, gamma_id_to_trading_fee

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
        gamma_items, condition_dict, trading_fees = (
            PolymarketAgentMarket._fetch_gamma_markets_with_conditions_and_fees(
                limit=limit,
                sort_by=sort_by,
                filter_by=filter_by,
                created_after=created_after,
                excluded_questions=excluded_questions,
                only_binary=question_type is not QuestionType.CATEGORICAL,
            )
        )

        result_markets: list[PolymarketAgentMarket] = []
        for m in gamma_items:
            result_markets.extend(
                PolymarketAgentMarket.from_data_model_all(
                    m,
                    condition_dict,
                    trading_fee_rate=trading_fees[m.id],
                )
            )

        return result_markets

    def ensure_min_native_balance(
        self,
        min_required_balance: xDai,
        multiplier: float = 3.0,
        web3: Web3 | None = None,
    ) -> None:
        """Ensure the wallet has enough POL for gas on Polygon.

        If POL is low, unwraps WPOL → POL. Same pattern as Seer's
        send_keeping_token_to_eoa_xdai which unwraps wxDAI → xDAI.
        """
        api_keys = APIKeys()
        web3 = web3 or RPCConfig().get_polygon_web3()

        # min_required_balance is typed as xDai in base class, but here
        # it represents POL. Both are 18-decimal native tokens.
        min_required = POL(min_required_balance.value)
        pol_balance = POL(web3.eth.get_balance(api_keys.public_key) / 1e18)

        if pol_balance >= min_required:
            return

        need = POL((min_required.value - pol_balance.value) * multiplier)
        need_wei = need.as_wei

        wpol = WPOLContract()
        wpol_balance = wpol.balanceOf(api_keys.public_key, web3=web3)

        if wpol_balance >= need_wei:
            logger.info(f"Unwrapping {need} WPOL → POL for gas.")
            wpol.withdraw(api_keys=api_keys, amount_wei=need_wei, web3=web3)
            return

        raise OutOfFundsError(
            f"Not enough POL/WPOL for gas: "
            f"need {need} POL, "
            f"have {pol_balance} POL, "
            f"{wpol_balance.as_token} WPOL."
        )

    @staticmethod
    def redeem_winnings(api_keys: APIKeys, web3: Web3 | None = None) -> None:
        web3 = web3 or RPCConfig().get_polygon_web3()
        user_id = api_keys.bet_from_address
        conditional_token_contract = PolymarketConditionalTokenContract()
        positions = PolymarketSubgraphHandler().get_market_positions_from_user(user_id)
        for pos in positions:
            if (
                pos.market.condition.resolutionTimestamp is None
                or pos.market.condition.payoutNumerators is None
            ):
                continue

            condition_id = pos.market.condition.id
            index_sets = pos.market.condition.index_sets

            redeem_event = conditional_token_contract.redeemPositions(
                api_keys=api_keys,
                collateral_token_address=USDCeContract().address,
                condition_id=condition_id,
                index_sets=index_sets,
                web3=web3,
            )

            logger.info(f"Redeemed {redeem_event=} from condition_id {condition_id=}.")

    @staticmethod
    def verify_operational_balance(api_keys: APIKeys) -> bool:
        """Method for checking if agent has enough funds to pay for gas fees."""
        web3 = RPCConfig().get_polygon_web3()
        pol_balance: Wei = Wei(web3.eth.get_balance(api_keys.public_key))
        return pol_balance > Wei(int(0.001 * 1e18))

    def store_prediction(
        self,
        processed_market: ProcessedMarket | None,
        keys: APIKeys,
        agent_name: str,
    ) -> None:
        pass

    def store_trades(
        self,
        traded_market: ProcessedMarket | None,
        keys: APIKeys,
        agent_name: str,
        web3: Web3 | None = None,
    ) -> None:
        logger.debug("Storing trades deactivated for Polymarket.")
        # Understand how market_id can be represented.
        # Condition_id could work but length doesn't seem to match.

    @classmethod
    def get_user_url(cls, keys: APIKeys) -> str:
        return f"https://polymarket.com/{keys.public_key}"

    @staticmethod
    def get_outcome_str_from_bool(outcome: bool) -> OutcomeStr:
        return OutcomeStr("Yes") if outcome else OutcomeStr("No")

    @staticmethod
    def get_user_balance(user_id: str) -> float:
        usdc_balance_wei = USDCeContract().balanceOf(
            for_address=Web3.to_checksum_address(user_id)
        )
        return usdc_balance_wei.value * 1e-6

    def get_position(
        self, user_id: str, web3: Web3 | None = None
    ) -> ExistingPosition | None:
        """
        Fetches position from the user in a given market.
        """
        positions = get_user_positions(
            user_id=Web3.to_checksum_address(user_id), condition_ids=[self.condition_id]
        )
        if not positions:
            return None

        amounts_ot = {i: OutcomeToken(0) for i in self.outcomes}
        amounts_potential = {i: USD(0) for i in self.outcomes}
        amounts_current = {i: USD(0) for i in self.outcomes}

        for p in positions:
            if p.conditionId != self.condition_id.to_0x_hex():
                continue

            amounts_potential[OutcomeStr(p.outcome)] = USD(p.size)
            amounts_ot[OutcomeStr(p.outcome)] = p.size_as_outcome_token
            amounts_current[OutcomeStr(p.outcome)] = p.current_value_usd

        return ExistingPosition(
            amounts_potential=amounts_potential,
            amounts_ot=amounts_ot,
            market_id=self.id,
            amounts_current=amounts_current,
        )

    @classmethod
    def get_positions(
        cls,
        user_id: str,
        liquid_only: bool = False,
        larger_than: OutcomeToken = OutcomeToken(0),
    ) -> t.Sequence[ExistingPosition]:
        all_pos = get_user_positions(
            user_id=Web3.to_checksum_address(user_id), condition_ids=None
        )
        if not all_pos:
            return []

        # Group positions by conditionId
        positions_by_condition: dict[str, list[PolymarketPositionResponse]] = (
            defaultdict(list)
        )
        for p in all_pos:
            positions_by_condition[p.conditionId].append(p)

        # Collect unique event slugs, mapping slug -> condition_ids
        slug_to_conditions: dict[str, list[str]] = defaultdict(list)
        for cid, pos_list in positions_by_condition.items():
            slug_to_conditions[pos_list[0].eventSlug].append(cid)

        # Fetch conditions from subgraph for resolution data
        all_condition_ids = [HexBytes(cid) for cid in positions_by_condition.keys()]
        conditions = PolymarketSubgraphHandler().get_conditions(all_condition_ids)
        condition_dict = {c.id: c for c in conditions}

        # Fetch markets from Gamma API by slug, resolve each condition_id
        markets_by_condition: dict[str, "PolymarketAgentMarket"] = {}
        for slug, condition_ids_for_slug in slug_to_conditions.items():
            event = get_gamma_event_by_slug(slug)
            for cid_str in condition_ids_for_slug:
                cid_bytes = HexBytes(cid_str)
                market = cls.from_data_model(
                    event,
                    condition_dict,
                    condition_id=cid_bytes,
                    trading_fee_rate=0,  # No need for fees in this method, so we dont' fetch it.
                )
                if market is not None:
                    markets_by_condition[cid_bytes.to_0x_hex()] = market

        # Build ExistingPosition for each condition group
        positions: list[ExistingPosition] = []
        for cid, pos_list in positions_by_condition.items():
            market = markets_by_condition.get(cid)

            if liquid_only and (market is None or not market.can_be_traded()):
                continue

            amounts_ot = {
                OutcomeStr(p.outcome): p.size_as_outcome_token for p in pos_list
            }
            amounts_current = {
                OutcomeStr(p.outcome): p.current_value_usd for p in pos_list
            }
            amounts_potential = {OutcomeStr(p.outcome): USD(p.size) for p in pos_list}

            if all(ot <= larger_than for ot in amounts_ot.values()):
                continue

            market_id = market.id if market is not None else pos_list[0].eventSlug

            positions.append(
                ExistingPosition(
                    market_id=market_id,
                    amounts_ot=amounts_ot,
                    amounts_current=amounts_current,
                    amounts_potential=amounts_potential,
                )
            )

        return positions

    def get_token_balance(
        self, user_id: str, outcome: OutcomeStr, web3: Web3 | None = None
    ) -> OutcomeToken:
        outcome_index = self.get_outcome_index(outcome)
        index_set = 1 << outcome_index
        ctf = PolymarketConditionalTokenContract()
        collection_id = ctf.getCollectionId(
            HexBytes(HASH_ZERO), self.condition_id, index_set, web3=web3
        )
        position_id = ctf.getPositionId(
            self.collateral_token_address(), collection_id, web3=web3
        )
        balance = ctf.balanceOf(
            Web3.to_checksum_address(user_id), position_id, web3=web3
        )
        return balance.as_outcome_token

    def get_sell_value_of_outcome_token(
        self, outcome: OutcomeStr, amount: OutcomeToken
    ) -> CollateralToken:
        if amount == OutcomeToken(0):
            return CollateralToken(0)
        token_id = self.get_token_id_for_outcome(outcome)
        sell_price = ClobManager(APIKeys()).get_token_price(
            token_id=token_id, side=PolymarketSideEnum.SELL
        )
        return CollateralToken(sell_price.value * amount.value)

    def liquidate_existing_positions(
        self,
        outcome: OutcomeStr,
        api_keys: APIKeys | None = None,
    ) -> None:
        api_keys = api_keys if api_keys is not None else APIKeys()
        better_address = api_keys.bet_from_address
        larger_than = self.get_liquidatable_amount()
        prev_positions = self.get_positions(
            user_id=better_address, liquid_only=True, larger_than=larger_than
        )
        for prev_position in prev_positions:
            if prev_position.market_id != self.id:
                continue
            for position_outcome, token_amount in prev_position.amounts_ot.items():
                if position_outcome != outcome:
                    self.sell_tokens(
                        outcome=position_outcome,
                        amount=token_amount,
                        api_keys=api_keys,
                    )

    @staticmethod
    def get_binary_market(id: str) -> "PolymarketAgentMarket":
        cid = HexBytes(id)
        model = get_gamma_event_by_condition_id(cid)
        conditions = PolymarketSubgraphHandler().get_conditions([cid])
        condition_dict = {c.id: c for c in conditions}
        trading_fee_rate = ClobManager().get_token_fee_rate(
            # Fee is dependent only on market category, so we can get it just for one market/token.
            model.markets[0].token_ids[0]
        )
        market = PolymarketAgentMarket.from_data_model(
            model,
            condition_dict,
            condition_id=cid,
            trading_fee_rate=trading_fee_rate,
        )
        return check_not_none(market)

    def can_be_traded(self) -> bool:
        return (
            self.active_flag_from_polymarket
            and not self.closed_flag_from_polymarket
            and self.liquidity_usd > POLYMARKET_MIN_LIQUIDITY_USD
        )

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
            token_id=token_id, side=PolymarketSideEnum.BUY
        )
        if not price:
            raise ValueError(
                f"Could not get price for outcome {outcome_str} with token_id {token_id}"
            )

        # we work with floats since USD and Collateral are the same on Polymarket
        buy_token_amount = bet_amount.value / price.value
        logger.info(f"Buy token amount: {buy_token_amount=}")
        return OutcomeToken(buy_token_amount)

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
        logger.info(f"Selling {amount=} from {outcome=}")
        clob_manager = ClobManager(api_keys=api_keys or APIKeys())
        token_id = self.get_token_id_for_outcome(outcome)
        token_shares: OutcomeToken
        if isinstance(amount, OutcomeToken):
            token_shares = amount
        elif isinstance(amount, USD):
            token_price = clob_manager.get_token_price(
                token_id=token_id, side=PolymarketSideEnum.SELL
            )
            # We expect that our order sizes don't move the price too much.
            token_shares = OutcomeToken(amount.value / token_price.value)
        else:
            raise ValueError(f"Unsupported amount type {type(amount)}")

        created_order = clob_manager.place_sell_market_order(
            token_id=token_id, token_shares=token_shares
        )
        if not created_order.success:
            raise ValueError(f"Error creating order: {created_order}")

        return created_order.transactionsHashes[0].to_0x_hex()

    def get_last_trade_p_yes(self) -> Probability | None:
        yes_token_id = self.get_token_id_for_outcome(
            OutcomeStr(POLYMARKET_TRUE_OUTCOME)
        )
        price = get_last_trade_price_from_clob(token_id=yes_token_id)
        if price is None:
            return None
        return Probability(price)

    def get_last_trade_p_no(self) -> Probability | None:
        p_yes = self.get_last_trade_p_yes()
        if p_yes is None:
            return None
        return Probability(1.0 - p_yes)

    @staticmethod
    def get_bets_made_since(
        better_address: ChecksumAddress, start_time: DatetimeUTC
    ) -> list[Bet]:
        trades = get_user_trades(user_address=better_address, after=start_time)
        bets = [t.to_polymarket_bet().to_bet() for t in trades]
        bets.sort(key=lambda b: b.created_time)
        return bets

    @staticmethod
    def get_resolved_bets_made_since(
        better_address: ChecksumAddress,
        start_time: DatetimeUTC,
        end_time: DatetimeUTC | None,
    ) -> list[ResolvedBet]:
        trades = get_user_trades(
            user_address=better_address, after=start_time, before=end_time
        )
        if not trades:
            return []

        unique_condition_ids = list(set(t.conditionId for t in trades))
        conditions = PolymarketSubgraphHandler().get_conditions(unique_condition_ids)
        condition_dict = {c.id: c for c in conditions}

        binary_outcomes = [
            OutcomeStr(POLYMARKET_TRUE_OUTCOME),
            OutcomeStr(POLYMARKET_FALSE_OUTCOME),
        ]

        resolved_bets: list[ResolvedBet] = []
        for trade in trades:
            resolution = PolymarketAgentMarket.build_resolution_from_condition(
                condition_id=trade.conditionId,
                condition_model_dict=condition_dict,
                outcomes=binary_outcomes,
            )
            if resolution is None or resolution.outcome is None:
                continue

            condition = condition_dict[trade.conditionId]
            resolved_time = DatetimeUTC.to_datetime_utc(
                check_not_none(condition.resolutionTimestamp)
            )
            resolved_bets.append(
                trade.to_polymarket_bet().to_generic_resolved_bet(
                    resolution, resolved_time
                )
            )

        return resolved_bets

    def have_bet_on_market_since(self, keys: APIKeys, since: timedelta) -> bool:
        trades = get_trades_for_market(
            market=self.condition_id, user=keys.bet_from_address
        )
        cutoff = utcnow() - since
        return any(t.timestamp >= cutoff for t in trades)

    def get_most_recent_trade_datetime(self, user_id: str) -> DatetimeUTC | None:
        trades = get_trades_for_market(
            market=self.condition_id,
            user=Web3.to_checksum_address(user_id),
        )
        if not trades:
            return None
        return max(t.timestamp for t in trades)
