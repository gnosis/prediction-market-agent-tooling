import typing as t

from eth_typing import ChecksumAddress
from web3 import Web3
from web3.types import TxReceipt

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    xDai,
    xdai_type,
    HexAddress,
    HexBytes,
    Probability,
    OutcomeStr,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
    ProcessedTradedMarket,
    ProcessedMarket,
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
    SeerMarket,
    NewMarketEvent,
)
from prediction_market_agent_tooling.markets.seer.seer_contracts import (
    SeerMarketFactory,
)
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.contract import (
    auto_deposit_collateral_token,
    init_collateral_token_contract,
    to_gnosis_chain_contract,
)
from prediction_market_agent_tooling.tools.cow.cow_order import swap_tokens_waiting
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


class SeerAgentMarket(AgentMarket):
    # ToDo - Turn into HexAddress
    id: str
    currency = Currency.sDai
    wrapped_tokens: list[ChecksumAddress]
    creator: HexAddress
    collateral_token_contract_address_checksummed: ChecksumAddress
    condition_id: HexBytes
    # No pools upon market creation
    # volume: float | None = None
    # outcome_token_pool = None

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

    def get_buy_token_amount(
        self, bet_amount: BetAmount, direction: bool
    ) -> TokenAmount:
        # ToDo - Calculate this from the pools associated to this market.
        # Below we simply return the same amount for simplicity, until the solution is properly implemented.
        return TokenAmount(amount=bet_amount.amount, currency=bet_amount.currency)

    @staticmethod
    def get_outcome_str_from_bool(outcome: bool) -> OutcomeStr:
        return OmenAgentMarket.get_outcome_str_from_bool(outcome=outcome)

    @staticmethod
    def get_trade_balance(api_keys: APIKeys) -> float:
        return OmenAgentMarket.get_trade_balance(api_keys=api_keys)

    @classmethod
    def get_tiny_bet_amount(cls) -> BetAmount:
        return OmenAgentMarket.get_tiny_bet_amount()

    def get_position(self, user_id: str) -> Position | None:
        # ToDo - Fetch from Swapr pools, Swapr v3 pools, or Uni v3 pools
        return None

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
            # ToDo - Get from cow
            current_p_yes=Probability(0.123),
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

        if amount.currency != self.currency:
            raise ValueError(f"Seer bets are made in xDai. Got {amount.currency}.")

        # We require that amount is given in sDAI.
        collateral_balance = get_balances(address=api_keys.bet_from_address, web3=web3)
        if collateral_balance.sdai < amount.amount:
            raise ValueError(
                f"Balance {collateral_balance.sdai} not enough for bet size {amount.amount}"
            )

        collateral_contract = sDaiContract()

        if auto_deposit:
            # We convert the deposit amount (in sDai) to assets in order to convert.
            asset_amount = collateral_contract.convertToAssets(
                xdai_to_wei(xdai_type(amount.amount))
            )
            auto_deposit_collateral_token(
                collateral_contract, asset_amount, api_keys, web3
            )

        # Get the index of the outcome we want to buy.
        outcome_index: int = self.get_outcome_index(get_bet_outcome(outcome))
        #  From wrapped tokens, get token address
        outcome_token = self.wrapped_tokens[outcome_index]
        #  Sell sDAI using token address
        order_metadata = swap_tokens_waiting(
            amount=xdai_type(amount.amount),
            sell_token=collateral_contract.address,
            buy_token=Web3.to_checksum_address(outcome_token),
            api_keys=api_keys,
            web3=web3,
        )
        logger.info(
            f"Purchased {outcome_token} in exchange for {collateral_contract.address}. Order details {order_metadata}"
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
