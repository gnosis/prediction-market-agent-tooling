from eth_typing.evm import ChecksumAddress
from web3 import Web3
from web3.types import Wei

from prediction_market_agent_tooling.config import RPCConfig
from prediction_market_agent_tooling.gtypes import ChecksumAddress, Wei
from prediction_market_agent_tooling.tools.contract import (
    ContractERC4626BaseClass,
    init_collateral_token_contract,
    to_gnosis_chain_contract,
)
from prediction_market_agent_tooling.tools.cow.cow_order import get_buy_token_amount


def convert_to_another_token(
    amount: Wei,
    from_token: ChecksumAddress,
    to_token: ChecksumAddress,
    web3: Web3 | None = None,
) -> Wei:
    web3 = web3 or RPCConfig().get_web3()
    from_token_contract = to_gnosis_chain_contract(
        init_collateral_token_contract(from_token, web3)
    )
    to_token_contract = to_gnosis_chain_contract(
        init_collateral_token_contract(to_token, web3)
    )

    if from_token == to_token:
        return amount

    elif (
        isinstance(to_token_contract, ContractERC4626BaseClass)
        and to_token_contract.get_asset_token_contract().address == from_token
    ):
        return to_token_contract.convertToShares(amount)

    elif (
        isinstance(from_token_contract, ContractERC4626BaseClass)
        and from_token_contract.get_asset_token_contract().address == to_token
    ):
        return from_token_contract.convertToAssets(amount)

    else:
        return get_buy_token_amount(
            amount,
            from_token,
            to_token,
        )
