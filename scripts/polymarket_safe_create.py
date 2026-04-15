"""Deploy an operator Safe on Polygon for the position-migration demo.

Thin wrapper over `create_safe_for_agent` that defaults to the Polygon RPC.
The deployed Safe will be the operator that holds stata + the user's USDC.e
outcome tokens. Save the printed Safe address — the other migration scripts
need it as their SAFE_ADDRESS env var.

Reads BET_FROM_PRIVATE_KEY from .env by default; pass --from-private-key
to override.

Usage:
    python scripts/polymarket_safe_create.py          # uses BET_FROM_PRIVATE_KEY
    python scripts/polymarket_safe_create.py --from-private-key 0x...
    python scripts/polymarket_safe_create.py [--salt-nonce 42] [--fund-amount-pol 1]
"""

import os
import secrets

import typer
from dotenv import load_dotenv
from eth_account import Account
from eth_typing import URI
from pydantic import SecretStr
from safe_eth.eth import EthereumClient

from prediction_market_agent_tooling.gtypes import PrivateKey, Wei, xDai
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.safe import create_safe
from prediction_market_agent_tooling.tools.web3_utils import send_xdai_to


def deploy_polymarket_operator_safe(
    from_private_key: str | None = typer.Option(
        None, help="Override BET_FROM_PRIVATE_KEY from .env."
    ),
    rpc_url: str | None = None,
    salt_nonce: int | None = None,
    fund_safe: bool = True,
    fund_amount_pol: int = 1,
) -> None:
    load_dotenv()
    if from_private_key is None:
        env_key = os.environ.get("BET_FROM_PRIVATE_KEY")
        if not env_key:
            raise typer.BadParameter(
                "Set BET_FROM_PRIVATE_KEY in .env or pass --from-private-key."
            )
        from_private_key = env_key
    salt_nonce = salt_nonce or secrets.randbits(256)
    rpc_url = rpc_url or os.environ.get("POLYGON_RPC_URL", "https://polygon.drpc.org")
    ethereum_client = EthereumClient(URI(rpc_url))
    account = Account.from_key(from_private_key)

    safe_address = create_safe(
        ethereum_client=ethereum_client,
        account=account,
        owners=[account.address],
        salt_nonce=salt_nonce,
        threshold=1,
    )
    if not safe_address:
        logger.error("Could not deploy Safe. Aborting.")
        return

    if fund_safe:
        send_xdai_to(
            web3=ethereum_client.w3,
            from_private_key=PrivateKey(SecretStr(from_private_key)),
            to_address=safe_address,
            value=xDai(fund_amount_pol).as_xdai_wei,
        )

    safe_pol_wei = Wei(ethereum_client.w3.eth.get_balance(safe_address))
    logger.info(
        f"Operator Safe deployed at {safe_address} on Polygon "
        f"(salt_nonce={salt_nonce}). POL balance: {safe_pol_wei.as_token}. "
        f"Set SAFE_ADDRESS={safe_address} in .env for the migration scripts."
    )


if __name__ == "__main__":
    typer.run(deploy_polymarket_operator_safe)
