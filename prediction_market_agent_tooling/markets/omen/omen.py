import sys
import typing as t
from datetime import datetime

from web3 import Web3
from web3.constants import HASH_ZERO

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexAddress,
    HexStr,
    OmenOutcomeToken,
    OutcomeStr,
    Probability,
    Wei,
    wei_type,
    xDai,
    xdai_type,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import (
    Bet,
    BetAmount,
    Currency,
    Position,
    TokenAmount,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BASE_URL,
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
    Condition,
    OmenBet,
    OmenMarket,
    OmenUserPosition,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OMEN_DEFAULT_MARKET_FEE,
    Arbitrator,
    OmenCollateralTokenContract,
    OmenConditionalTokenContract,
    OmenFixedProductMarketMakerContract,
    OmenFixedProductMarketMakerFactoryContract,
    OmenOracleContract,
    OmenRealitioContract,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.utils import (
    calculate_sell_amount_in_collateral,
    check_not_none,
)
from prediction_market_agent_tooling.tools.web3_utils import (
    add_fraction,
    remove_fraction,
    wei_to_xdai,
    xdai_to_wei,
)

OMEN_DEFAULT_REALITIO_BOND_VALUE = xdai_type(0.01)


class OmenAgentMarket(AgentMarket):
    """
    Omen's market class that can be used by agents to make predictions.
    """

    currency: t.ClassVar[Currency] = Currency.xDai
    base_url: t.ClassVar[str] = OMEN_BASE_URL
    creator: HexAddress

    collateral_token_contract_address_checksummed: ChecksumAddress
    market_maker_contract_address_checksummed: ChecksumAddress
    condition: Condition
    finalized_time: datetime | None
    created_time: datetime
    close_time: datetime
    outcome_token_amounts: list[OmenOutcomeToken]
    fee: float  # proportion, from 0 to 1

    INVALID_MARKET_ANSWER: HexStr = HexStr(
        "0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
    )

    _binary_market_p_yes_history: list[Probability] | None = None

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

    def get_liquidity_in_wei(self) -> Wei:
        return self.get_contract().totalSupply()

    def get_liquidity_in_xdai(self) -> xDai:
        return wei_to_xdai(self.get_liquidity_in_wei())

    def get_liquidity(self) -> TokenAmount:
        return TokenAmount(
            amount=self.get_liquidity_in_xdai(),
            currency=Currency.xDai,
        )

    def get_tiny_bet_amount(self) -> BetAmount:
        return BetAmount(amount=0.00001, currency=self.currency)

    def place_bet(
        self,
        outcome: bool,
        amount: BetAmount,
        omen_auto_deposit: bool = True,
        web3: Web3 | None = None,
    ) -> None:
        if not self.can_be_traded():
            raise ValueError(
                f"Market {self.id} is not open for trading. Cannot place bet."
            )
        if amount.currency != self.currency:
            raise ValueError(f"Omen bets are made in xDai. Got {amount.currency}.")
        amount_xdai = xDai(amount.amount)
        binary_omen_buy_outcome_tx(
            api_keys=APIKeys(),
            amount=amount_xdai,
            market=self,
            binary_outcome=outcome,
            auto_deposit=omen_auto_deposit,
            web3=web3,
        )

    def calculate_sell_amount_in_collateral(
        self, amount: TokenAmount, outcome: bool
    ) -> xDai:
        if len(self.outcome_token_amounts) != 2:
            raise ValueError(
                f"Market {self.id} has {len(self.outcome_token_amounts)} "
                f"outcomes. This method only supports binary markets."
            )
        sell_index = self.yes_index if outcome else self.no_index
        other_index = self.no_index if outcome else self.yes_index
        collateral = calculate_sell_amount_in_collateral(
            shares_to_sell=amount.amount,
            holdings=wei_to_xdai(Wei(self.outcome_token_amounts[sell_index])),
            other_holdings=wei_to_xdai(Wei(self.outcome_token_amounts[other_index])),
            fee=self.fee,
        )
        return xDai(collateral)

    def sell_tokens(
        self, outcome: bool, amount: TokenAmount, auto_withdraw: bool = False
    ) -> None:
        if not self.can_be_traded():
            raise ValueError(
                f"Market {self.id} is not open for trading. Cannot sell tokens."
            )

        # Convert from token (i.e. share) number to xDai value of tokens, as
        # this is the expected unit of the argument in the smart contract.
        collateral = self.calculate_sell_amount_in_collateral(
            amount=amount,
            outcome=outcome,
        )
        binary_omen_sell_outcome_tx(
            api_keys=APIKeys(),
            amount=collateral,
            market=self,
            binary_outcome=outcome,
            auto_withdraw=auto_withdraw,
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
        If the user never placed a bet on this market, this corretly return False.
        """
        positions = OmenSubgraphHandler().get_positions(condition_id=self.condition.id)
        user_positions = OmenSubgraphHandler().get_user_positions(
            better_address=user,
            position_id_in=[p.id for p in positions],
            # After redeem, this will became zero.
            total_balance_bigger_than=wei_type(0),
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
            current_p_yes=model.current_p_yes,
            condition=model.condition,
            url=model.url,
            volume=wei_to_xdai(model.collateralVolume),
            close_time=model.close_time,
            outcome_token_amounts=model.outcomeTokenAmounts,
            fee=float(wei_to_xdai(model.fee)) if model.fee is not None else 0.0,
        )

    @staticmethod
    def get_binary_markets(
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[datetime] = None,
        excluded_questions: set[str] | None = None,
    ) -> t.Sequence["OmenAgentMarket"]:
        return [
            OmenAgentMarket.from_data_model(m)
            for m in OmenSubgraphHandler().get_omen_binary_markets_simple(
                limit=limit,
                sort_by=sort_by,
                filter_by=filter_by,
                created_after=created_after,
                excluded_questions=excluded_questions,
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
    def get_bets_made_since(
        better_address: ChecksumAddress, start_time: datetime
    ) -> list[Bet]:
        bets = OmenSubgraphHandler().get_bets(
            better_address=better_address, start_time=start_time
        )
        bets.sort(key=lambda x: x.creation_datetime)
        return [b.to_bet() for b in bets]

    def get_contract(
        self,
    ) -> OmenFixedProductMarketMakerContract:
        return OmenFixedProductMarketMakerContract(
            address=self.market_maker_contract_address_checksummed,
        )

    def get_index_set(self, outcome: str) -> int:
        return self.get_outcome_index(outcome) + 1

    def index_set_to_outcome_index(cls, index_set: int) -> int:
        return index_set - 1

    def index_set_to_outcome_str(cls, index_set: int) -> OutcomeStr:
        return OutcomeStr(
            cls.get_outcome_str(cls.index_set_to_outcome_index(index_set))
        )

    def get_token_balance(
        self, user_id: str, outcome: str, web3: Web3 | None = None
    ) -> TokenAmount:
        index_set = self.get_index_set(outcome)
        balances = get_conditional_tokens_balance_for_market(
            self, Web3.to_checksum_address(user_id), web3=web3
        )
        return TokenAmount(
            amount=wei_to_xdai(balances[index_set]),
            currency=Currency.xDai,
        )

    @classmethod
    def get_positions(cls, user_id: str, liquid_only: bool = False) -> list[Position]:
        sgh = OmenSubgraphHandler()
        omen_positions = sgh.get_user_positions(
            better_address=Web3.to_checksum_address(user_id),
            total_balance_bigger_than=wei_type(0),
        )

        # Sort positions and corresponding markets by condition_id
        omen_positions_dict: dict[HexBytes, list[OmenUserPosition]] = {}
        for omen_position in omen_positions:
            condition_id = omen_position.position.condition_id
            omen_positions_dict.setdefault(condition_id, []).append(omen_position)

        omen_markets: dict[HexBytes, OmenMarket] = {
            m.condition.id: m
            for m in sgh.get_omen_binary_markets(
                limit=sys.maxsize,
                condition_id_in=list(omen_positions_dict.keys()),
            )
        }
        if len(omen_markets) != len(omen_positions_dict):
            raise ValueError(
                f"Number of condition ids for markets {len(omen_markets)} and positions {len(omen_positions_dict)} are not equal."
            )

        positions = []
        for condition_id, omen_positions in omen_positions_dict.items():
            market = cls.from_data_model(omen_markets[condition_id])

            # Skip markets that cannot be traded if `liquid_only`` is True.
            if liquid_only and not market.can_be_traded():
                continue

            amounts: dict[OutcomeStr, TokenAmount] = {}
            for omen_position in omen_positions:
                outecome_str = market.index_set_to_outcome_str(
                    omen_position.position.index_set
                )

                # Validate that outcomes are unique for a given condition_id.
                if outecome_str in amounts:
                    raise ValueError(
                        f"Outcome {outecome_str} already exists in {amounts=}"
                    )

                amounts[outecome_str] = TokenAmount(
                    amount=wei_to_xdai(omen_position.totalBalance),
                    currency=Currency.xDai,
                )

            positions.append(Position(market_id=market.id, amounts=amounts))

        return positions

    @classmethod
    def get_user_url(cls, keys: APIKeys) -> str:
        return f"https://gnosisscan.io/address/{keys.bet_from_address}"


def pick_binary_market(
    sort_by: SortBy = SortBy.CLOSING_SOONEST, filter_by: FilterBy = FilterBy.OPEN
) -> OmenMarket:
    subgraph_handler = OmenSubgraphHandler()
    return subgraph_handler.get_omen_binary_markets_simple(
        limit=1, sort_by=sort_by, filter_by=filter_by
    )[0]


def omen_buy_outcome_tx(
    api_keys: APIKeys,
    amount: xDai,
    market: OmenAgentMarket,
    outcome: str,
    auto_deposit: bool,
    web3: Web3 | None = None,
) -> None:
    """
    Bets the given amount of xDai for the given outcome in the given market.
    """
    amount_wei = xdai_to_wei(amount)
    from_address_checksummed = api_keys.bet_from_address

    market_contract: OmenFixedProductMarketMakerContract = market.get_contract()

    collateral_token_contract = OmenCollateralTokenContract()

    # Get the index of the outcome we want to buy.
    outcome_index: int = market.get_outcome_index(outcome)

    # Calculate the amount of shares we will get for the given investment amount.
    expected_shares = market_contract.calcBuyAmount(
        amount_wei, outcome_index, web3=web3
    )
    # Allow 1% slippage.
    expected_shares = remove_fraction(expected_shares, 0.01)
    # Approve the market maker to withdraw our collateral token.
    collateral_token_contract.approve(
        api_keys=api_keys,
        for_address=market_contract.address,
        amount_wei=amount_wei,
        web3=web3,
    )
    # Deposit xDai to the collateral token,
    # this can be skipped, if we know we already have enough collateral tokens.
    collateral_token_balance = collateral_token_contract.balanceOf(
        for_address=from_address_checksummed, web3=web3
    )
    if auto_deposit and collateral_token_balance < amount_wei:
        collateral_token_contract.deposit(
            api_keys=api_keys, amount_wei=amount_wei, web3=web3
        )
    # Buy shares using the deposited xDai in the collateral token.
    market_contract.buy(
        api_keys=api_keys,
        amount_wei=amount_wei,
        outcome_index=outcome_index,
        min_outcome_tokens_to_buy=expected_shares,
        web3=web3,
    )


def binary_omen_buy_outcome_tx(
    api_keys: APIKeys,
    amount: xDai,
    market: OmenAgentMarket,
    binary_outcome: bool,
    auto_deposit: bool,
    web3: Web3 | None = None,
) -> None:
    omen_buy_outcome_tx(
        api_keys=api_keys,
        amount=amount,
        market=market,
        outcome=OMEN_TRUE_OUTCOME if binary_outcome else OMEN_FALSE_OUTCOME,
        auto_deposit=auto_deposit,
        web3=web3,
    )


def omen_sell_outcome_tx(
    api_keys: APIKeys,
    amount: xDai,  # The xDai value of shares to sell.
    market: OmenAgentMarket,
    outcome: str,
    auto_withdraw: bool,
    web3: Web3 | None = None,
) -> None:
    """
    Sells the given xDai value of shares corresponding to the given outcome in
    the given market.

    The number of shares sold will depend on the share price at the time of the
    transaction.
    """
    amount_wei = xdai_to_wei(amount)

    market_contract: OmenFixedProductMarketMakerContract = market.get_contract()
    conditional_token_contract = OmenConditionalTokenContract()
    collateral_token = OmenCollateralTokenContract()

    # Verify, that markets uses conditional tokens that we expect.
    if (
        market_contract.conditionalTokens(web3=web3)
        != conditional_token_contract.address
    ):
        raise ValueError(
            f"Market {market.id} uses conditional token that we didn't expect, {market_contract.conditionalTokens()} != {conditional_token_contract.address=}"
        )

    # Get the index of the outcome we want to buy.
    outcome_index: int = market.get_outcome_index(outcome)

    # Calculate the amount of shares we will sell for the given selling amount of xdai.
    max_outcome_tokens_to_sell = market_contract.calcSellAmount(
        amount_wei, outcome_index, web3=web3
    )
    # Allow 1% slippage.
    max_outcome_tokens_to_sell = add_fraction(max_outcome_tokens_to_sell, 0.01)

    # Approve the market maker to move our (all) conditional tokens.
    conditional_token_contract.setApprovalForAll(
        api_keys=api_keys,
        for_address=market_contract.address,
        approve=True,
        web3=web3,
    )
    # Sell the shares.
    market_contract.sell(
        api_keys,
        amount_wei,
        outcome_index,
        max_outcome_tokens_to_sell,
        web3=web3,
    )
    if auto_withdraw:
        # Optionally, withdraw from the collateral token back to the `from_address` wallet.
        collateral_token.withdraw(api_keys=api_keys, amount_wei=amount_wei, web3=web3)


def binary_omen_sell_outcome_tx(
    api_keys: APIKeys,
    amount: xDai,
    market: OmenAgentMarket,
    binary_outcome: bool,
    auto_withdraw: bool,
    web3: Web3 | None = None,
) -> None:
    omen_sell_outcome_tx(
        api_keys=api_keys,
        amount=amount,
        market=market,
        outcome=OMEN_TRUE_OUTCOME if binary_outcome else OMEN_FALSE_OUTCOME,
        auto_withdraw=auto_withdraw,
        web3=web3,
    )


def omen_create_market_tx(
    api_keys: APIKeys,
    initial_funds: xDai,
    question: str,
    closing_time: datetime,
    category: str,
    language: str,
    outcomes: list[str],
    auto_deposit: bool,
    fee: float = OMEN_DEFAULT_MARKET_FEE,
    web3: Web3 | None = None,
) -> ChecksumAddress:
    """
    Based on omen-exchange TypeScript code: https://github.com/protofire/omen-exchange/blob/b0b9a3e71b415d6becf21fe428e1c4fc0dad2e80/app/src/services/cpk/cpk.ts#L308
    """
    from_address = api_keys.bet_from_address
    initial_funds_wei = xdai_to_wei(initial_funds)

    realitio_contract = OmenRealitioContract()
    conditional_token_contract = OmenConditionalTokenContract()
    collateral_token_contract = OmenCollateralTokenContract()
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

    # Approve the market maker to withdraw our collateral token.
    collateral_token_contract.approve(
        api_keys=api_keys,
        for_address=factory_contract.address,
        amount_wei=initial_funds_wei,
        web3=web3,
    )

    # Deposit xDai to the collateral token,
    # this can be skipped, if we know we already have enough collateral tokens.
    collateral_token_balance = collateral_token_contract.balanceOf(
        for_address=from_address, web3=web3
    )
    if (
        auto_deposit
        and initial_funds_wei > 0
        and collateral_token_balance < initial_funds_wei
    ):
        collateral_token_contract.deposit(api_keys, initial_funds_wei, web3=web3)

    # Create the question on Realitio.
    question_id = realitio_contract.askQuestion(
        api_keys=api_keys,
        question=question,
        category=category,
        outcomes=outcomes,
        language=language,
        arbitrator=Arbitrator.KLEROS,
        opening=closing_time,  # The question is opened at the closing time of the market.
        web3=web3,
    )

    # Construct the condition id.
    condition_id = conditional_token_contract.getConditionId(
        question_id=question_id,
        oracle_address=oracle_contract.address,
        outcomes_slot_count=len(outcomes),
        web3=web3,
    )
    if not conditional_token_contract.does_condition_exists(condition_id, web3=web3):
        conditional_token_contract.prepareCondition(
            api_keys=api_keys,
            question_id=question_id,
            oracle_address=oracle_contract.address,
            outcomes_slot_count=len(outcomes),
            web3=web3,
        )

    # Create the market.
    create_market_receipt_tx = factory_contract.create2FixedProductMarketMaker(
        api_keys=api_keys,
        condition_id=condition_id,
        fee=fee,
        initial_funds_wei=initial_funds_wei,
        web3=web3,
    )

    # Note: In the Omen's Typescript code, there is futher a creation of `stakingRewardsFactoryAddress`,
    # (https://github.com/protofire/omen-exchange/blob/763d9c9d05ebf9edacbc1dbaa561aa5d08813c0f/app/src/services/cpk/fns.ts#L979)
    # but address of stakingRewardsFactoryAddress on xDai/Gnosis is 0x0000000000000000000000000000000000000000,
    # so skipping it here.

    market_address = create_market_receipt_tx["logs"][-1][
        "address"
    ]  # The market address is available in the last emitted log, in the address field.
    return market_address


def omen_fund_market_tx(
    api_keys: APIKeys,
    market: OmenAgentMarket,
    funds: Wei,
    auto_deposit: bool,
    web3: Web3 | None = None,
) -> None:
    from_address = api_keys.bet_from_address
    market_contract = market.get_contract()
    collateral_token_contract = OmenCollateralTokenContract()

    # Deposit xDai to the collateral token,
    # this can be skipped, if we know we already have enough collateral tokens.
    if (
        auto_deposit
        and collateral_token_contract.balanceOf(for_address=from_address, web3=web3)
        < funds
    ):
        collateral_token_contract.deposit(api_keys, funds, web3=web3)

    collateral_token_contract.approve(
        api_keys=api_keys,
        for_address=market_contract.address,
        amount_wei=funds,
        web3=web3,
    )

    market_contract.addFunding(api_keys, funds, web3=web3)


def build_parent_collection_id() -> HexStr:
    return HASH_ZERO  # Taken from Olas


def omen_redeem_full_position_tx(
    api_keys: APIKeys,
    market: OmenAgentMarket,
    web3: Web3 | None = None,
) -> None:
    """
    Redeems position from a given Omen market. Note that we check if there is a balance
    to be redeemed before sending the transaction.
    """

    from_address = api_keys.bet_from_address

    market_contract: OmenFixedProductMarketMakerContract = market.get_contract()
    conditional_token_contract = OmenConditionalTokenContract()

    # Verify, that markets uses conditional tokens that we expect.
    if market_contract.conditionalTokens() != conditional_token_contract.address:
        raise ValueError(
            f"Market {market.id} uses conditional token that we didn't expect, {market_contract.conditionalTokens()} != {conditional_token_contract.address=}"
        )

    parent_collection_id = build_parent_collection_id()

    if not market.is_resolved():
        logger.debug("Cannot redeem winnings if market is not yet resolved. Exiting.")
        return

    amount_per_index = get_conditional_tokens_balance_for_market(
        market, from_address, web3
    )
    amount_wei = sum(amount_per_index.values())
    if amount_wei == 0:
        logger.debug("No balance to claim. Exiting.")
        return

    if not conditional_token_contract.is_condition_resolved(market.condition.id):
        logger.debug("Market not yet resolved, not possible to claim")
        return

    conditional_token_contract.redeemPositions(
        api_keys=api_keys,
        collateral_token_address=market.collateral_token_contract_address_checksummed,
        condition_id=market.condition.id,
        parent_collection_id=parent_collection_id,
        index_sets=market.condition.index_sets,
        web3=web3,
    )


def get_conditional_tokens_balance_for_market(
    market: OmenAgentMarket,
    from_address: ChecksumAddress,
    web3: Web3 | None = None,
) -> dict[int, Wei]:
    """
    We derive the withdrawable balance from the ConditionalTokens contract through CollectionId -> PositionId (which
    also serves as tokenId) -> TokenBalances.
    """
    balance_per_index_set: dict[int, Wei] = {}
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
        balance_per_index_set[index_set] = wei_type(balance_for_position)

    return balance_per_index_set


def omen_remove_fund_market_tx(
    api_keys: APIKeys,
    market: OmenAgentMarket,
    shares: Wei | None,
    web3: Web3 | None = None,
) -> None:
    """
    Removes funding from a given OmenMarket (moving the funds from the OmenMarket to the
    ConditionalTokens contract), and finally calls the `mergePositions` method which transfers collateralToken from the ConditionalTokens contract to the address corresponding to `from_private_key`.

    Warning: Liquidity removal works on the principle of getting market's shares, not the collateral token itself.
    After we remove funding, using the `mergePositions` we get `min(shares per index)` of wxDai back, but the remaining shares can be converted back only after the market is resolved.
    That can be done using the `redeem_from_all_user_positions` function below.
    """
    from_address = api_keys.bet_from_address
    market_contract = market.get_contract()
    original_balances = get_balances(from_address, web3=web3)

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
    parent_collection_id = build_parent_collection_id()
    amount_per_index_set = get_conditional_tokens_balance_for_market(
        market, from_address, web3
    )
    # We fetch the minimum balance of outcome token - for ex, in this tx (https://gnosisscan.io/tx/0xc31c4e9bc6a60cf7db9991a40ec2f2a06e3539f8cb8dd81b6af893cef6f40cd7#eventlog) - event #460, this should yield 9804940144070370149. This amount matches what is displayed in the Omen UI.
    # See similar logic from Olas
    # https://github.com/valory-xyz/market-creator/blob/4bc47f696fb5ecb61c3b7ec8c001ff2ab6c60fcf/packages/valory/skills/market_creation_manager_abci/behaviours.py#L1308
    amount_to_merge = min(amount_per_index_set.values())

    result = conditional_tokens.mergePositions(
        api_keys=api_keys,
        collateral_token_address=market.collateral_token_contract_address_checksummed,
        parent_collection_id=parent_collection_id,
        conditionId=market.condition.id,
        index_sets=market.condition.index_sets,
        amount=amount_to_merge,
        web3=web3,
    )

    new_balances = get_balances(from_address, web3)

    logger.debug(f"Result from merge positions {result}")
    logger.info(
        f"Withdrawn {new_balances.wxdai - original_balances.wxdai} wxDai from liquidity at {market.url=}."
    )


def redeem_from_all_user_positions(
    api_keys: APIKeys,
    web3: Web3 | None = None,
) -> None:
    """
    Redeems from all user positions where the user didn't redeem yet.
    """
    public_key = api_keys.bet_from_address

    conditional_token_contract = OmenConditionalTokenContract()
    user_positions = OmenSubgraphHandler().get_user_positions(
        public_key,
        # After redeem, this will became zero and we won't re-process it.
        total_balance_bigger_than=wei_type(0),
    )

    for index, user_position in enumerate(user_positions):
        condition_id = user_position.position.condition_id

        if not conditional_token_contract.is_condition_resolved(condition_id):
            logger.info(
                f"[{index+1} / {len(user_positions)}] Skipping redeem, {user_position.id=} isn't resolved yet."
            )
            continue

        logger.info(
            f"[{index+1} / {len(user_positions)}] Processing redeem from {user_position.id=}."
        )

        original_balances = get_balances(public_key, web3)
        conditional_token_contract.redeemPositions(
            api_keys=api_keys,
            collateral_token_address=user_position.position.collateral_token_contract_address_checksummed,
            condition_id=condition_id,
            parent_collection_id=build_parent_collection_id(),
            index_sets=user_position.position.indexSets,
            web3=web3,
        )
        new_balances = get_balances(public_key, web3)

        logger.info(
            f"Redeemed {new_balances.wxdai - original_balances.wxdai} wxDai from position {user_position.id=}."
        )


def get_binary_market_p_yes_history(market: OmenAgentMarket) -> list[Probability]:
    history: list[Probability] = []
    trades = sorted(
        OmenSubgraphHandler().get_trades(  # We need to look at price both after buying or selling, so get trades, not bets.
            market_id=market.market_maker_contract_address_checksummed,
            end_time=market.close_time,  # Even after market is closed, there can be many `Sell` trades which will converge the probability to the true one.
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
