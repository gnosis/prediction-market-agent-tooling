import typing as t

from eth_typing import ChecksumAddress
from web3 import Web3
from web3.types import TxReceipt

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    HexAddress,
    HexBytes,
    OutcomeStr,
    Wei,
    wei_type,
    xDai,
    xdai_type,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    ProcessedMarket,
    ProcessedTradedMarket,
    SortBy,
)
from prediction_market_agent_tooling.markets.blockchain_utils import (
    get_total_balance,
    store_trades,
)
from prediction_market_agent_tooling.markets.data_models import (
    BetAmount,
    Currency,
    Position,
    TokenAmount,
)
from prediction_market_agent_tooling.markets.market_fees import MarketFees
from prediction_market_agent_tooling.markets.omen.data_models import get_bet_outcome
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.omen.omen_contracts import sDaiContract
from prediction_market_agent_tooling.markets.seer.data_models import (
    NewMarketEvent,
    SeerMarket,
    SeerOutcomeEnum,
)
from prediction_market_agent_tooling.markets.seer.seer_contracts import (
    SeerMarketFactory,
)
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.contract import (
    ContractERC20OnGnosisChain,
    init_collateral_token_contract,
    to_gnosis_chain_contract,
)
from prediction_market_agent_tooling.tools.cow.cow_manager import (
    CowManager,
    NoLiquidityAvailableOnCowException,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.tokens.auto_deposit import (
    auto_deposit_collateral_token,
)
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai, xdai_to_wei

# We place a larger bet amount by default than Omen so that cow presents valid quotes.
SEER_TINY_BET_AMOUNT = xdai_type(0.1)


class SeerAgentMarket(AgentMarket):
    currency = Currency.sDai
    wrapped_tokens: list[ChecksumAddress]
    creator: HexAddress
    collateral_token_contract_address_checksummed: ChecksumAddress
    condition_id: HexBytes
    seer_outcomes: dict[SeerOutcomeEnum, int]

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
    ) -> None:
        return store_trades(
            market_id=self.id,
            traded_market=traded_market,
            keys=keys,
            agent_name=agent_name,
        )

    def _convert_bet_amount_into_wei(self, bet_amount: BetAmount) -> Wei:
        if bet_amount.currency == self.currency:
            return xdai_to_wei(xdai_type(bet_amount.amount))
        raise ValueError(
            f"Currencies don't match. Currency bet amount {bet_amount.currency} currency market: {self.currency}"
        )

    def get_buy_token_amount(
        self, bet_amount: BetAmount, direction: bool
    ) -> TokenAmount:
        """Returns number of outcome tokens returned for a given bet expressed in collateral units."""

        outcome_token = self.get_wrapped_token_for_outcome(direction)

        bet_amount_in_wei = self._convert_bet_amount_into_wei(bet_amount=bet_amount)

        quote = CowManager().get_quote(
            buy_token=outcome_token,
            sell_amount=bet_amount_in_wei,
            collateral_token=self.collateral_token_contract_address_checksummed,
        )
        sell_amount = wei_to_xdai(wei_type(quote.quote.buyAmount.root))
        return TokenAmount(amount=sell_amount, currency=bet_amount.currency)

    def get_outcome_str_from_bool(self, outcome: bool) -> OutcomeStr:
        outcome_translated = SeerOutcomeEnum.from_bool(outcome)
        idx = self.seer_outcomes[outcome_translated]
        return OutcomeStr(self.outcomes[idx])

    @staticmethod
    def get_trade_balance(api_keys: APIKeys) -> float:
        return OmenAgentMarket.get_trade_balance(api_keys=api_keys)

    @classmethod
    def get_tiny_bet_amount(cls) -> BetAmount:
        return BetAmount(amount=SEER_TINY_BET_AMOUNT, currency=cls.currency)

    def get_position(self, user_id: str, web3: Web3 | None = None) -> Position | None:
        """
        Fetches position from the user in a given market.
        We ignore the INVALID balances since we are only interested in binary outcomes.
        """

        amounts = {}

        for outcome in [True, False]:
            wrapped_token = self.get_wrapped_token_for_outcome(outcome)

            outcome_token_balance = ContractERC20OnGnosisChain(
                address=wrapped_token
            ).balanceOf(for_address=Web3.to_checksum_address(user_id), web3=web3)
            outcome_str = self.get_outcome_str_from_bool(outcome=outcome)
            amounts[outcome_str] = TokenAmount(
                amount=wei_to_xdai(outcome_token_balance), currency=self.currency
            )

        return Position(market_id=self.id, amounts=amounts)

    @staticmethod
    def get_user_id(api_keys: APIKeys) -> str:
        return OmenAgentMarket.get_user_id(api_keys)

    @staticmethod
    def redeem_winnings(api_keys: APIKeys) -> None:
        # ToDo - implement me (https://github.com/gnosis/prediction-market-agent-tooling/issues/499)
        pass

    @staticmethod
    def verify_operational_balance(api_keys: APIKeys) -> bool:
        return get_total_balance(
            api_keys.public_key,
            # Use `public_key`, not `bet_from_address` because transaction costs are paid from the EOA wallet.
            sum_wxdai=False,
        ) > xdai_type(0.001)

    @staticmethod
    def from_data_model(model: SeerMarket) -> "SeerAgentMarket":
        return SeerAgentMarket(
            id=model.id.hex(),
            description=None,
            question=model.title,
            creator=model.creator,
            created_time=model.created_time,
            outcomes=model.outcomes,
            collateral_token_contract_address_checksummed=model.collateral_token_contract_address_checksummed,
            condition_id=model.conditionId,
            url=model.url,
            close_time=model.close_time,
            wrapped_tokens=[Web3.to_checksum_address(i) for i in model.wrapped_tokens],
            fees=MarketFees.get_zero_fees(),
            outcome_token_pool=None,
            resolution=model.get_resolution_enum(),
            volume=None,
            current_p_yes=model.current_p_yes,
            seer_outcomes=model.outcome_as_enums,
        )

    @staticmethod
    def get_binary_markets(
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[DatetimeUTC] = None,
        excluded_questions: set[str] | None = None,
    ) -> t.Sequence["SeerAgentMarket"]:
        return [
            SeerAgentMarket.from_data_model(m)
            for m in SeerSubgraphHandler().get_binary_markets(
                limit=limit,
                sort_by=sort_by,
                filter_by=filter_by,
            )
        ]

    def has_liquidity_for_outcome(self, outcome: bool) -> bool:
        outcome_token = self.get_wrapped_token_for_outcome(outcome)
        try:
            CowManager().get_quote(
                collateral_token=self.collateral_token_contract_address_checksummed,
                buy_token=outcome_token,
                sell_amount=xdai_to_wei(
                    xdai_type(1)
                ),  # we take 1 xDai as a baseline value for common trades the agents take.
            )
            return True
        except NoLiquidityAvailableOnCowException:
            logger.info(
                f"Could not get a quote for {outcome_token=} {outcome=}, returning no liquidity"
            )
            return False

    def has_liquidity(self) -> bool:
        # We conservatively define a market as having liquidity if it has liquidity for the `True` outcome token AND the `False` outcome token.
        return self.has_liquidity_for_outcome(True) and self.has_liquidity_for_outcome(
            False
        )

    def get_wrapped_token_for_outcome(self, outcome: bool) -> ChecksumAddress:
        outcome_index: int = self.get_outcome_index(get_bet_outcome(outcome))
        outcome_token = self.wrapped_tokens[outcome_index]
        return outcome_token

    def place_bet(
        self,
        outcome: bool,
        amount: BetAmount,
        auto_deposit: bool = True,
        web3: Web3 | None = None,
        api_keys: APIKeys | None = None,
    ) -> str:
        api_keys = api_keys if api_keys is not None else APIKeys()
        if not self.can_be_traded():
            raise ValueError(
                f"Market {self.id} is not open for trading. Cannot place bet."
            )

        # We add an additional check below since we want to be certain that liquidity exists for the outcome token
        # being traded.
        if not self.has_liquidity_for_outcome(outcome):
            raise ValueError(
                f"Market {self.id} does not have liquidity for this {outcome=}"
            )
        if amount.currency != self.currency:
            raise ValueError(f"Seer bets are made in xDai. Got {amount.currency}.")

        collateral_contract = sDaiContract()
        if auto_deposit:
            # We convert the deposit amount (in sDai) to assets in order to convert.
            asset_amount = collateral_contract.convertToAssets(
                xdai_to_wei(xdai_type(amount.amount))
            )
            auto_deposit_collateral_token(
                collateral_contract, asset_amount, api_keys, web3
            )

        # We require that amount is given in sDAI.
        collateral_balance = get_balances(address=api_keys.bet_from_address, web3=web3)
        if collateral_balance.sdai < amount.amount:
            raise ValueError(
                f"Balance {collateral_balance.sdai} not enough for bet size {amount.amount}"
            )

        outcome_token = self.get_wrapped_token_for_outcome(outcome)
        #  Sell sDAI using token address
        order_metadata = CowManager().swap(
            amount=xdai_type(amount.amount),
            sell_token=collateral_contract.address,
            buy_token=Web3.to_checksum_address(outcome_token),
            api_keys=api_keys,
            web3=web3,
        )

        return order_metadata.uid.root


def seer_create_market_tx(
    api_keys: APIKeys,
    initial_funds: xDai,
    question: str,
    opening_time: DatetimeUTC,
    language: str,
    outcomes: list[str],
    auto_deposit: bool,
    category: str,
    min_bond_xdai: xDai,
    web3: Web3 | None = None,
) -> ChecksumAddress:
    web3 = web3 or SeerMarketFactory.get_web3()  # Default to Gnosis web3.
    initial_funds_wei = xdai_to_wei(initial_funds)

    factory_contract = SeerMarketFactory()
    collateral_token_address = factory_contract.collateral_token(web3=web3)
    collateral_token_contract = to_gnosis_chain_contract(
        init_collateral_token_contract(collateral_token_address, web3)
    )

    if auto_deposit:
        auto_deposit_collateral_token(
            collateral_token_contract=collateral_token_contract,
            api_keys=api_keys,
            amount_wei=initial_funds_wei,
            web3=web3,
        )

    # In case of ERC4626, obtained (for example) sDai out of xDai could be lower than the `amount_wei`, so we need to handle it.
    initial_funds_in_shares = collateral_token_contract.get_in_shares(
        amount=initial_funds_wei, web3=web3
    )

    # Approve the market maker to withdraw our collateral token.
    collateral_token_contract.approve(
        api_keys=api_keys,
        for_address=factory_contract.address,
        amount_wei=initial_funds_in_shares,
        web3=web3,
    )

    # Create the market.
    params = factory_contract.build_market_params(
        market_question=question,
        outcomes=outcomes,
        opening_time=opening_time,
        language=language,
        category=category,
        min_bond_xdai=min_bond_xdai,
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
