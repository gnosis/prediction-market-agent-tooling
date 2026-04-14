"""Wrap the operator Safe's USDC native into stataPolUSDCn shares.

Prerequisite: USDC native (0x3c499c54…) is already in the Safe — send it
there manually first (e.g. from your trading wallet on Polygonscan or via
your usual on/off-ramp).

This script does:
    Safe -> USDC.approve(stata_vault, amount)
    Safe -> stata.deposit(amount, receiver=safe)
which mints stata shares to the Safe. ERC-4626 wrap; no DEX.

Run with the operator's APIKeys env (BET_FROM_PRIVATE_KEY + SAFE_ADDRESS).

Usage:
    python scripts/polymarket_safe_fund_stata.py --usdc-amount 100
"""

import typer

from prediction_market_agent_tooling.config import APIKeys, RPCConfig
from prediction_market_agent_tooling.gtypes import Wei
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    StataPolUSDCnContract,
    USDCContract,
)


def fund_safe_with_stata(
    usdc_amount: float = typer.Option(
        ..., help="USDC native amount to wrap into stata shares (e.g. 100)."
    ),
) -> None:
    api_keys = APIKeys()
    if api_keys.safe_address_checksum is None:
        raise typer.BadParameter(
            "SAFE_ADDRESS env var must be set to the operator Safe address."
        )

    web3 = RPCConfig().get_polygon_web3()
    safe_address = api_keys.safe_address_checksum
    usdc = USDCContract()
    stata = StataPolUSDCnContract()

    usdc_wei = Wei(int(usdc_amount * 1e6))
    usdc_balance = usdc.balanceOf(for_address=safe_address, web3=web3)
    if usdc_balance.value < usdc_wei.value:
        raise typer.BadParameter(
            f"Safe holds {usdc_balance} USDC native; need {usdc_wei}. "
            "Send USDC to the Safe first."
        )

    stata_before = stata.balanceOf(for_address=safe_address, web3=web3)
    logger.info(
        f"Safe {safe_address}: USDC={usdc_balance} stata_before={stata_before}. "
        f"Wrapping {usdc_wei} USDC -> stata."
    )

    stata.deposit_asset_token(asset_value=usdc_wei, api_keys=api_keys, web3=web3)

    stata_after = stata.balanceOf(for_address=safe_address, web3=web3)
    logger.info(
        f"Wrap complete. stata_after={stata_after} "
        f"(gained {stata_after.value - stata_before.value} shares)."
    )


if __name__ == "__main__":
    typer.run(fund_safe_with_stata)
