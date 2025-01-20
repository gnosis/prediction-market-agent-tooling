from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Wei, wei_type
from prediction_market_agent_tooling.tools.contract import (
    ContractDepositableWrapperERC20BaseClass,
    ContractERC20BaseClass,
    ContractERC20OnGnosisChain,
    ContractERC4626BaseClass,
)
from prediction_market_agent_tooling.tools.cow.cow_order import (
    get_buy_token_amount,
    swap_tokens_waiting,
)
from prediction_market_agent_tooling.tools.tokens.main_token import KEEPING_ERC20_TOKEN
from prediction_market_agent_tooling.tools.utils import should_not_happen


def auto_deposit_collateral_token(
    collateral_token_contract: ContractERC20BaseClass,
    amount_wei: Wei,
    api_keys: APIKeys,
    web3: Web3 | None = None,
) -> None:
    if isinstance(collateral_token_contract, ContractERC4626BaseClass):
        auto_deposit_erc4626(collateral_token_contract, amount_wei, api_keys, web3)

    elif isinstance(
        collateral_token_contract, ContractDepositableWrapperERC20BaseClass
    ):
        auto_deposit_depositable_wrapper_erc20(
            collateral_token_contract, amount_wei, api_keys, web3
        )

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

    # If the asset token is Depositable Wrapper ERC-20, we can deposit it, in case we don't have enough.
    if (
        collateral_token_contract.get_asset_token_balance(for_address, web3)
        < asset_amount_wei
    ):
        if isinstance(asset_token_contract, ContractDepositableWrapperERC20BaseClass):
            auto_deposit_depositable_wrapper_erc20(
                asset_token_contract, asset_amount_wei, api_keys, web3
            )
        elif isinstance(collateral_token_contract, ContractERC20BaseClass):
            auto_deposit_erc20(asset_token_contract, asset_amount_wei, api_keys, web3)
        else:
            raise ValueError(
                "Not enough of the asset token, but it's not a depositable wrapper token that we can deposit automatically."
            )

    # Finally, we can deposit the asset token into the erc4626 vault.
    collateral_token_balance_in_assets = collateral_token_contract.convertToAssets(
        collateral_token_balance_in_shares, web3
    )
    left_to_deposit = Wei(asset_amount_wei - collateral_token_balance_in_assets)
    collateral_token_contract.deposit_asset_token(left_to_deposit, api_keys, web3)


def auto_deposit_erc20(
    collateral_token_contract: ContractERC20BaseClass,
    amount_xdai_wei: Wei,
    api_keys: APIKeys,
    web3: Web3 | None,
) -> None:
    # How much it is in the other token (collateral token).
    collateral_amount_wei = get_buy_token_amount(
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
    if amount_to_sell_wei > ContractERC20OnGnosisChain(
        address=KEEPING_ERC20_TOKEN.address
    ).balanceOf(api_keys.bet_from_address):
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
