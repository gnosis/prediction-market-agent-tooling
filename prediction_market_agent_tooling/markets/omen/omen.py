import typing as t
from collections import defaultdict
from datetime import timedelta

import tenacity
from tqdm import tqdm
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    USD,
    ChecksumAddress,
    CollateralToken,
    HexAddress,
    HexStr,
    OutcomeStr,
    OutcomeToken,
    OutcomeWei,
    Probability,
    Wei,
    xDai,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    MarketFees,
    ProcessedMarket,
    ProcessedTradedMarket,
    SortBy,
)
from prediction_market_agent_tooling.markets.blockchain_utils import store_trades
from prediction_market_agent_tooling.markets.data_models import (
    Bet,
    ExistingPosition,
    ResolvedBet,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
    PRESAGIO_BASE_URL,
    Condition,
    ConditionPreparationEvent,
    CreatedMarket,
    OmenBet,
    OmenMarket,
    OmenUserPosition,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OMEN_DEFAULT_MARKET_FEE_PERC,
    REALITY_DEFAULT_FINALIZATION_TIMEOUT,
    Arbitrator,
    OmenConditionalTokenContract,
    OmenFixedProductMarketMakerContract,
    OmenFixedProductMarketMakerFactoryContract,
    OmenOracleContract,
    OmenRealitioContract,
    WrappedxDaiContract,
    build_parent_collection_id,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.contract import (
    init_collateral_token_contract,
    to_gnosis_chain_contract,
)
from prediction_market_agent_tooling.tools.custom_exceptions import OutOfFundsError
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.tokens.auto_deposit import (
    auto_deposit_collateral_token,
)
from prediction_market_agent_tooling.tools.tokens.auto_withdraw import (
    auto_withdraw_collateral_token,
)
from prediction_market_agent_tooling.tools.tokens.main_token import KEEPING_ERC20_TOKEN
from prediction_market_agent_tooling.tools.tokens.usd import (
    get_token_in_usd,
    get_usd_in_token,
    get_xdai_in_usd,
)
from prediction_market_agent_tooling.tools.utils import (
    DatetimeUTC,
    calculate_sell_amount_in_collateral,
    check_not_none,
)
from prediction_market_agent_tooling.tools.web3_utils import get_receipt_block_timestamp

OMEN_DEFAULT_REALITIO_BOND_VALUE = xDai(0.01)
# Too low value would work with the Omen contract, but causes CoW orders (when buying the specific market's tokens) to fail.
OMEN_TINY_BET_AMOUNT = USD(0.01)


class OmenAgentMarket(AgentMarket):
    """
    Omen's market class that can be used by agents to make predictions.
    """

    base_url: t.ClassVar[str] = PRESAGIO_BASE_URL
    creator: HexAddress

    collateral_token_contract_address_checksummed: ChecksumAddress
    market_maker_contract_address_checksummed: ChecksumAddress
    condition: Condition
    finalized_time: DatetimeUTC | None
    created_time: DatetimeUTC
    close_time: DatetimeUTC

    _binary_market_p_yes_history: list[Probability] | None = None
    description: str | None = (
        None  # Omen markets don't have a description, so just default to None.
    )

    @property
    def yes_index(self) -> int:
        return self.outcomes.index(OMEN_TRUE_OUTCOME)

    @property
    def no_index(self) -> int:
        return self.outcomes.index(OMEN_FALSE_OUTCOME)

    def get_p_yes_history_cached(self) -> list[Probability]:
        if self._binary_market_p_yes_history is None:
            self._binary_market_p_yes_history = get_binary_market_p_yes_history(self)
        return self._binary_market_p_yes_history

    def get_last_trade_p_yes(self) -> Probability | None:
        """On Omen, probablities converge after the resolution, so we need to get market's predicted probability from the trade history."""
        return (
            self.get_p_yes_history_cached()[-1]
            if self.get_p_yes_history_cached()
            else None
        )

    def get_last_trade_p_no(self) -> Probability | None:
        """On Omen, probablities converge after the resolution, so we need to get market's predicted probability from the trade history."""
        last_trade_p_yes = self.get_last_trade_p_yes()
        return (
            Probability(1.0 - last_trade_p_yes)
            if last_trade_p_yes is not None
            else None
        )

    def get_liquidity_in_wei(self, web3: Web3 | None = None) -> Wei:
        return self.get_contract().totalSupply(web3)

    def get_liquidity(self, web3: Web3 | None = None) -> CollateralToken:
        return self.get_liquidity_in_wei(web3).as_token

    def get_tiny_bet_amount(self) -> CollateralToken:
        return self.get_in_token(OMEN_TINY_BET_AMOUNT)

    def get_token_in_usd(self, x: CollateralToken) -> USD:
        return get_token_in_usd(x, self.collateral_token_contract_address_checksummed)

    def get_usd_in_token(self, x: USD) -> CollateralToken:
        return get_usd_in_token(x, self.collateral_token_contract_address_checksummed)

    def liquidate_existing_positions(
        self,
        bet_outcome: OutcomeStr,
        web3: Web3 | None = None,
        api_keys: APIKeys | None = None,
        larger_than: OutcomeToken | None = None,
    ) -> None:
        """
        Liquidates all previously existing positions.

        """
        api_keys = api_keys if api_keys is not None else APIKeys()
        better_address = api_keys.bet_from_address
        larger_than = (
            larger_than if larger_than is not None else self.get_liquidatable_amount()
        )
        prev_positions_for_market = self.get_positions(
            user_id=better_address, liquid_only=True, larger_than=larger_than
        )

        for prev_position in prev_positions_for_market:
            for position_outcome, token_amount in prev_position.amounts_ot.items():
                if position_outcome != bet_outcome:
                    self.sell_tokens(
                        outcome=position_outcome,
                        amount=token_amount,
                        auto_withdraw=True,
                        web3=web3,
                        api_keys=api_keys,
                    )

    def place_bet(
        self,
        outcome: OutcomeStr,
        amount: USD,
        auto_deposit: bool = True,
        web3: Web3 | None = None,
        api_keys: APIKeys | None = None,
    ) -> str:
        if not self.can_be_traded():
            raise ValueError(
                f"Market {self.id} is not open for trading. Cannot place bet."
            )
        return binary_omen_buy_outcome_tx(
            api_keys=api_keys if api_keys is not None else APIKeys(),
            amount=amount,
            market=self,
            outcome=outcome,
            auto_deposit=auto_deposit,
            web3=web3,
        )

    def buy_tokens(
        self,
        outcome: OutcomeStr,
        amount: USD,
        web3: Web3 | None = None,
        api_keys: APIKeys | None = None,
    ) -> str:
        return self.place_bet(
            outcome=outcome,
            amount=amount,
            web3=web3,
            api_keys=api_keys,
        )

    def get_sell_value_of_outcome_token(
        self, outcome: OutcomeStr, amount: OutcomeToken, web3: Web3 | None = None
    ) -> CollateralToken:
        """
        Market can have as collateral token GNO for example.
        When you place bet, you buy shares with GNO. For example, you get 10 shares for 1 GNO.
        When selling, you need to provide the amount in GNO, which is cumbersome because you know how much shares you have, but you don't have the price of the shares in GNO.
        Use this to convert how much collateral token (GNO in our example) to sell, to get the amount of shares you want to sell.
        """

        pool_balance = get_conditional_tokens_balance_for_market(
            self, self.market_maker_contract_address_checksummed, web3=web3
        )
        outcome_idx = self.index_set_to_outcome_index(self.get_index_set(outcome))
        collateral = calculate_sell_amount_in_collateral(
            shares_to_sell=amount,
            outcome_index=outcome_idx,
            pool_balances=[x.as_outcome_token for x in pool_balance.values()],
            fees=self.fees,
        )

        return collateral

    def sell_tokens(
        self,
        outcome: OutcomeStr,
        amount: USD | OutcomeToken,
        auto_withdraw: bool = True,
        api_keys: APIKeys | None = None,
        web3: Web3 | None = None,
    ) -> str:
        if not self.can_be_traded():
            raise ValueError(
                f"Market {self.id} is not open for trading. Cannot sell tokens."
            )
        return binary_omen_sell_outcome_tx(
            amount=amount,
            api_keys=api_keys if api_keys is not None else APIKeys(),
            market=self,
            outcome=outcome,
            auto_withdraw=auto_withdraw,
            web3=web3,
        )

    def was_any_bet_outcome_correct(
        self, resolved_omen_bets: t.List[OmenBet]
    ) -> bool | None:
        resolved_bets_for_market = [
            bet
            for bet in resolved_omen_bets
            if bet.fpmm.id == self.id and bet.fpmm.is_resolved
        ]

        # If there were no bets for this market, we conservatively say that
        # this method was called incorrectly, hence we raise an Error.
        if not resolved_bets_for_market:
            raise ValueError(f"No resolved bets provided for market {self.id}")

        if not resolved_bets_for_market[0].fpmm.has_valid_answer:
            # We return None if the market was resolved as invalid, as we were neither right or wrong.
            return None

        # We iterate through bets since agent could have placed bets on multiple outcomes.
        # If one of the bets was correct, we return true since there is a redeemable amount to be retrieved.
        for bet in resolved_bets_for_market:
            # Like Olas, we assert correctness by matching index
            if bet.outcomeIndex == check_not_none(
                bet.fpmm.question.outcome_index,
                "Shouldn't be None if the market is resolved",
            ):
                return True

        return False

    def market_redeemable_by(self, user: ChecksumAddress) -> bool:
        """
        Will return true if given user placed a bet on this market and that bet has a balance.
        If the user never placed a bet on this market, this correctly return False.
        """
        positions = OmenSubgraphHandler().get_positions(condition_id=self.condition.id)
        user_positions = OmenSubgraphHandler().get_user_positions(
            better_address=user,
            position_id_in=[p.id for p in positions],
            # After redeem, this will became zero.
            total_balance_bigger_than=OutcomeWei(0),
        )
        return len(user_positions) > 0

    def redeem_positions(
        self,
        api_keys: APIKeys,
    ) -> None:
        for_public_key = api_keys.bet_from_address
        market_is_redeemable = self.market_redeemable_by(user=for_public_key)
        if not market_is_redeemable:
            logger.debug(
                f"Position on market {self.id} was already redeemed or no bets were placed at all by {for_public_key=}."
            )
            return None

        omen_redeem_full_position_tx(api_keys=api_keys, market=self)

    @staticmethod
    def from_created_market(model: "CreatedMarket") -> "OmenAgentMarket":
        return OmenAgentMarket.from_data_model(OmenMarket.from_created_market(model))

    @staticmethod
    def from_data_model(model: OmenMarket) -> "OmenAgentMarket":
        return OmenAgentMarket(
            id=model.id,
            question=model.title,
            creator=model.creator,
            outcomes=model.outcomes,
            collateral_token_contract_address_checksummed=model.collateral_token_contract_address_checksummed,
            market_maker_contract_address_checksummed=model.market_maker_contract_address_checksummed,
            resolution=model.get_resolution_enum(),
            created_time=model.creation_datetime,
            finalized_time=model.finalized_datetime,
            condition=model.condition,
            url=model.url,
            volume=model.collateralVolume.as_token,
            close_time=model.close_time,
            fees=MarketFees(
                bet_proportion=(
                    model.fee.as_token.value if model.fee is not None else 0.0
                ),
                absolute=0,
            ),
            outcome_token_pool={
                model.outcomes[i]: model.outcomeTokenAmounts[i].as_outcome_token
                for i in range(len(model.outcomes))
            },
            probabilities=AgentMarket.build_probability_map(
                outcome_token_amounts=model.outcomeTokenAmounts,
                outcomes=list(model.outcomes),
            ),
        )

    @staticmethod
    def get_markets(
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[DatetimeUTC] = None,
        excluded_questions: set[str] | None = None,
        fetch_categorical_markets: bool = False,
    ) -> t.Sequence["OmenAgentMarket"]:
        return [
            OmenAgentMarket.from_data_model(m)
            for m in OmenSubgraphHandler().get_omen_markets_simple(
                limit=limit,
                sort_by=sort_by,
                filter_by=filter_by,
                created_after=created_after,
                excluded_questions=excluded_questions,
                include_categorical_markets=fetch_categorical_markets,
            )
        ]

    @staticmethod
    def get_binary_market(id: str) -> "OmenAgentMarket":
        return OmenAgentMarket.from_data_model(
            OmenSubgraphHandler().get_omen_market_by_market_id(
                market_id=HexAddress(HexStr(id))
            )
        )

    @staticmethod
    def redeem_winnings(api_keys: APIKeys) -> None:
        redeem_from_all_user_positions(api_keys)

    @staticmethod
    def get_trade_balance(api_keys: APIKeys, web3: Web3 | None = None) -> USD:
        native_usd = get_xdai_in_usd(
            get_balances(api_keys.bet_from_address, web3=web3).xdai
        )
        keeping_usd = get_token_in_usd(
            KEEPING_ERC20_TOKEN.balance_of_in_tokens(
                api_keys.bet_from_address, web3=web3
            ),
            KEEPING_ERC20_TOKEN.address,
        )
        return keeping_usd + native_usd

    @staticmethod
    def verify_operational_balance(api_keys: APIKeys) -> bool:
        return get_balances(
            # Use `public_key`, not `bet_from_address` because transaction costs are paid from the EOA wallet.
            api_keys.public_key,
        ).xdai > xDai(0.001)

    def store_prediction(
        self, processed_market: ProcessedMarket | None, keys: APIKeys, agent_name: str
    ) -> None:
        """On Omen, we have to store predictions along with trades, see `store_trades`."""

    def store_trades(
        self,
        traded_market: ProcessedTradedMarket | None,
        keys: APIKeys,
        agent_name: str,
        web3: Web3 | None = None,
    ) -> None:
        return store_trades(
            market_id=self.id,
            traded_market=traded_market,
            keys=keys,
            agent_name=agent_name,
        )

    @staticmethod
    def get_bets_made_since(
        better_address: ChecksumAddress, start_time: DatetimeUTC
    ) -> list[Bet]:
        bets = OmenSubgraphHandler().get_bets(
            better_address=better_address, start_time=start_time
        )
        bets.sort(key=lambda x: x.creation_datetime)
        return [b.to_bet() for b in bets]

    @staticmethod
    def get_resolved_bets_made_since(
        better_address: ChecksumAddress,
        start_time: DatetimeUTC,
        end_time: DatetimeUTC | None,
        market_resolved_before: DatetimeUTC | None = None,
        market_resolved_after: DatetimeUTC | None = None,
    ) -> list[ResolvedBet]:
        subgraph_handler = OmenSubgraphHandler()
        bets = subgraph_handler.get_resolved_bets_with_valid_answer(
            better_address=better_address,
            start_time=start_time,
            end_time=end_time,
            market_id=None,
            market_resolved_before=market_resolved_before,
            market_resolved_after=market_resolved_after,
        )
        generic_bets = [b.to_generic_resolved_bet() for b in bets]
        return generic_bets

    def get_contract(
        self,
    ) -> OmenFixedProductMarketMakerContract:
        return OmenFixedProductMarketMakerContract(
            address=self.market_maker_contract_address_checksummed,
        )

    def get_index_set(self, outcome: OutcomeStr) -> int:
        return self.get_outcome_index(outcome) + 1

    def index_set_to_outcome_index(cls, index_set: int) -> int:
        return index_set - 1

    def index_set_to_outcome_str(cls, index_set: int) -> OutcomeStr:
        return OutcomeStr(
            cls.get_outcome_str(cls.index_set_to_outcome_index(index_set))
        )

    @staticmethod
    def get_outcome_str_from_bool(outcome: bool) -> OutcomeStr:
        return (
            OutcomeStr(OMEN_TRUE_OUTCOME) if outcome else OutcomeStr(OMEN_FALSE_OUTCOME)
        )

    def get_token_balance(
        self, user_id: str, outcome: OutcomeStr, web3: Web3 | None = None
    ) -> OutcomeToken:
        index_set = self.get_index_set(outcome)
        balances = get_conditional_tokens_balance_for_market(
            self, Web3.to_checksum_address(user_id), web3=web3
        )
        return balances[index_set].as_outcome_token

    def get_position(self, user_id: str) -> ExistingPosition | None:
        liquidatable_amount = self.get_liquidatable_amount()
        existing_positions = self.get_positions(
            user_id=user_id,
            liquid_only=True,
            larger_than=liquidatable_amount,
        )
        existing_position = next(
            iter([i for i in existing_positions if i.market_id == self.id]), None
        )
        return existing_position

    @classmethod
    def get_positions(
        cls,
        user_id: str,
        liquid_only: bool = False,
        larger_than: OutcomeToken = OutcomeToken(0),
    ) -> t.Sequence[ExistingPosition]:
        sgh = OmenSubgraphHandler()
        omen_positions = sgh.get_user_positions(
            better_address=Web3.to_checksum_address(user_id),
            total_balance_bigger_than=larger_than.as_outcome_wei,
        )

        # Sort positions and corresponding markets by condition_id
        omen_positions_dict: dict[HexBytes, list[OmenUserPosition]] = defaultdict(list)

        for omen_position in omen_positions:
            omen_positions_dict[omen_position.position.condition_id].append(
                omen_position
            )

        # We include categorical markets below simply because we are already filtering on condition_ids.
        omen_markets: dict[HexBytes, OmenMarket] = {
            m.condition.id: m
            for m in sgh.get_omen_markets(
                limit=None,
                condition_id_in=list(omen_positions_dict.keys()),
                include_categorical_markets=True,
            )
        }

        if len(omen_markets) != len(omen_positions_dict):
            missing_conditions_ids = set(
                omen_position.position.condition_id for omen_position in omen_positions
            ) - set(market.condition.id for market in omen_markets.values())
            raise ValueError(
                f"Number of condition ids for markets {len(omen_markets)} and positions {len(omen_positions_dict)} are not equal. "
                f"Missing condition ids: {missing_conditions_ids}"
            )

        positions = []
        for condition_id, omen_positions in tqdm(
            omen_positions_dict.items(), mininterval=3
        ):
            market = cls.from_data_model(omen_markets[condition_id])

            # Skip markets that cannot be traded if `liquid_only`` is True.
            if liquid_only and not market.can_be_traded():
                continue

            amounts_ot: dict[OutcomeStr, OutcomeToken] = {}

            for omen_position in omen_positions:
                outecome_str = market.index_set_to_outcome_str(
                    omen_position.position.index_set
                )

                # Validate that outcomes are unique for a given condition_id.
                if outecome_str in amounts_ot:
                    raise ValueError(
                        f"Outcome {outecome_str} already exists in {amounts_ot=}"
                    )

                amounts_ot[outecome_str] = omen_position.totalBalance.as_outcome_token

            amounts_current = {
                k: market.get_token_in_usd(
                    # If the market is not open for trading anymore, then current value is equal to potential value.
                    market.get_sell_value_of_outcome_token(k, v)
                    if market.can_be_traded()
                    else v.as_token
                )
                for k, v in amounts_ot.items()
            }
            amounts_potential = {
                k: market.get_token_in_usd(v.as_token) for k, v in amounts_ot.items()
            }
            positions.append(
                ExistingPosition(
                    market_id=market.id,
                    amounts_current=amounts_current,
                    amounts_potential=amounts_potential,
                    amounts_ot=amounts_ot,
                )
            )

        return positions

    @classmethod
    def get_user_url(cls, keys: APIKeys) -> str:
        return get_omen_user_url(keys.bet_from_address)

    def get_buy_token_amount(
        self, bet_amount: USD | CollateralToken, outcome: OutcomeStr
    ) -> OutcomeToken:
        """
        Note: this is only valid if the market instance's token pool is
        up-to-date with the smart contract.
        """
        outcome_token_pool = check_not_none(self.outcome_token_pool)
        amount = get_buy_outcome_token_amount(
            investment_amount=self.get_in_token(bet_amount),
            outcome_index=self.get_outcome_index(outcome),
            pool_balances=[outcome_token_pool[x] for x in self.outcomes],
            fees=self.fees,
        )
        return amount

    def _get_buy_token_amount_from_smart_contract(
        self, bet_amount: USD, outcome: OutcomeStr
    ) -> OutcomeToken:
        bet_amount_in_tokens = get_usd_in_token(
            bet_amount, self.collateral_token_contract_address_checksummed
        )

        received_token_amount_wei = self.get_contract().calcBuyAmount(
            investment_amount=bet_amount_in_tokens.as_wei,
            outcome_index=self.get_outcome_index(outcome),
        )
        received_token_amount = received_token_amount_wei.as_outcome_token
        return received_token_amount

    @staticmethod
    def get_user_balance(user_id: str) -> float:
        return float(get_balances(Web3.to_checksum_address(user_id)).total)

    @staticmethod
    def get_user_id(api_keys: APIKeys) -> str:
        return api_keys.bet_from_address

    def get_most_recent_trade_datetime(self, user_id: str) -> DatetimeUTC | None:
        sgh = OmenSubgraphHandler()
        trades = sgh.get_trades(
            sort_by_field=sgh.trades_subgraph.FpmmTrade.creationTimestamp,
            sort_direction="desc",
            limit=1,
            better_address=Web3.to_checksum_address(user_id),
            market_id=Web3.to_checksum_address(self.id),
        )
        if not trades:
            return None

        return trades[0].creation_datetime


def get_omen_user_url(address: ChecksumAddress) -> str:
    return f"https://gnosisscan.io/address/{address}"


@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_fixed(1),
    after=lambda x: logger.debug(f"omen_buy_outcome_tx failed, {x.attempt_number=}."),
)
def omen_buy_outcome_tx(
    api_keys: APIKeys,
    amount: USD | CollateralToken,
    market: OmenAgentMarket,
    outcome: OutcomeStr,
    auto_deposit: bool,
    web3: Web3 | None = None,
    slippage: float = 0.01,
) -> str:
    """
    Bets the given amount for the given outcome in the given market.
    """
    market_contract: OmenFixedProductMarketMakerContract = market.get_contract()
    collateral_token_contract = market_contract.get_collateral_token_contract(web3)

    amount_token = market.get_in_token(amount)
    amount_wei = amount_token.as_wei

    logger.info(
        f"Buying asked {amount.value=} {amount.symbol}, converted to {amount_token.value=} {amount_token.symbol} for {outcome=} in market {market.url=}."
    )

    # Get the index of the outcome we want to buy.
    outcome_index: int = market.get_outcome_index(outcome)

    # Calculate the amount of shares we will get for the given investment amount.
    expected_shares = market_contract.calcBuyAmount(
        amount_wei, outcome_index, web3=web3
    )
    # Allow small slippage.
    expected_shares = expected_shares.without_fraction(slippage)
    # Approve the market maker to withdraw our collateral token.
    collateral_token_contract.approve(
        api_keys=api_keys,
        for_address=market_contract.address,
        amount_wei=amount_wei,
        web3=web3,
    )

    if auto_deposit:
        auto_deposit_collateral_token(
            collateral_token_contract, amount_wei, api_keys, web3
        )

    # Buy shares using the deposited xDai in the collateral token.
    tx_receipt = market_contract.buy(
        api_keys=api_keys,
        amount_wei=amount_wei,
        outcome_index=outcome_index,
        min_outcome_tokens_to_buy=expected_shares,
        web3=web3,
    )

    return tx_receipt["transactionHash"].hex()


def binary_omen_buy_outcome_tx(
    api_keys: APIKeys,
    amount: USD | CollateralToken,
    market: OmenAgentMarket,
    outcome: OutcomeStr,
    auto_deposit: bool,
    web3: Web3 | None = None,
) -> str:
    return omen_buy_outcome_tx(
        api_keys=api_keys,
        amount=amount,
        market=market,
        outcome=outcome,
        auto_deposit=auto_deposit,
        web3=web3,
    )


def omen_sell_outcome_tx(
    api_keys: APIKeys,
    amount: OutcomeToken | CollateralToken | USD,
    market: OmenAgentMarket,
    outcome: OutcomeStr,
    auto_withdraw: bool,
    web3: Web3 | None = None,
    slippage: float = 0.01,
) -> str:
    """
    Sells the given xDai value of shares corresponding to the given outcome in
    the given market.

    The number of shares sold will depend on the share price at the time of the
    transaction.
    """
    market_contract: OmenFixedProductMarketMakerContract = market.get_contract()
    conditional_token_contract = OmenConditionalTokenContract()
    collateral_token_contract = market_contract.get_collateral_token_contract(web3)

    amount_token = (
        market.get_sell_value_of_outcome_token(outcome, amount, web3)
        if isinstance(amount, OutcomeToken)
        else market.get_in_token(amount)
    )
    amount_wei = amount_token.as_wei

    logger.info(
        f"Selling asked {amount.value=} {amount.symbol}, converted to {amount_wei.as_token.value=} {amount_wei.as_token.symbol} for {outcome=} in market {market.url=}."
    )

    # Verify, that markets uses conditional tokens that we expect.
    if (
        market_contract.conditionalTokens(web3=web3)
        != conditional_token_contract.address
    ):
        raise ValueError(
            f"Market {market.id} uses conditional token that we didn't expect, {market_contract.conditionalTokens()} != {conditional_token_contract.address=}"
        )

    # Get the index of the outcome we want to sell.
    outcome_index: int = market.get_outcome_index(outcome)

    # Calculate the amount of shares we will sell for the given selling amount of collateral.
    max_outcome_tokens_to_sell = market_contract.calcSellAmount(
        amount_wei, outcome_index, web3=web3
    )
    # Allow small slippage.
    max_outcome_tokens_to_sell = max_outcome_tokens_to_sell.with_fraction(slippage)

    # Approve the market maker to move our (all) conditional tokens.
    conditional_token_contract.setApprovalForAll(
        api_keys=api_keys,
        for_address=market_contract.address,
        approve=True,
        web3=web3,
    )
    # Sell the shares.
    tx_receipt = market_contract.sell(
        api_keys,
        amount_wei,
        outcome_index,
        max_outcome_tokens_to_sell,
        web3=web3,
    )
    if auto_withdraw:
        auto_withdraw_collateral_token(
            collateral_token_contract=collateral_token_contract,
            amount_wei=amount_wei,
            api_keys=api_keys,
            web3=web3,
        )

    return tx_receipt["transactionHash"].hex()


def binary_omen_sell_outcome_tx(
    api_keys: APIKeys,
    amount: OutcomeToken | CollateralToken | USD,
    market: OmenAgentMarket,
    outcome: OutcomeStr,
    auto_withdraw: bool,
    web3: Web3 | None = None,
) -> str:
    return omen_sell_outcome_tx(
        api_keys=api_keys,
        amount=amount,
        market=market,
        outcome=outcome,
        auto_withdraw=auto_withdraw,
        web3=web3,
    )


def omen_create_market_tx(
    api_keys: APIKeys,
    initial_funds: USD | CollateralToken,
    question: str,
    closing_time: DatetimeUTC,
    category: str,
    language: str,
    outcomes: t.Sequence[str],
    auto_deposit: bool,
    finalization_timeout: timedelta = REALITY_DEFAULT_FINALIZATION_TIMEOUT,
    fee_perc: float = OMEN_DEFAULT_MARKET_FEE_PERC,
    distribution_hint: list[OutcomeWei] | None = None,
    collateral_token_address: ChecksumAddress = WrappedxDaiContract().address,
    arbitrator: Arbitrator = Arbitrator.KLEROS_31_JURORS_WITH_APPEAL,
    web3: Web3 | None = None,
) -> CreatedMarket:
    """
    Based on omen-exchange TypeScript code: https://github.com/protofire/omen-exchange/blob/b0b9a3e71b415d6becf21fe428e1c4fc0dad2e80/app/src/services/cpk/cpk.ts#L308
    """
    web3 = (
        web3 or OmenFixedProductMarketMakerFactoryContract.get_web3()
    )  # Default to Gnosis web3.
    initial_funds_in_collateral = (
        get_usd_in_token(initial_funds, collateral_token_address)
        if isinstance(initial_funds, USD)
        else initial_funds
    )
    initial_funds_in_collateral_wei = initial_funds_in_collateral.as_wei

    realitio_contract = OmenRealitioContract()
    conditional_token_contract = OmenConditionalTokenContract()
    collateral_token_contract = to_gnosis_chain_contract(
        init_collateral_token_contract(collateral_token_address, web3)
    )
    factory_contract = OmenFixedProductMarketMakerFactoryContract()
    oracle_contract = OmenOracleContract()

    # These checks were originally maded somewhere in the middle of the process, but it's safer to do them right away.
    # Double check that the oracle's realitio address is the same as we are using.
    if oracle_contract.realitio() != realitio_contract.address:
        raise RuntimeError(
            "The oracle's realitio address is not the same as we are using."
        )
    # Double check that the oracle's conditional tokens address is the same as we are using.
    if oracle_contract.conditionalTokens() != conditional_token_contract.address:
        raise RuntimeError(
            "The oracle's conditional tokens address is not the same as we are using."
        )

    if auto_deposit:
        auto_deposit_collateral_token(
            collateral_token_contract,
            initial_funds_in_collateral_wei,
            api_keys=api_keys,
            web3=web3,
        )

    # Create the question on Realitio.
    question_event = realitio_contract.askQuestion(
        api_keys=api_keys,
        question=question,
        category=category,
        outcomes=outcomes,
        language=language,
        arbitrator=arbitrator,
        opening=closing_time,  # The question is opened at the closing time of the market.
        timeout=finalization_timeout,
        web3=web3,
    )

    # Construct the condition id.
    cond_event: ConditionPreparationEvent | None = None
    condition_id = conditional_token_contract.getConditionId(
        question_id=question_event.question_id,
        oracle_address=oracle_contract.address,
        outcomes_slot_count=len(outcomes),
        web3=web3,
    )
    if not conditional_token_contract.does_condition_exists(condition_id, web3=web3):
        cond_event = conditional_token_contract.prepareCondition(
            api_keys=api_keys,
            question_id=question_event.question_id,
            oracle_address=oracle_contract.address,
            outcomes_slot_count=len(outcomes),
            web3=web3,
        )

    # Approve the market maker to withdraw our collateral token.
    collateral_token_contract.approve(
        api_keys=api_keys,
        for_address=factory_contract.address,
        amount_wei=initial_funds_in_collateral_wei,
        web3=web3,
    )

    # Create the market.
    fee = CollateralToken(fee_perc).as_wei
    (
        market_event,
        funding_event,
        receipt_tx,
    ) = factory_contract.create2FixedProductMarketMaker(
        api_keys=api_keys,
        condition_id=condition_id,
        fee=fee,
        distribution_hint=distribution_hint,
        initial_funds_wei=initial_funds_in_collateral_wei,
        collateral_token_address=collateral_token_contract.address,
        web3=web3,
    )

    # Note: In the Omen's Typescript code, there is futher a creation of `stakingRewardsFactoryAddress`,
    # (https://github.com/protofire/omen-exchange/blob/763d9c9d05ebf9edacbc1dbaa561aa5d08813c0f/app/src/services/cpk/fns.ts#L979)
    # but address of stakingRewardsFactoryAddress on xDai/Gnosis is 0x0000000000000000000000000000000000000000,
    # so skipping it here.

    return CreatedMarket(
        market_creation_timestamp=get_receipt_block_timestamp(receipt_tx, web3),
        market_event=market_event,
        funding_event=funding_event,
        condition_id=condition_id,
        question_event=question_event,
        condition_event=cond_event,
        initial_funds=initial_funds_in_collateral_wei,
        fee=fee,
        distribution_hint=distribution_hint,
    )


def omen_fund_market_tx(
    api_keys: APIKeys,
    market: OmenAgentMarket,
    funds: USD | CollateralToken,
    auto_deposit: bool,
    web3: Web3 | None = None,
) -> None:
    funds_in_collateral = market.get_in_token(funds)
    funds_in_collateral_wei = funds_in_collateral.as_wei
    market_contract = market.get_contract()
    collateral_token_contract = market_contract.get_collateral_token_contract(web3=web3)

    collateral_token_contract.approve(
        api_keys=api_keys,
        for_address=market_contract.address,
        amount_wei=funds_in_collateral_wei,
        web3=web3,
    )

    if auto_deposit:
        auto_deposit_collateral_token(
            collateral_token_contract, funds_in_collateral_wei, api_keys, web3
        )

    market_contract.addFunding(api_keys, funds_in_collateral_wei, web3=web3)


def omen_redeem_full_position_tx(
    api_keys: APIKeys,
    market: OmenAgentMarket,
    auto_withdraw: bool = True,
    web3: Web3 | None = None,
) -> None:
    """
    Redeems position from a given Omen market. Note that we check if there is a balance
    to be redeemed before sending the transaction.
    """

    from_address = api_keys.bet_from_address

    market_contract: OmenFixedProductMarketMakerContract = market.get_contract()
    conditional_token_contract = OmenConditionalTokenContract()
    collateral_token_contract = market_contract.get_collateral_token_contract(web3)

    # Verify, that markets uses conditional tokens that we expect.
    if market_contract.conditionalTokens() != conditional_token_contract.address:
        raise ValueError(
            f"Market {market.id} uses conditional token that we didn't expect, {market_contract.conditionalTokens()} != {conditional_token_contract.address=}"
        )

    if not market.is_resolved():
        logger.debug("Cannot redeem winnings if market is not yet resolved. Exiting.")
        return

    amount_per_index = get_conditional_tokens_balance_for_market(
        market, from_address, web3
    )
    amount_wei = sum(amount_per_index.values(), start=OutcomeWei.zero())
    if amount_wei == 0:
        logger.debug("No balance to claim. Exiting.")
        return

    if not conditional_token_contract.is_condition_resolved(market.condition.id):
        logger.debug("Market not yet resolved, not possible to claim")
        return

    redeem_event = conditional_token_contract.redeemPositions(
        api_keys=api_keys,
        collateral_token_address=market.collateral_token_contract_address_checksummed,
        condition_id=market.condition.id,
        index_sets=market.condition.index_sets,
        web3=web3,
    )

    logger.info(
        f"Redeemed {redeem_event.payout.as_token} {collateral_token_contract.symbol_cached(web3=web3)} from market {market.question=} ({market.url})."
    )

    if auto_withdraw:
        auto_withdraw_collateral_token(
            collateral_token_contract=collateral_token_contract,
            amount_wei=redeem_event.payout,
            api_keys=api_keys,
            web3=web3,
        )


def get_conditional_tokens_balance_for_market(
    market: OmenAgentMarket,
    from_address: ChecksumAddress,
    web3: Web3 | None = None,
) -> dict[int, OutcomeWei]:
    """
    We derive the withdrawable balance from the ConditionalTokens contract through CollectionId -> PositionId (which
    also serves as tokenId) -> TokenBalances.
    """
    balance_per_index_set: dict[int, OutcomeWei] = {}
    conditional_token_contract = OmenConditionalTokenContract()
    parent_collection_id = build_parent_collection_id()

    for index_set in market.condition.index_sets:
        collection_id = conditional_token_contract.getCollectionId(
            parent_collection_id, market.condition.id, index_set, web3=web3
        )
        # Note that collection_id is returned as bytes, which is accepted by the contract calls downstream.
        position_id: int = conditional_token_contract.getPositionId(
            market.collateral_token_contract_address_checksummed,
            collection_id,
            web3=web3,
        )
        balance_for_position = conditional_token_contract.balanceOf(
            from_address=from_address, position_id=position_id, web3=web3
        )
        balance_per_index_set[index_set] = balance_for_position

    return balance_per_index_set


def omen_remove_fund_market_tx(
    api_keys: APIKeys,
    market: OmenAgentMarket,
    shares: Wei | None,
    web3: Web3 | None = None,
    auto_withdraw: bool = True,
) -> None:
    """
    Removes funding from a given OmenMarket (moving the funds from the OmenMarket to the
    ConditionalTokens contract), and finally calls the `mergePositions` method which transfers collateralToken from the ConditionalTokens contract to the address corresponding to `from_private_key`.

    Warning: Liquidity removal works on the principle of getting market's shares, not the collateral token itself.
    After we remove funding, using the `mergePositions` we get `min(shares per index)` of collateral token back, but the remaining shares can be converted back only after the market is resolved.
    That can be done using the `redeem_from_all_user_positions` function below.
    """
    from_address = api_keys.bet_from_address
    market_contract = market.get_contract()
    market_collateral_token_contract = market_contract.get_collateral_token_contract(
        web3=web3
    )
    original_balance = market_collateral_token_contract.balanceOf(
        from_address, web3=web3
    )

    total_shares = market_contract.balanceOf(from_address, web3=web3)
    if total_shares == 0:
        logger.info("No shares to remove.")
        return

    if shares is None or shares > total_shares:
        logger.debug(
            f"shares available to claim {total_shares} - defaulting to a total removal."
        )
        shares = total_shares

    market_contract.removeFunding(api_keys=api_keys, remove_funding=shares, web3=web3)

    conditional_tokens = OmenConditionalTokenContract()
    amount_per_index_set = get_conditional_tokens_balance_for_market(
        market, from_address, web3
    )
    # We fetch the minimum balance of outcome token - for ex, in this tx (https://gnosisscan.io/tx/0xc31c4e9bc6a60cf7db9991a40ec2f2a06e3539f8cb8dd81b6af893cef6f40cd7#eventlog) - event #460, this should yield 9804940144070370149. This amount matches what is displayed in the Omen UI. # web3-private-key-ok
    # See similar logic from Olas
    # https://github.com/valory-xyz/market-creator/blob/4bc47f696fb5ecb61c3b7ec8c001ff2ab6c60fcf/packages/valory/skills/market_creation_manager_abci/behaviours.py#L1308
    amount_to_merge = min(amount_per_index_set.values())

    result = conditional_tokens.mergePositions(
        api_keys=api_keys,
        collateral_token_address=market.collateral_token_contract_address_checksummed,
        conditionId=market.condition.id,
        index_sets=market.condition.index_sets,
        amount=amount_to_merge,
        web3=web3,
    )

    new_balance = market_collateral_token_contract.balanceOf(from_address, web3=web3)
    balance_diff = new_balance - original_balance

    logger.debug(f"Result from merge positions {result}")
    logger.info(
        f"Withdrawn {balance_diff.as_token} {market_collateral_token_contract.symbol_cached(web3=web3)} from liquidity at {market.url=}."
    )

    if auto_withdraw:
        auto_withdraw_collateral_token(
            collateral_token_contract=market_collateral_token_contract,
            amount_wei=balance_diff,
            api_keys=api_keys,
            web3=web3,
        )


def redeem_from_all_user_positions(
    api_keys: APIKeys,
    web3: Web3 | None = None,
    auto_withdraw: bool = True,
) -> None:
    """
    Redeems from all user positions where the user didn't redeem yet.
    """
    public_key = api_keys.bet_from_address

    conditional_token_contract = OmenConditionalTokenContract()
    user_positions = OmenSubgraphHandler().get_user_positions(
        public_key,
        # After redeem, this will became zero and we won't re-process it.
        total_balance_bigger_than=OutcomeWei(0),
    )

    for index, user_position in enumerate(user_positions):
        condition_id = user_position.position.condition_id

        if not conditional_token_contract.is_condition_resolved(condition_id):
            logger.info(
                f"[{index + 1} / {len(user_positions)}] Skipping redeem, {user_position.id=} isn't resolved yet."
            )
            continue

        logger.info(
            f"[{index + 1} / {len(user_positions)}] Processing redeem from {user_position.id=}."
        )
        collateral_token_contract = (
            user_position.position.get_collateral_token_contract(web3=web3)
        )

        redeem_event = conditional_token_contract.redeemPositions(
            api_keys=api_keys,
            collateral_token_address=user_position.position.collateral_token_contract_address_checksummed,
            condition_id=condition_id,
            index_sets=user_position.position.indexSets,
            web3=web3,
        )

        logger.info(
            f"Redeemed {redeem_event.payout.as_token} {collateral_token_contract.symbol_cached(web3=web3)} from position {user_position.id=}."
        )

        if auto_withdraw:
            auto_withdraw_collateral_token(
                collateral_token_contract=collateral_token_contract,
                amount_wei=redeem_event.payout,
                api_keys=api_keys,
                web3=web3,
            )


def get_binary_market_p_yes_history(market: OmenAgentMarket) -> list[Probability]:
    history: list[Probability] = []
    trades = sorted(
        OmenSubgraphHandler().get_trades(
            # We need to look at price both after buying or selling, so get trades, not bets.
            market_id=market.market_maker_contract_address_checksummed,
            end_time=market.close_time,
            # Even after market is closed, there can be many `Sell` trades which will converge the probability to the true one.
        ),
        key=lambda x: x.creation_datetime,
    )

    for index, trade in enumerate(trades):
        # We need to append the old probability to have also the initial state of the market (before any bet placement).
        history.append(
            trade.old_probability
            if trade.outcomeIndex == market.yes_index
            else Probability(1 - trade.old_probability)
        )

        # At the last trade, we also need to append the new probability, to have the market latest state.
        if index == len(trades) - 1:
            history.append(
                trade.probability
                if trade.outcomeIndex == market.yes_index
                else Probability(1 - trade.probability)
            )

    return history


def send_keeping_token_to_eoa_xdai(
    api_keys: APIKeys,
    min_required_balance: xDai,
    multiplier: float = 1.0,
    web3: Web3 | None = None,
) -> None:
    """
    Keeps xDai balance above the minimum required balance by transfering keeping token to xDai.
    Optionally, the amount to transfer can be multiplied by the `multiplier`, which can be useful to keep a buffer.
    """
    # Only wxDai can be withdrawn to xDai. Anything else needs to be swapped to wxDai first.
    wxdai_contract = WrappedxDaiContract()

    if KEEPING_ERC20_TOKEN.address != wxdai_contract.address:
        raise RuntimeError(
            "Only wxDai can be withdrawn to xDai. Rest is not implemented for simplicity for now. It would require trading using CoW, or double withdrawing from sDai"
        )

    current_balances_eoa = get_balances(api_keys.public_key, web3)
    current_balances_betting = get_balances(api_keys.bet_from_address, web3)

    # xDai needs to be in our wallet where we pay transaction fees, so do not check for Safe's balance here, but for EOA.
    if current_balances_eoa.xdai >= min_required_balance:
        logger.info(
            f"Current xDai balance {current_balances_eoa.xdai} is more or equal than the required minimum balance {min_required_balance}."
        )
        return

    need_to_withdraw = (min_required_balance - current_balances_eoa.xdai) * multiplier
    need_to_withdraw_wei = need_to_withdraw.as_xdai_wei

    if current_balances_eoa.wxdai >= need_to_withdraw.as_token:
        # If EOA has enough of wxDai, simply withdraw it.
        logger.info(
            f"Withdrawing {need_to_withdraw} wxDai from EOA to keep the EOA's xDai balance above the minimum required balance {min_required_balance}."
        )
        wxdai_contract.withdraw(
            api_keys=api_keys.copy_without_safe_address(),
            amount_wei=need_to_withdraw_wei.as_wei,
            web3=web3,
        )

    elif current_balances_betting.wxdai >= need_to_withdraw.as_token:
        # If Safe has enough of wxDai:
        # First send them to EOA's address.
        logger.info(
            f"Transfering {need_to_withdraw} wxDai from betting address to EOA's address."
        )
        wxdai_contract.transferFrom(
            api_keys=api_keys,
            sender=api_keys.bet_from_address,
            recipient=api_keys.public_key,
            amount_wei=need_to_withdraw_wei.as_wei,
            web3=web3,
        )
        # And then simply withdraw it.
        logger.info(
            f"Withdrawing {need_to_withdraw} wxDai from EOA to keep the EOA's xDai balance above the minimum required balance {min_required_balance}."
        )
        wxdai_contract.withdraw(
            api_keys=api_keys.copy_without_safe_address(),
            amount_wei=need_to_withdraw_wei.as_wei,
            web3=web3,
        )

    else:
        raise OutOfFundsError(
            f"Current wxDai balance ({current_balances_eoa=} for {api_keys.public_key=}, {current_balances_betting=} for {api_keys.bet_from_address=}) is less than the required minimum wxDai to withdraw {need_to_withdraw}."
        )


def get_buy_outcome_token_amount(
    investment_amount: CollateralToken,
    outcome_index: int,
    pool_balances: list[OutcomeToken],
    fees: MarketFees,
) -> OutcomeToken:
    """
    Calculates the amount of outcome tokens received for a given investment

    Taken from https://github.com/gnosis/conditional-tokens-market-makers/blob/6814c0247c745680bb13298d4f0dd7f5b574d0db/contracts/FixedProductMarketMaker.sol#L264
    """
    if outcome_index >= len(pool_balances):
        raise ValueError("invalid outcome index")

    investment_amount_minus_fees = fees.get_after_fees(investment_amount)
    investment_amount_minus_fees_as_ot = OutcomeToken(
        investment_amount_minus_fees.value
    )

    buy_token_pool_balance = pool_balances[outcome_index]
    ending_outcome_balance = buy_token_pool_balance

    # Calculate the ending balance considering all other outcomes
    for i, pool_balance in enumerate(pool_balances):
        if i != outcome_index:
            denominator = pool_balance + investment_amount_minus_fees_as_ot
            ending_outcome_balance = OutcomeToken(
                (ending_outcome_balance * pool_balance / denominator)
            )

    if ending_outcome_balance <= 0:
        raise ValueError("must have non-zero balances")

    result = (
        buy_token_pool_balance
        + investment_amount_minus_fees_as_ot
        - ending_outcome_balance
    )
    return result
