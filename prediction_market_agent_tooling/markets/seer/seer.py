from eth_typing import ChecksumAddress
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xDai
from prediction_market_agent_tooling.markets.seer.seer_contracts import (
    SeerMarketFactory,
)
from prediction_market_agent_tooling.tools.contract import (
    to_gnosis_chain_contract,
    init_collateral_token_contract,
    auto_deposit_collateral_token,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


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
    factory_contract.create_categorical_market(
        api_keys=api_keys, params=params, web3=web3
    )
    # ToDo - Add liquidity to market on Swapr (https://github.com/gnosis/prediction-market-agent-tooling/issues/497)

    # Fetch newly created market
    count_markets = factory_contract.market_count(web3=web3)
    new_market_address = factory_contract.market_at_index(count_markets - 1, web3=web3)
    return new_market_address
