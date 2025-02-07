import typing as t

from eth_typing import ChecksumAddress
from web3 import Web3
from web3.types import TxReceipt

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xDai, xdai_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import BetAmount, Currency
from prediction_market_agent_tooling.markets.omen.omen_contracts import sDaiContract
from prediction_market_agent_tooling.markets.seer.data_models import (
    NewMarketEvent,
    get_bet_outcome,
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
    currency = Currency.sDai
    wrapped_tokens: list[ChecksumAddress]

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
                created_after=created_after,
            )
        ]

    def place_bet(
        self,
        outcome: bool,
        amount: BetAmount,
        auto_deposit: bool = True,
        web3: Web3 | None = None,
        api_keys: APIKeys | None = None,
        **kwargs: t.Any,
    ) -> str:
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

        # ToDo
        #  Match outcome index with outcomes
        # Get the index of the outcome we want to buy.
        outcome_index: int = self.get_outcome_index(get_bet_outcome(outcome))
        #  From wrapped tokens, get token address
        outcome_token = self.wrapped_tokens[outcome_index]
        #  Sell sDAI using token address
        swap_result = swap_tokens_waiting(
            amount=xdai_type(amount.amount),
            sell_token=collateral_contract.address,
            buy_token=Web3.to_checksum_address(outcome_token),
            api_keys=api_keys,
            web3=web3,
        )
        logger.info(
            f"Purchased {outcome_token} in exchange for {collateral_contract.address}. Swap result {swap_result}"
        )


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
