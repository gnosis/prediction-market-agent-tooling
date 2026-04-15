"""User-side: mint a USDC.e-backed outcome full set on Polymarket's CTF.

Splits `--amount` USDC.e into N outcome ERC1155s (YES + NO for binary
markets) keyed to `--condition-id`. The user EOA ends up holding both
sides of the position in equal amount. Useful for demos that need a
"user with a Polymarket position" without going through the CLOB.

Reads BET_FROM_PRIVATE_KEY from .env; never routes via Safe even if
SAFE_ADDRESS is set.

Usage:
    python scripts/polymarket_user_mint_full_set.py \\
        --condition-id 0x... \\
        --amount 0.005 \\
        [--outcome-slot-count 2]
"""

import os

import typer
from dotenv import load_dotenv

from prediction_market_agent_tooling.config import APIKeys, RPCConfig
from prediction_market_agent_tooling.gtypes import HexBytes, Wei, private_key_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
    USDCeContract,
)


def user_mint_full_set(
    condition_id: str = typer.Option(..., help="0x-prefixed Polymarket conditionId."),
    amount: float = typer.Option(
        ..., help="USDC.e amount to lock (each outcome leg gets this many shares)."
    ),
    outcome_slot_count: int = 2,
) -> None:
    load_dotenv()
    private_key = os.environ.get("BET_FROM_PRIVATE_KEY")
    if not private_key:
        raise typer.BadParameter("Set BET_FROM_PRIVATE_KEY in .env.")

    user_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(private_key),
        SAFE_ADDRESS=None,
    )
    web3 = RPCConfig().get_polygon_web3()
    ctf = PolymarketConditionalTokenContract()
    usdce = USDCeContract()
    cond = HexBytes(condition_id)
    amount_wei = Wei(int(amount * 1e6))

    usdce_balance = usdce.balanceOf(user_keys.bet_from_address, web3=web3)
    if usdce_balance.value < amount_wei.value:
        raise typer.BadParameter(
            f"User holds {usdce_balance} USDC.e; need {amount_wei}."
        )

    logger.info(
        f"User {user_keys.bet_from_address}: minting full set of {amount_wei} "
        f"on cond={condition_id} (USDC.e collateral)."
    )
    receipt = ctf.mint_full_set(
        api_keys=user_keys,
        collateral_token=usdce,
        condition_id=cond,
        amount=amount_wei,
        outcome_slot_count=outcome_slot_count,
        web3=web3,
    )

    balances = []
    for i in range(outcome_slot_count):
        position_id = ctf._position_id_for(usdce.address, cond, 1 << i, web3=web3)
        bal = ctf.balanceOf(user_keys.bet_from_address, position_id, web3=web3)
        balances.append(bal.value)
    logger.info(
        f"Mint complete. tx={receipt['transactionHash'].hex()} "
        f"outcome balances={balances}"
    )


if __name__ == "__main__":
    typer.run(user_mint_full_set)
