"""Deploy an operator Safe on Polygon for the position-migration demo.

Thin wrapper over `create_safe_for_agent` that defaults to the Polygon RPC.
The deployed Safe will be the operator that holds stata + the user's USDC.e
outcome tokens. Save the printed Safe address — the other migration scripts
need it as their SAFE_ADDRESS env var.

Usage:
    python scripts/polymarket_safe_create.py \\
        --from-private-key 0x... \\
        [--salt-nonce 42] \\
        [--fund-amount-pol 1]
"""

import secrets

import typer
from eth_account import Account
from eth_typing import URI
from pydantic import SecretStr
from safe_eth.eth import EthereumClient
from web3 import Web3

from prediction_market_agent_tooling.config import RPCConfig
from prediction_market_agent_tooling.gtypes import PrivateKey, xDai
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.safe import create_safe
from prediction_market_agent_tooling.tools.web3_utils import send_xdai_to


def deploy_polymarket_operator_safe(
    from_private_key: str = typer.Option(),
    rpc_url: str | None = None,
    salt_nonce: int | None = None,
    fund_safe: bool = True,
    fund_amount_pol: int = 1,
) -> None:
    salt_nonce = salt_nonce or secrets.randbits(256)
    rpc_url = rpc_url or RPCConfig().polygon_rpc_url
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

    safe_balance = get_balances(
        Web3.to_checksum_address(safe_address), ethereum_client.w3
    )
    logger.info(
        f"Operator Safe deployed at {safe_address} on Polygon "
        f"(salt_nonce={salt_nonce}). Balance: {safe_balance}. "
        f"Set SAFE_ADDRESS={safe_address} in .env for the migration scripts."
    )


if __name__ == "__main__":
    typer.run(deploy_polymarket_operator_safe)
