"""User-side: approve the operator Safe to move ERC1155 outcome tokens.

The migration batch's "pull" leg is `safeTransferFrom(user, safe, ...)`,
which requires the user to have called `setApprovalForAll(safe, true)` on
the Polymarket CTF beforehand. This script does exactly that — once.

The user runs this themselves with their own private key. It is one tx,
no Safe involved on the user side. Idempotent: a no-op if already approved.

Usage:
    python scripts/polymarket_approve_safe_for_user.py \\
        --user-private-key 0x... \\
        --safe-address 0x...
"""

import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys, RPCConfig
from prediction_market_agent_tooling.gtypes import private_key_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
)


def approve_safe_for_user(
    user_private_key: str = typer.Option(
        ..., help="User EOA private key (signs the approval tx)."
    ),
    safe_address: str = typer.Option(
        ..., help="Operator Safe address to approve as ERC1155 operator."
    ),
) -> None:
    web3 = RPCConfig().get_polygon_web3()
    user_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(user_private_key),
        SAFE_ADDRESS=None,
    )
    safe_addr = Web3.to_checksum_address(safe_address)
    ctf = PolymarketConditionalTokenContract()

    if ctf.isApprovedForAll(
        owner=user_keys.bet_from_address, for_address=safe_addr, web3=web3
    ):
        logger.info(
            f"User {user_keys.bet_from_address} already approved Safe {safe_addr}. "
            "Nothing to do."
        )
        return

    logger.info(
        f"Approving Safe {safe_addr} as ERC1155 operator for user "
        f"{user_keys.bet_from_address}…"
    )
    receipt = ctf.setApprovalForAll(
        api_keys=user_keys, for_address=safe_addr, approve=True, web3=web3
    )
    logger.info(f"Approved. tx={receipt['transactionHash'].hex()}")


if __name__ == "__main__":
    typer.run(approve_safe_for_user)
