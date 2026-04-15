"""User-side: burn wrapped ERC-20 back into the underlying CTF ERC-1155.

Inverse of the `--wrap-output` leg in `polymarket_migrate_position.py`.
Calls `Wrapped1155Factory.unwrap(...)` which burns the user's ERC-20 and
returns the original ERC-1155 outcome token (e.g. stata-YES).

Reads BET_FROM_PRIVATE_KEY from .env; never routes via Safe.

Usage:
    python scripts/polymarket_user_unwrap_erc20.py \\
        --condition-id 0x... \\
        --outcome YES \\
        --amount 0.005
"""

import os

import typer
from dotenv import load_dotenv

from prediction_market_agent_tooling.config import APIKeys, RPCConfig
from prediction_market_agent_tooling.gtypes import (
    HexBytes,
    OutcomeWei,
    private_key_type,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.polymarket.migration import (
    _default_wrap_metadata,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
    StataPolUSDCnContract,
    Wrapped1155Contract,
    Wrapped1155FactoryContract,
)


def user_unwrap_erc20(
    condition_id: str = typer.Option(..., help="0x-prefixed Polymarket conditionId."),
    outcome: str = typer.Option("YES", help="Outcome side: YES or NO."),
    amount: float = typer.Option(..., help="ERC-20 amount to burn (e.g. 0.005)."),
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
    stata = StataPolUSDCnContract()
    factory = Wrapped1155FactoryContract()
    cond = HexBytes(condition_id)
    amount_wei = OutcomeWei(int(amount * 1e6))

    if outcome.upper() == "YES":
        outcome_index = 0
    elif outcome.upper() == "NO":
        outcome_index = 1
    else:
        raise typer.BadParameter("--outcome must be YES or NO.")

    index_set = 1 << outcome_index
    target_position_id = ctf._position_id_for(stata.address, cond, index_set, web3=web3)
    name, symbol, decimals = _default_wrap_metadata(cond, outcome_index)
    metadata = Wrapped1155FactoryContract.encode_metadata(name, symbol, decimals)
    wrapped_address = factory.get_wrapped_1155(
        multi_token=ctf.address,
        token_id=target_position_id,
        data=metadata,
        web3=web3,
    )
    wrapped = Wrapped1155Contract(address=wrapped_address)

    balance = wrapped.balanceOf(user_keys.bet_from_address, web3=web3)
    if balance.value < amount_wei.value:
        raise typer.BadParameter(
            f"User holds {balance} wrapped ERC-20; asked to burn {amount_wei}."
        )

    logger.info(
        f"Unwrapping {amount_wei} of {wrapped_address} ({name}/{symbol}) "
        f"back to CTF ERC-1155 positionId={target_position_id}."
    )
    receipt = factory.send(
        api_keys=user_keys,
        function_name="unwrap",
        function_params=[
            ctf.address,
            target_position_id,
            amount_wei.value,
            user_keys.bet_from_address,
            metadata,
        ],
        web3=web3,
    )
    logger.info(f"Unwrap tx: {receipt['transactionHash'].hex()}")
    new_bal = ctf.balanceOf(
        from_address=user_keys.bet_from_address,
        position_id=target_position_id,
        web3=web3,
    )
    logger.info(f"User now holds {new_bal} raw ERC-1155 (stata-{outcome}).")


if __name__ == "__main__":
    typer.run(user_unwrap_erc20)
