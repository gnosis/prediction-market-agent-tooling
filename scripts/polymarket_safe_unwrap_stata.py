"""Burn stata shares from the operator Safe and receive USDC native back.

Inverse of polymarket_safe_fund_stata.py. Calls
`stata.redeem(shares, receiver=safe, owner=safe)` so the Safe gets USDC
native equal to `convertToAssets(shares)`. No DEX, just an ERC-4626 unwrap.

Run with the operator's APIKeys env (BET_FROM_PRIVATE_KEY + SAFE_ADDRESS).

Usage:
    python scripts/polymarket_safe_unwrap_stata.py --shares 0.876694
    python scripts/polymarket_safe_unwrap_stata.py --all
"""

import typer

from prediction_market_agent_tooling.config import APIKeys, RPCConfig
from prediction_market_agent_tooling.gtypes import Wei
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    StataPolUSDCnContract,
    USDCContract,
)


def unwrap_safe_stata(
    shares: float = typer.Option(
        0.0, help="Shares to burn (e.g. 0.876694). Ignored if --all."
    ),
    all_shares: bool = typer.Option(
        False, "--all", help="Burn the Safe's entire stata balance."
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

    stata_balance = stata.balanceOf(for_address=safe_address, web3=web3)
    if all_shares:
        shares_wei = Wei(stata_balance.value)
    else:
        if shares <= 0:
            raise typer.BadParameter("Pass --all or a positive --shares value.")
        shares_wei = Wei(int(shares * 1e6))

    if shares_wei.value <= 0:
        raise typer.BadParameter("Nothing to unwrap — Safe holds 0 stata.")
    if shares_wei.value > stata_balance.value:
        raise typer.BadParameter(
            f"Safe holds {stata_balance} stata; cannot burn {shares_wei}."
        )

    expected_usdc = stata.convertToAssets(shares_wei, web3=web3)
    usdc_before = usdc.balanceOf(for_address=safe_address, web3=web3)
    logger.info(
        f"Safe {safe_address}: stata={stata_balance} USDC_before={usdc_before}. "
        f"Burning {shares_wei} stata -> ~{expected_usdc} USDC native."
    )

    stata.withdraw_in_shares(api_keys=api_keys, shares_wei=shares_wei, web3=web3)

    usdc_after = usdc.balanceOf(for_address=safe_address, web3=web3)
    stata_after = stata.balanceOf(for_address=safe_address, web3=web3)
    logger.info(
        f"Unwrap complete. USDC_after={usdc_after} stata_after={stata_after} "
        f"(gained {usdc_after.value - usdc_before.value} USDC)."
    )


if __name__ == "__main__":
    typer.run(unwrap_safe_stata)
