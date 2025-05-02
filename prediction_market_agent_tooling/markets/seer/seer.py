import typing as t

from eth_typing import ChecksumAddress
from web3 import Web3
from web3.types import TxReceipt

from prediction_market_agent_tooling.config import APIKeys, RPCConfig
from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    HexAddress,
    HexBytes,
    HexStr,
    OutcomeStr,
    OutcomeToken,
    OutcomeWei,
    xDai,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    ProcessedMarket,
    ProcessedTradedMarket,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import ExistingPosition
from prediction_market_agent_tooling.markets.market_fees import MarketFees
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.seer.data_models import (
    RedeemParams,
    SeerMarket,
)
from prediction_market_agent_tooling.markets.seer.price_manager import PriceManager
from prediction_market_agent_tooling.markets.seer.seer_contracts import (
    GnosisRouter,
    SeerMarketFactory,
)
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import (
    NewMarketEvent,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractERC20OnGnosisChain,
    init_collateral_token_contract,
    to_gnosis_chain_contract,
)
from prediction_market_agent_tooling.tools.cow.cow_order import (
    get_buy_token_amount_else_raise,
    get_trades_by_owner,
    swap_tokens_waiting,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.tokens.auto_deposit import (
    auto_deposit_collateral_token,
)
from prediction_market_agent_tooling.tools.tokens.usd import (
    get_token_in_usd,
    get_usd_in_token,
)

# We place a larger bet amount by default than Omen so that cow presents valid quotes.
SEER_TINY_BET_AMOUNT = USD(0.1)


class SeerAgentMarket(AgentMarket):
    wrapped_tokens: list[ChecksumAddress]
    creator: HexAddress
    collateral_token_contract_address_checksummed: ChecksumAddress
    condition_id: HexBytes
    description: str | None = (
        None  # Seer markets don't have a description, so just default to None.
    )
    outcomes_supply: int

    def get_collateral_token_contract(
        self, web3: Web3 | None = None
    ) -> ContractERC20OnGnosisChain:
        web3 = web3 or RPCConfig().get_web3()
        return to_gnosis_chain_contract(
            init_collateral_token_contract(
                self.collateral_token_contract_address_checksummed, web3
            )
        )

    def store_prediction(
        self,
        processed_market: ProcessedMarket | None,
        keys: APIKeys,
        agent_name: str,
    ) -> None:
        """On Seer, we have to store predictions along with trades, see `store_trades`."""

    def store_trades(
        self,
        traded_market: ProcessedTradedMarket | None,
        keys: APIKeys,
        agent_name: str,
        web3: Web3 | None = None,
    ) -> None:
        pass

    def get_token_in_usd(self, x: CollateralToken) -> USD:
        return get_token_in_usd(x, self.collateral_token_contract_address_checksummed)

    def get_usd_in_token(self, x: USD) -> CollateralToken:
        return get_usd_in_token(x, self.collateral_token_contract_address_checksummed)

    def get_buy_token_amount(
        self, bet_amount: USD | CollateralToken, outcome_str: OutcomeStr
    ) -> OutcomeToken | None:
        """Returns number of outcome tokens returned for a given bet expressed in collateral units."""

        if outcome_str not in self.outcomes:
            raise ValueError(
                f"Outcome {outcome_str} not found in market outcomes {self.outcomes}"
            )

        outcome_token = self.get_wrapped_token_for_outcome(outcome_str)

        bet_amount_in_tokens = self.get_in_token(bet_amount)

        p = PriceManager.build(market_id=HexBytes(HexStr(self.id)))
        price = p.get_price_for_token(
            token=outcome_token, collateral_exchange_amount=bet_amount_in_tokens
        )
        if not price:
            logger.info(f"Could not get price for token {outcome_token}")
            return None

        amount_outcome_tokens = bet_amount_in_tokens / price
        return OutcomeToken(amount_outcome_tokens)

    def get_sell_value_of_outcome_token(
        self, outcome: OutcomeStr, amount: OutcomeToken
    ) -> CollateralToken:
        if amount == amount.zero():
            return CollateralToken.zero()

        wrapped_outcome_token = self.get_wrapped_token_for_outcome(outcome)

        # We calculate how much collateral we would get back if we sold `amount` of outcome token.
        value_outcome_token_in_collateral = get_buy_token_amount_else_raise(
            sell_amount=amount.as_outcome_wei.as_wei,
            sell_token=wrapped_outcome_token,
            buy_token=self.collateral_token_contract_address_checksummed,
        )
        return value_outcome_token_in_collateral.as_token

    @staticmethod
    def get_trade_balance(api_keys: APIKeys) -> USD:
        return OmenAgentMarket.get_trade_balance(api_keys=api_keys)

    def get_tiny_bet_amount(self) -> CollateralToken:
        return self.get_in_token(SEER_TINY_BET_AMOUNT)

    def get_position_else_raise(
        self, user_id: str, web3: Web3 | None = None
    ) -> ExistingPosition:
        """
        Fetches position from the user in a given market.
        We ignore the INVALID balances since we are only interested in binary outcomes.
        """

        amounts_ot: dict[OutcomeStr, OutcomeToken] = {}

        for outcome_str, wrapped_token in zip(self.outcomes, self.wrapped_tokens):
            outcome_token_balance_wei = OutcomeWei.from_wei(
                ContractERC20OnGnosisChain(address=wrapped_token).balanceOf(
                    for_address=Web3.to_checksum_address(user_id), web3=web3
                )
            )

            amounts_ot[
                OutcomeStr(outcome_str)
            ] = outcome_token_balance_wei.as_outcome_token

        amounts_current = {
            k: self.get_token_in_usd(self.get_sell_value_of_outcome_token(k, v))
            for k, v in amounts_ot.items()
        }
        amounts_potential = {
            k: self.get_token_in_usd(v.as_token) for k, v in amounts_ot.items()
        }
        return ExistingPosition(
            market_id=self.id,
            amounts_current=amounts_current,
            amounts_potential=amounts_potential,
            amounts_ot=amounts_ot,
        )

    def get_position(
        self, user_id: str, web3: Web3 | None = None
    ) -> ExistingPosition | None:
        try:
            return self.get_position_else_raise(user_id=user_id, web3=web3)
        except Exception as e:
            logger.warning(f"Could not get position for user {user_id}, exception {e}")
            return None

    @staticmethod
    def get_user_id(api_keys: APIKeys) -> str:
        return OmenAgentMarket.get_user_id(api_keys)

    @staticmethod
    def _filter_markets_contained_in_trades(
        api_keys: APIKeys,
        markets: list[SeerMarket],
    ) -> list[SeerMarket]:
        """
        We filter the markets using previous trades by the user so that we don't have to process all Seer markets.
        """
        trades_by_user = get_trades_by_owner(api_keys.bet_from_address)

        traded_tokens = {t.buyToken for t in trades_by_user}.union(
            [t.sellToken for t in trades_by_user]
        )
        filtered_markets = []
        for market in markets:
            if any(
                [
                    Web3.to_checksum_address(wrapped_token) in traded_tokens
                    for wrapped_token in market.wrapped_tokens
                ]
            ):
                filtered_markets.append(market)

        return filtered_markets

    @staticmethod
    def redeem_winnings(api_keys: APIKeys) -> None:
        web3 = RPCConfig().get_web3()
        subgraph = SeerSubgraphHandler()

        closed_markets = subgraph.get_binary_markets(
            filter_by=FilterBy.RESOLVED, sort_by=SortBy.NEWEST
        )
        filtered_markets = SeerAgentMarket._filter_markets_contained_in_trades(
            api_keys, closed_markets
        )

        market_balances = {
            market.id: market.get_outcome_token_balances(
                api_keys.bet_from_address, web3
            )
            for market in filtered_markets
        }

        markets_to_redeem = [
            market
            for market in filtered_markets
            if market.is_redeemable(owner=api_keys.bet_from_address, web3=web3)
        ]

        gnosis_router = GnosisRouter()
        for market in markets_to_redeem:
            try:
                params = RedeemParams(
                    market=Web3.to_checksum_address(market.id),
                    outcome_indices=list(range(len(market.payout_numerators))),
                    amounts=market_balances[market.id],
                )
                gnosis_router.redeem_to_base(api_keys, params=params, web3=web3)
                logger.info(f"Redeemed market {market.id.hex()}")
            except Exception as e:
                logger.error(f"Failed to redeem market {market.id.hex()}, {e}")

        # GnosisRouter withdraws sDai into wxDAI/xDai on its own, so no auto-withdraw needed by us.

    @staticmethod
    def verify_operational_balance(api_keys: APIKeys) -> bool:
        return OmenAgentMarket.verify_operational_balance(api_keys=api_keys)

    @staticmethod
    def from_data_model_with_subgraph(
        model: SeerMarket, seer_subgraph: SeerSubgraphHandler
    ) -> t.Optional["SeerAgentMarket"]:
        p = PriceManager(seer_market=model, seer_subgraph=seer_subgraph)
        # current_p_yes = p.current_p_yes()
        probability_map = p.build_probability_map()
        if not probability_map:
            logger.info(
                f"probability_map for market {model.id.hex()} could not be calculated. Skipping."
            )
            return None

        return SeerAgentMarket(
            id=model.id.hex(),
            question=model.title,
            creator=model.creator,
            created_time=model.created_time,
            outcomes=model.outcomes,
            collateral_token_contract_address_checksummed=model.collateral_token_contract_address_checksummed,
            condition_id=model.condition_id,
            url=model.url,
            close_time=model.close_time,
            wrapped_tokens=[Web3.to_checksum_address(i) for i in model.wrapped_tokens],
            fees=MarketFees.get_zero_fees(),
            outcome_token_pool=None,
            outcomes_supply=model.outcomes_supply,
            resolution=None,
            volume=None,
            probabilities=probability_map,
        )

    @staticmethod
    def get_markets(
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[DatetimeUTC] = None,
        excluded_questions: set[str] | None = None,
        fetch_categorical_markets: bool = False,
    ) -> t.Sequence["SeerAgentMarket"]:
        seer_subgraph = SeerSubgraphHandler()
        markets = seer_subgraph.get_binary_markets(
            limit=limit,
            sort_by=sort_by,
            filter_by=filter_by,
            include_categorical_markets=fetch_categorical_markets,
        )

        # We exclude the None values below because `from_data_model_with_subgraph` can return None, which
        # represents an invalid market.
        return [
            market
            for m in markets
            if (
                market := SeerAgentMarket.from_data_model_with_subgraph(
                    model=m, seer_subgraph=seer_subgraph
                )
            )
            is not None
        ]

    def get_outcome_str_from_idx(self, outcome_index: int) -> OutcomeStr:
        return self.outcomes[outcome_index]

    def get_liquidity_for_outcome(
        self, outcome: OutcomeStr, web3: Web3 | None = None
    ) -> CollateralToken:
        """Liquidity per outcome is comprised of the balance of outcomeToken + collateralToken held by the pool itself (see https://github.com/seer-pm/demo/blob/7bfd0a062780ed6567f65714c4fc4f6e6cdf1c4f/web/netlify/functions/utils/fetchPools.ts#L35-L42)."""

        outcome_token = self.get_wrapped_token_for_outcome(outcome)
        pool = SeerSubgraphHandler().get_pool_by_token(
            token_address=outcome_token,
            collateral_address=self.collateral_token_contract_address_checksummed,
        )
        if not pool:
            logger.info(
                f"Could not fetch pool for token {outcome_token}, no liquidity available for outcome."
            )
            return CollateralToken(0)
        p = PriceManager.build(HexBytes(HexStr(self.id)))
        total = CollateralToken(0)

        for token_address in [pool.token0.id, pool.token1.id]:
            token_address_checksummed = Web3.to_checksum_address(token_address)
            token_contract = ContractERC20OnGnosisChain(
                address=token_address_checksummed
            )

            token_balance = token_contract.balance_of_in_tokens(
                for_address=Web3.to_checksum_address(HexAddress(HexStr(pool.id.hex()))),
                web3=web3,
            )

            # get price
            token_price_in_sdai = (
                p.get_token_price_from_pools(token=token_address_checksummed)
                if token_address_checksummed
                != self.collateral_token_contract_address_checksummed
                else CollateralToken(1.0)
            )

            # We ignore the liquidity in outcome tokens if price unknown.
            if token_price_in_sdai:
                sdai_balance = token_balance * token_price_in_sdai
                total += sdai_balance

        return total

    def get_liquidity(self) -> CollateralToken:
        liquidity_in_collateral = CollateralToken(0)
        # We ignore the invalid outcome
        for outcome in self.outcomes[:-1]:
            liquidity_for_outcome = self.get_liquidity_for_outcome(outcome)
            liquidity_in_collateral += liquidity_for_outcome

        return liquidity_in_collateral

    def has_liquidity_for_outcome(self, outcome: OutcomeStr) -> bool:
        liquidity = self.get_liquidity_for_outcome(outcome)
        return liquidity > CollateralToken(0)

    def has_liquidity(self) -> bool:
        # We define a market as having liquidity if it has liquidity for all outcomes except for the invalid (index -1)
        return all(
            [self.has_liquidity_for_outcome(outcome) for outcome in self.outcomes[:-1]]
        )

    def get_wrapped_token_for_outcome(self, outcome: OutcomeStr) -> ChecksumAddress:
        outcome_idx = self.outcomes.index(outcome)
        return self.wrapped_tokens[outcome_idx]

    def place_bet(
        self,
        outcome: OutcomeStr,
        amount: USD,
        auto_deposit: bool = True,
        web3: Web3 | None = None,
        api_keys: APIKeys | None = None,
    ) -> str:
        api_keys = api_keys if api_keys is not None else APIKeys()
        if not self.can_be_traded():
            raise ValueError(
                f"Market {self.id} is not open for trading. Cannot place bet."
            )

        amount_in_token = self.get_usd_in_token(amount)
        amount_wei = amount_in_token.as_wei
        collateral_contract = self.get_collateral_token_contract()

        if auto_deposit:
            auto_deposit_collateral_token(
                collateral_contract, amount_wei, api_keys, web3
            )

        collateral_balance = collateral_contract.balanceOf(api_keys.bet_from_address)
        if collateral_balance < amount_wei:
            raise ValueError(
                f"Balance {collateral_balance} not enough for bet size {amount}"
            )

        outcome_token = self.get_wrapped_token_for_outcome(outcome)

        #  Sell sDAI using token address
        order_metadata = swap_tokens_waiting(
            amount_wei=amount_wei,
            sell_token=collateral_contract.address,
            buy_token=outcome_token,
            api_keys=api_keys,
            web3=web3,
        )
        logger.debug(
            f"Purchased {outcome_token} in exchange for {collateral_contract.address}. Order details {order_metadata}"
        )

        return order_metadata.uid.root

    def sell_tokens(
        self,
        outcome: OutcomeStr,
        amount: USD | OutcomeToken,
        auto_withdraw: bool = True,
        api_keys: APIKeys | None = None,
        web3: Web3 | None = None,
    ) -> str:
        """
        Sells the given number of shares for the given outcome in the given market.
        """
        outcome_token = self.get_wrapped_token_for_outcome(outcome)
        api_keys = api_keys if api_keys is not None else APIKeys()

        token_amount = (
            amount.as_outcome_wei.as_wei
            if isinstance(amount, OutcomeToken)
            else self.get_in_token(amount).as_wei
        )

        order_metadata = swap_tokens_waiting(
            amount_wei=token_amount,
            sell_token=outcome_token,
            buy_token=Web3.to_checksum_address(
                self.collateral_token_contract_address_checksummed
            ),
            api_keys=api_keys,
            web3=web3,
        )

        logger.debug(
            f"Sold {outcome_token} in exchange for {self.collateral_token_contract_address_checksummed}. Order details {order_metadata}"
        )

        return order_metadata.uid.root


def seer_create_market_tx(
    api_keys: APIKeys,
    initial_funds: USD | CollateralToken,
    question: str,
    opening_time: DatetimeUTC,
    language: str,
    outcomes: t.Sequence[OutcomeStr],
    auto_deposit: bool,
    category: str,
    min_bond: xDai,
    web3: Web3 | None = None,
) -> ChecksumAddress:
    web3 = web3 or SeerMarketFactory.get_web3()  # Default to Gnosis web3.

    factory_contract = SeerMarketFactory()
    collateral_token_address = factory_contract.collateral_token(web3=web3)
    collateral_token_contract = to_gnosis_chain_contract(
        init_collateral_token_contract(collateral_token_address, web3)
    )

    initial_funds_in_collateral = (
        get_usd_in_token(initial_funds, collateral_token_address)
        if isinstance(initial_funds, USD)
        else initial_funds
    )
    initial_funds_in_collateral_wei = initial_funds_in_collateral.as_wei

    if auto_deposit:
        auto_deposit_collateral_token(
            collateral_token_contract=collateral_token_contract,
            api_keys=api_keys,
            collateral_amount_wei_or_usd=initial_funds_in_collateral_wei,
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
    params = factory_contract.build_market_params(
        market_question=question,
        outcomes=outcomes,
        opening_time=opening_time,
        language=language,
        category=category,
        min_bond=min_bond,
    )
    tx_receipt = factory_contract.create_categorical_market(
        api_keys=api_keys, params=params, web3=web3
    )

    # ToDo - Add liquidity to market on Swapr (https://github.com/gnosis/prediction-market-agent-tooling/issues/497)
    market_address = extract_market_address_from_tx(
        factory_contract=factory_contract, tx_receipt=tx_receipt, web3=web3
    )
    return market_address


def extract_market_address_from_tx(
    factory_contract: SeerMarketFactory, tx_receipt: TxReceipt, web3: Web3
) -> ChecksumAddress:
    """We extract the newly created market from the NewMarket event emitted in the transaction."""
    event_logs = (
        factory_contract.get_web3_contract(web3=web3)
        .events.NewMarket()
        .process_receipt(tx_receipt)
    )
    new_market_event = NewMarketEvent(**event_logs[0]["args"])
    return Web3.to_checksum_address(new_market_event.market)
