import typing as t
from datetime import datetime
from decimal import Decimal

from eth_typing import HexStr
from web3 import Web3
from web3.constants import HASH_ZERO

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexAddress,
    OmenOutcomeToken,
    PrivateKey,
    Wei,
    xDai,
)
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import BetAmount, Currency
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
    Condition,
    OmenBet,
    OmenMarket,
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
from prediction_market_agent_tooling.markets.omen.omen_graph_queries import (
    get_omen_markets,
)
from prediction_market_agent_tooling.tools.web3_utils import (
    add_fraction,
    private_key_to_public_key,
    remove_fraction,
    wei_to_xdai,
    xdai_to_wei,
)

MAX_NUMBER_OF_MARKETS_FOR_SUBGRAPH_RETRIEVAL = 1000


class OmenAgentMarket(AgentMarket):
    """
    Omen's market class that can be used by agents to make predictions.
    """

    currency: t.ClassVar[Currency] = Currency.xDai

    collateral_token_contract_address_checksummed: ChecksumAddress
    market_maker_contract_address_checksummed: ChecksumAddress
    condition: Condition

    INVALID_MARKET_ANSWER: HexStr = HexStr(
        "0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
    )

    def get_tiny_bet_amount(self) -> BetAmount:
        return BetAmount(amount=Decimal(0.00001), currency=self.currency)

    def place_bet(
        self, outcome: bool, amount: BetAmount, omen_auto_deposit: bool = True
    ) -> None:
        if amount.currency != self.currency:
            raise ValueError(f"Omen bets are made in xDai. Got {amount.currency}.")
        amount_xdai = xDai(amount.amount)
        keys = APIKeys()
        binary_omen_buy_outcome_tx(
            amount=amount_xdai,
            from_private_key=keys.bet_from_private_key,
            market=self,
            binary_outcome=outcome,
            auto_deposit=omen_auto_deposit,
        )

    def was_bet_outcome_correct(self, resolved_omen_bets: t.List[OmenBet]) -> bool:
        resolved_bets_for_market = [
            bet for bet in resolved_omen_bets if bet.fpmm.id == self.id
        ]
        # We iterate through bets since agent could have placed bets on multiple outcomes.
        # If one of the bets was correct, we return true since there is a redeemable amount to be retrieved.
        for bet in resolved_bets_for_market:
            # We only handle markets that are already finalized AND have a final answer
            if (
                bet.fpmm.question.answerFinalizedTimestamp is None
                or bet.fpmm.question.currentAnswer is None
            ):
                continue

            # Like Olas, we assert correctness by matching index OR invalid market answer
            if bet.outcomeIndex == int(
                bet.fpmm.question.currentAnswer, 16
            ) or bet.outcomeIndex == int(self.INVALID_MARKET_ANSWER, 16):
                return True

        return False

    def check_if_position_was_already_redeemed(self) -> bool:
        """
        Olas solves this problem (see https://github.com/valory-xyz/trader/blob/033ad88998fe0dc16457cd312b32f9e3b2d9a25f/packages/valory/skills/decision_maker_abci/behaviours/reedem.py#L487) by keeping state of the conditionIDs that were already claimed.
        Since we currently use stateless functions to redeem positions, it's not possible to query state. Hence we proceed by not tracking the positions already redeemed.
        Note that this has no major consequences from a gas perspective, it only incurs extra subgraph queries and RPC reads, no writes hence no gas costs.
        """
        return False

    def redeem_positions(self, bets_on_market: t.List[OmenBet]) -> None:
        keys = APIKeys()

        bet_was_correct = self.was_bet_outcome_correct(bets_on_market)
        if not bet_was_correct:
            # print(f"Bet placed on market {self.id} was incorrect.")
            return None

        position_already_redeemed = self.check_if_position_was_already_redeemed()
        if position_already_redeemed:
            print(f"Position on market {self.id} was already redeemed.")
            return None

        return omen_redeem_full_position_tx(
            market=self, from_private_key=keys.bet_from_private_key
        )

    @staticmethod
    def from_data_model(model: OmenMarket) -> "OmenAgentMarket":
        return OmenAgentMarket(
            id=model.id,
            question=model.title,
            outcomes=model.outcomes,
            collateral_token_contract_address_checksummed=model.collateral_token_contract_address_checksummed,
            market_maker_contract_address_checksummed=model.market_maker_contract_address_checksummed,
            resolution=model.get_resolution_enum(),
            created_time=model.creation_datetime,
            close_time=model.finalized_datetime,
            p_yes=model.p_yes,
            condition=model.condition,
            url=model.url,
            volume=wei_to_xdai(model.collateralVolume),
        )

    @staticmethod
    def get_binary_markets(
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[datetime] = None,
        excluded_questions: set[str] | None = None,
    ) -> list[AgentMarket]:
        return [
            OmenAgentMarket.from_data_model(m)
            for m in get_omen_binary_markets(
                limit=limit,
                sort_by=sort_by,
                created_after=created_after,
                filter_by=filter_by,
                excluded_questions=excluded_questions,
            )
        ]

    def get_contract(self) -> OmenFixedProductMarketMakerContract:
        return OmenFixedProductMarketMakerContract(
            address=self.market_maker_contract_address_checksummed
        )


def construct_query_get_fixed_product_markets_makers(
    include_creator: bool, filter_by: FilterBy
) -> str:
    query = """
        query getFixedProductMarketMakers(
            $first: Int!,
            $outcomes: [String!],
            $orderBy: String!,
            $orderDirection: String!,
            $creationTimestamp_gt: Int!,
            $creator: Bytes = null,
        ) {
            fixedProductMarketMakers(
                where: {
                    isPendingArbitration: false,
                    outcomes: $outcomes
                    creationTimestamp_gt: $creationTimestamp_gt
                    creator: $creator,
                    answerFinalizedTimestamp: null
                    resolutionTimestamp_not: null
                },
                orderBy: creationTimestamp,
                orderDirection: desc,
                first: $first
            ) {
                id
                title
                collateralVolume
                usdVolume
                collateralToken
                outcomes
                outcomeTokenAmounts
                outcomeTokenMarginalPrices
                fee
                answerFinalizedTimestamp
                resolutionTimestamp
                currentAnswer
                creationTimestamp
                category
                condition {
                    id
                    outcomeSlotCount
                }
            }
        }
    """

    if filter_by == FilterBy.OPEN:
        query = query.replace("resolutionTimestamp_not: null", "")
    elif filter_by == FilterBy.RESOLVED:
        query = query.replace("answerFinalizedTimestamp: null", "")
    elif filter_by == FilterBy.NONE:
        query = query.replace("answerFinalizedTimestamp: null", "")
        query = query.replace("resolutionTimestamp_not: null", "")
    else:
        raise ValueError(f"Unknown filter_by: {filter_by}")

    if not include_creator:
        # If we aren't filtering by query, we need to remove it from where, otherwise "creator: null" will return 0 results.
        query = query.replace("creator: $creator,", "")

    return query


def ordering_from_sort_by(sort_by: SortBy) -> tuple[str, str]:
    """
    Returns 'orderBy' and 'orderDirection' strings for the given SortBy.
    """
    if sort_by == SortBy.CLOSING_SOONEST:
        return "creationTimestamp", "desc"  # TODO make more accurate
    elif sort_by == SortBy.NEWEST:
        return "creationTimestamp", "desc"
    else:
        raise ValueError(f"Unknown sort_by: {sort_by}")


def get_omen_binary_markets(
    limit: int,
    sort_by: SortBy,
    filter_by: FilterBy = FilterBy.OPEN,
    created_after: t.Optional[datetime] = None,
    creator: t.Optional[HexAddress] = None,
    excluded_questions: set[str] | None = None,
) -> list[OmenMarket]:
    return get_omen_markets(
        first=limit,
        outcomes=[OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
        sort_by=sort_by,
        created_after=created_after,
        filter_by=filter_by,
        creator=creator,
        excluded_questions=excluded_questions,
    )


def pick_binary_market(
    sort_by: SortBy = SortBy.CLOSING_SOONEST, filter_by: FilterBy = FilterBy.OPEN
) -> OmenMarket:
    return get_omen_binary_markets(limit=1, sort_by=sort_by, filter_by=filter_by)[0]


def omen_buy_outcome_tx(
    amount: xDai,
    from_private_key: PrivateKey,
    market: OmenAgentMarket,
    outcome: str,
    auto_deposit: bool,
) -> None:
    """
    Bets the given amount of xDai for the given outcome in the given market.
    """
    amount_wei = xdai_to_wei(amount)
    from_address_checksummed = private_key_to_public_key(from_private_key)

    market_contract: OmenFixedProductMarketMakerContract = market.get_contract()
    collateral_token_contract = OmenCollateralTokenContract()

    # Get the index of the outcome we want to buy.
    outcome_index: int = market.get_outcome_index(outcome)

    # Calculate the amount of shares we will get for the given investment amount.
    expected_shares = market_contract.calcBuyAmount(amount_wei, outcome_index)
    # Allow 1% slippage.
    expected_shares = remove_fraction(expected_shares, 0.01)
    # Approve the market maker to withdraw our collateral token.
    collateral_token_contract.approve(
        for_address=market_contract.address,
        amount_wei=amount_wei,
        from_private_key=from_private_key,
    )
    # Deposit xDai to the collateral token,
    # this can be skipped, if we know we already have enough collateral tokens.
    collateral_token_balance = collateral_token_contract.balanceOf(
        for_address=from_address_checksummed,
    )
    if auto_deposit and collateral_token_balance < amount_wei:
        collateral_token_contract.deposit(
            amount_wei=amount_wei,
            from_private_key=from_private_key,
        )
    # Buy shares using the deposited xDai in the collateral token.
    market_contract.buy(
        amount_wei=amount_wei,
        outcome_index=outcome_index,
        min_outcome_tokens_to_buy=expected_shares,
        from_private_key=from_private_key,
    )


def binary_omen_buy_outcome_tx(
    amount: xDai,
    from_private_key: PrivateKey,
    market: OmenAgentMarket,
    binary_outcome: bool,
    auto_deposit: bool,
) -> None:
    omen_buy_outcome_tx(
        amount=amount,
        from_private_key=from_private_key,
        market=market,
        outcome=OMEN_TRUE_OUTCOME if binary_outcome else OMEN_FALSE_OUTCOME,
        auto_deposit=auto_deposit,
    )


def omen_sell_outcome_tx(
    amount: xDai,
    from_private_key: PrivateKey,
    market: OmenAgentMarket,
    outcome: str,
    auto_withdraw: bool,
) -> None:
    """
    Sells the given amount of shares for the given outcome in the given market.
    """
    amount_wei = xdai_to_wei(amount)

    market_contract: OmenFixedProductMarketMakerContract = market.get_contract()
    conditional_token_contract = OmenConditionalTokenContract()
    collateral_token = OmenCollateralTokenContract()

    # Verify, that markets uses conditional tokens that we expect.
    if market_contract.conditionalTokens() != conditional_token_contract.address:
        raise ValueError(
            f"Market {market.id} uses conditional token that we didn't expect, {market_contract.conditionalTokens()} != {conditional_token_contract.address=}"
        )

    # Get the index of the outcome we want to buy.
    outcome_index: int = market.get_outcome_index(outcome)

    # Calculate the amount of shares we will sell for the given selling amount of xdai.
    max_outcome_tokens_to_sell = market_contract.calcSellAmount(
        amount_wei, outcome_index
    )
    # Allow 1% slippage.
    max_outcome_tokens_to_sell = add_fraction(max_outcome_tokens_to_sell, 0.01)

    # Approve the market maker to move our (all) conditional tokens.
    conditional_token_contract.setApprovalForAll(
        for_address=market_contract.address,
        approve=True,
        from_private_key=from_private_key,
    )
    # Sell the shares.
    market_contract.sell(
        amount_wei,
        outcome_index,
        max_outcome_tokens_to_sell,
        from_private_key,
    )
    if auto_withdraw:
        # Optionally, withdraw from the collateral token back to the `from_address` wallet.
        collateral_token.withdraw(
            amount_wei=amount_wei,
            from_private_key=from_private_key,
        )


def binary_omen_sell_outcome_tx(
    amount: xDai,
    from_private_key: PrivateKey,
    market: OmenAgentMarket,
    binary_outcome: bool,
    auto_withdraw: bool,
) -> None:
    omen_sell_outcome_tx(
        amount=amount,
        from_private_key=from_private_key,
        market=market,
        outcome=OMEN_TRUE_OUTCOME if binary_outcome else OMEN_FALSE_OUTCOME,
        auto_withdraw=auto_withdraw,
    )


def omen_create_market_tx(
    initial_funds: xDai,
    question: str,
    closing_time: datetime,
    category: str,
    language: str,
    from_private_key: PrivateKey,
    outcomes: list[str],
    auto_deposit: bool,
    fee: float = OMEN_DEFAULT_MARKET_FEE,
) -> ChecksumAddress:
    """
    Based on omen-exchange TypeScript code: https://github.com/protofire/omen-exchange/blob/b0b9a3e71b415d6becf21fe428e1c4fc0dad2e80/app/src/services/cpk/cpk.ts#L308
    """
    from_address = private_key_to_public_key(from_private_key)
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
        for_address=factory_contract.address,
        amount_wei=initial_funds_wei,
        from_private_key=from_private_key,
    )

    # Deposit xDai to the collateral token,
    # this can be skipped, if we know we already have enough collateral tokens.
    collateral_token_balance = collateral_token_contract.balanceOf(
        for_address=from_address,
    )
    if (
        auto_deposit
        and initial_funds_wei > 0
        and collateral_token_balance < initial_funds_wei
    ):
        collateral_token_contract.deposit(initial_funds_wei, from_private_key)

    # Create the question on Realitio.
    question_id = realitio_contract.askQuestion(
        question=question,
        category=category,
        outcomes=outcomes,
        language=language,
        arbitrator=Arbitrator.KLEROS,
        opening=closing_time,  # The question is opened at the closing time of the market.
        from_private_key=from_private_key,
    )

    # Construct the condition id.
    condition_id = conditional_token_contract.getConditionId(
        question_id=question_id,
        oracle_address=oracle_contract.address,
        outcomes_slot_count=len(outcomes),
    )
    if not conditional_token_contract.does_condition_exists(condition_id):
        conditional_token_contract.prepareCondition(
            question_id=question_id,
            oracle_address=oracle_contract.address,
            outcomes_slot_count=len(outcomes),
            from_private_key=from_private_key,
        )

    # Create the market.
    create_market_receipt_tx = factory_contract.create2FixedProductMarketMaker(
        from_private_key=from_private_key,
        condition_id=condition_id,
        fee=fee,
        initial_funds_wei=initial_funds_wei,
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
    market: OmenAgentMarket,
    funds: xDai,
    from_private_key: PrivateKey,
    auto_deposit: bool,
) -> None:
    funds_wei = xdai_to_wei(funds)
    from_address = private_key_to_public_key(from_private_key)
    market_contract = market.get_contract()
    collateral_token_contract = OmenCollateralTokenContract()

    # Deposit xDai to the collateral token,
    # this can be skipped, if we know we already have enough collateral tokens.
    if (
        auto_deposit
        and collateral_token_contract.balanceOf(
            for_address=from_address,
        )
        < funds_wei
    ):
        collateral_token_contract.deposit(funds_wei, from_private_key)

    collateral_token_contract.approve(
        for_address=market_contract.address,
        amount_wei=funds_wei,
        from_private_key=from_private_key,
    )

    market_contract.addFunding(funds_wei, from_private_key)


def build_parent_collection_id() -> HexStr:
    return HASH_ZERO  # Taken from Olas


def omen_redeem_full_position_tx(
    market: OmenAgentMarket,
    from_private_key: PrivateKey,
    web3: Web3 | None = None,
) -> None:
    """
    Redeems position from a given Omen market. Note that we check if there is a balance
    to be redeemed before sending the transaction.
    """

    from_address = private_key_to_public_key(from_private_key)

    market_contract: OmenFixedProductMarketMakerContract = market.get_contract()
    conditional_token_contract = OmenConditionalTokenContract()

    # Verify, that markets uses conditional tokens that we expect.
    if market_contract.conditionalTokens() != conditional_token_contract.address:
        raise ValueError(
            f"Market {market.id} uses conditional token that we didn't expect, {market_contract.conditionalTokens()} != {conditional_token_contract.address=}"
        )

    parent_collection_id = build_parent_collection_id()

    if not market.is_resolved():
        print("Cannot redeem winnings if market is not yet resolved. Exiting.")
        return

    amount_wei = get_conditional_tokens_balance_for_market(market, from_address, web3)
    if amount_wei == 0:
        print("No balance to claim. Exiting.")
        return

    conditional_token_contract = OmenConditionalTokenContract()

    # check if condition has already been resolved by oracle
    payout_for_condition = conditional_token_contract.payoutDenominator(
        market.condition.id
    )
    if not payout_for_condition > 0:
        # from ConditionalTokens.redeemPositions:
        # uint den = payoutDenominator[conditionId]; require(den > 0, "result for condition not received yet");
        print("Market not yet resolved, not possible to claim")
        return

    conditional_token_contract.redeemPositions(
        from_private_key=from_private_key,
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
) -> Wei:
    """
    We derive the withdrawable balance from the ConditionalTokens contract through CollectionId -> PositionId (which
    also serves as tokenId) -> TokenBalances.
    """
    conditional_token_contract = OmenConditionalTokenContract()
    parent_collection_id = build_parent_collection_id()
    balance = 0

    for index_set in market.condition.index_sets:
        collection_id: bytes = conditional_token_contract.getCollectionId(
            parent_collection_id, market.condition.id, index_set, web3=web3
        )
        # Note that collection_id is returned as bytes, which is accepted by the contract calls downstream.
        position_id: int = conditional_token_contract.getPositionId(
            market.collateral_token_contract_address_checksummed,
            collection_id,
            web3=web3,
        )
        balance_for_position: int = conditional_token_contract.balanceOf(
            from_address=from_address, position_id=position_id, web3=web3
        )
        balance += balance_for_position

    return Wei(balance)


def omen_remove_fund_market_tx(
    market: OmenAgentMarket,
    shares: OmenOutcomeToken,
    from_private_key: PrivateKey,
    auto_withdraw: bool,
) -> None:
    market_contract = market.get_contract()
    market_contract.removeFunding(shares, from_private_key)

    # TODO: How to withdraw remove funding back to our wallet.
    if auto_withdraw:
        raise NotImplementedError("TODO")
