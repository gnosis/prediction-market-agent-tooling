from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Wei, wei_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.contract import (
    ContractDepositableWrapperERC20BaseClass,
    ContractERC20BaseClass,
    ContractERC20OnGnosisChain,
    ContractERC4626BaseClass,
)
from prediction_market_agent_tooling.tools.cow.cow_order import swap_tokens_waiting
from prediction_market_agent_tooling.tools.tokens.main_token import KEEPING_ERC20_TOKEN
from prediction_market_agent_tooling.tools.tokens.token_utils import (
    convert_to_another_token,
)
from prediction_market_agent_tooling.tools.utils import should_not_happen
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai


def auto_deposit_collateral_token(
    collateral_token_contract: ContractERC20BaseClass,
    amount_wei: Wei,
    api_keys: APIKeys,
    web3: Web3 | None = None,
) -> None:
    if isinstance(collateral_token_contract, ContractDepositableWrapperERC20BaseClass):
        # In this case, we can use deposit function directly, no need to go through DEX.
        auto_deposit_depositable_wrapper_erc20(
            collateral_token_contract, amount_wei, api_keys, web3
        )

    elif isinstance(collateral_token_contract, ContractERC4626BaseClass):
        auto_deposit_erc4626(collateral_token_contract, amount_wei, api_keys, web3)

    elif isinstance(collateral_token_contract, ContractERC20BaseClass):
        auto_deposit_erc20(collateral_token_contract, amount_wei, api_keys, web3)

    else:
        should_not_happen("Unsupported ERC20 contract type.")


def auto_deposit_depositable_wrapper_erc20(
    collateral_token_contract: ContractDepositableWrapperERC20BaseClass,
    amount_wei: Wei,
    api_keys: APIKeys,
    web3: Web3 | None,
) -> None:
    collateral_token_balance = collateral_token_contract.balanceOf(
        for_address=api_keys.bet_from_address, web3=web3
    )

    # If we have enough of the collateral token, we don't need to deposit.
    if collateral_token_balance >= amount_wei:
        return

    # If we don't have enough, we need to deposit the difference.
    left_to_deposit = Wei(amount_wei - collateral_token_balance)
    logger.info(
        f"Depositing {wei_to_xdai(left_to_deposit)} {collateral_token_contract.symbol()}."
    )
    collateral_token_contract.deposit(api_keys, left_to_deposit, web3=web3)


def auto_deposit_erc4626(
    collateral_token_contract: ContractERC4626BaseClass,
    asset_amount_wei: Wei,
    api_keys: APIKeys,
    web3: Web3 | None,
) -> None:
    for_address = api_keys.bet_from_address
    collateral_token_balance_in_shares = collateral_token_contract.balanceOf(
        for_address=for_address, web3=web3
    )
    asset_amount_wei_in_shares = collateral_token_contract.convertToShares(
        asset_amount_wei, web3
    )

    # If we have enough shares, we don't need to deposit.
    if collateral_token_balance_in_shares >= asset_amount_wei_in_shares:
        return

    # If we need to deposit into erc4626, we first need to have enough of the asset token.
    asset_token_contract = collateral_token_contract.get_asset_token_contract(web3=web3)

    if isinstance(asset_token_contract, ContractDepositableWrapperERC20BaseClass):
        # If the asset token is Depositable Wrapper ERC-20, we don't need to go through DEX.
        # First, calculate how much of asset token we need to deposit into the vault.
        collateral_token_balance_in_assets = collateral_token_contract.convertToAssets(
            collateral_token_balance_in_shares, web3
        )
        left_to_deposit = Wei(asset_amount_wei - collateral_token_balance_in_assets)
        if (
            collateral_token_contract.get_asset_token_balance(for_address, web3)
            < left_to_deposit
        ):
            # If we don't have enough of asset token to deposit into the vault, deposit that one first.
            auto_deposit_depositable_wrapper_erc20(
                asset_token_contract, left_to_deposit, api_keys, web3
            )
        # And finally, we can deposit the asset token into the erc4626 vault directly as well, without DEX.
        collateral_token_contract.deposit_asset_token(left_to_deposit, api_keys, web3)

    else:
        # Otherwise, we need to go through DEX.
        auto_deposit_erc20(collateral_token_contract, asset_amount_wei, api_keys, web3)


def auto_deposit_erc20(
    collateral_token_contract: ContractERC20BaseClass,
    amount_xdai_wei: Wei,
    api_keys: APIKeys,
    web3: Web3 | None,
) -> None:
    # How much it is in the other token (collateral token).
    collateral_amount_wei = convert_to_another_token(
        amount_xdai_wei,
        KEEPING_ERC20_TOKEN.address,
        collateral_token_contract.address,
    )
    # How much do we have already in the other token (collateral token).
    collateral_balance_wei = collateral_token_contract.balanceOf(
        api_keys.bet_from_address
    )
    # Amount of collateral token remaining to get.
    remaining_to_get_in_collateral_wei = max(
        0, collateral_amount_wei - collateral_balance_wei
    )
    if not remaining_to_get_in_collateral_wei:
        return
    # Estimate of how much of the source token we need to sell in order to fill the remaining collateral amount, with 1% slippage to be sure.
    amount_to_sell_wei = wei_type(
        (remaining_to_get_in_collateral_wei * amount_xdai_wei)
        / collateral_amount_wei
        * 1.01
    )
    # If we don't have enough of the source token.
    if amount_to_sell_wei > ContractERC20OnGnosisChain(
        address=KEEPING_ERC20_TOKEN.address
    ).balanceOf(api_keys.bet_from_address):
        # Try to deposit it, if it's depositable token (like Wrapped xDai, agent could have xDai).
        if isinstance(KEEPING_ERC20_TOKEN, ContractDepositableWrapperERC20BaseClass):
            auto_deposit_depositable_wrapper_erc20(
                KEEPING_ERC20_TOKEN, amount_to_sell_wei, api_keys, web3
            )
        else:
            raise ValueError(
                "Not enough of the source token to sell to get the desired amount of the collateral token."
            )
    swap_tokens_waiting(
        amount_wei=amount_to_sell_wei,
        sell_token=KEEPING_ERC20_TOKEN.address,
        buy_token=collateral_token_contract.address,
        api_keys=api_keys,
        web3=web3,
    )
