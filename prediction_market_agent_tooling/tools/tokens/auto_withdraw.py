from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Wei
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.contract import (
    ContractERC20BaseClass,
    ContractERC4626BaseClass,
)
from prediction_market_agent_tooling.tools.cow.cow_order import (
    get_buy_token_amount,
    swap_tokens_waiting,
)
from prediction_market_agent_tooling.tools.tokens.main_token import KEEPING_ERC20_TOKEN
from prediction_market_agent_tooling.tools.utils import should_not_happen
from prediction_market_agent_tooling.tools.web3_utils import (
    remove_fraction,
    wei_to_xdai,
)


def auto_withdraw_collateral_token(
    collateral_token_contract: ContractERC20BaseClass,
    amount_wei: Wei,
    api_keys: APIKeys,
    web3: Web3 | None = None,
    slippage: float = 0.001,
) -> None:
    # Small slippage as exact exchange rate constantly changes and we don't care about small differences.
    amount_wei = remove_fraction(
        amount_wei,
        slippage,
    )

    if not amount_wei:
        logger.warning(
            f"Amount to withdraw is zero, skipping withdrawal of {collateral_token_contract.symbol_cached(web3)}."
        )
        return

    if collateral_token_contract.address == KEEPING_ERC20_TOKEN.address:
        # Do nothing, as this is the token we want to keep.
        logger.info(
            f"Collateral token {collateral_token_contract.symbol_cached(web3)} is the same as KEEPING_ERC20_TOKEN. Not withdrawing."
        )
        return
    elif (
        isinstance(collateral_token_contract, ContractERC4626BaseClass)
        and collateral_token_contract.get_asset_token_contract().address
        == KEEPING_ERC20_TOKEN.address
    ):
        # If the ERC4626 is backed by KEEPING_ERC20_TOKEN, we can withdraw it directly, no need to go through DEX.
        logger.info(
            f"Withdrawing {wei_to_xdai(amount_wei)} from {collateral_token_contract.symbol_cached(web3)} into {KEEPING_ERC20_TOKEN.symbol_cached(web3)}"
        )
        collateral_token_contract.withdraw_in_shares(
            api_keys,
            amount_wei,
            web3=web3,
        )
    elif isinstance(collateral_token_contract, ContractERC20BaseClass):
        logger.info(
            f"Swapping {wei_to_xdai(amount_wei)} {collateral_token_contract.symbol_cached(web3)} into {KEEPING_ERC20_TOKEN.symbol_cached(web3)}"
        )
        # Otherwise, DEX will handle the rest of token swaps.
        # First, convert `amount_wei` from xDai-based value into the collateral token-based value.
        collateral_amount_wei = get_buy_token_amount(
            amount_wei,
            KEEPING_ERC20_TOKEN.address,
            collateral_token_contract.address,
        )
        # And then sell it.
        swap_tokens_waiting(
            amount_wei=collateral_amount_wei,
            sell_token=collateral_token_contract.address,
            buy_token=KEEPING_ERC20_TOKEN.address,
            api_keys=api_keys,
            web3=web3,
        )
    else:
        should_not_happen("Unsupported ERC20 contract type.")
