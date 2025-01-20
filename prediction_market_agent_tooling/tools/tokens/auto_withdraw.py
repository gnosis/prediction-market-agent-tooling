from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Wei
from prediction_market_agent_tooling.tools.contract import (
    ContractDepositableWrapperERC20BaseClass,
    ContractERC20BaseClass,
    ContractERC4626BaseClass,
)
from prediction_market_agent_tooling.tools.cow.cow_order import swap_tokens_waiting
from prediction_market_agent_tooling.tools.tokens.main_token import KEEPING_ERC20_TOKEN
from prediction_market_agent_tooling.tools.utils import should_not_happen
from prediction_market_agent_tooling.tools.web3_utils import remove_fraction


def auto_withdraw_collateral_token(
    collateral_token_contract: ContractERC20BaseClass,
    amount_wei: Wei,
    api_keys: APIKeys,
    web3: Web3 | None = None,
    slippage: float = 0.001,
) -> None:
    amount_wei = remove_fraction(
        amount_wei,
        slippage,
    )

    if collateral_token_contract.address == KEEPING_ERC20_TOKEN.address:
        # Do nothing, as this is the token we want to keep.
        return
    elif isinstance(collateral_token_contract, ContractERC4626BaseClass) or isinstance(
        collateral_token_contract, ContractDepositableWrapperERC20BaseClass
    ):
        collateral_token_contract.withdraw(
            api_keys,
            amount_wei,
            web3=web3,
        )
    elif isinstance(collateral_token_contract, ContractERC20BaseClass):
        swap_tokens_waiting(
            amount_wei=amount_wei,
            sell_token=collateral_token_contract.address,
            buy_token=KEEPING_ERC20_TOKEN.address,
            api_keys=api_keys,
            web3=web3,
        )
    else:
        should_not_happen("Unsupported ERC20 contract type.")
