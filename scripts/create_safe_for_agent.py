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


def create_safe_for_agent(
    from_private_key: str = typer.Option(),
    rpc_url: str | None = None,
    salt_nonce: int | None = None,
    fund_safe: bool = True,
    fund_amount_xdai: int = 1,
) -> None:
    """
        Helper script to create a Safe for an agent, usage:

        ```bash
        python scripts/create_safe_for_agent.py \
            --from-private-key your-private-key
            --rpc_url RPC URL [Optional, defaults to Gnosis Mainnet]
            --salt_nonce SALT_NONCE for reproducible Safe creation [Optional, defaults to random value]
            --fund_safe FUND_SAFE [Optional, defaults to true]
            --fund_amount FUND_AMOUNT [Optional, defaults to 1 xDAI]
        ```
        """

    salt_nonce = salt_nonce or secrets.randbits(256)
    rpc_url = rpc_url if rpc_url else RPCConfig().gnosis_rpc_url
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
        logger.error("Could not deploy safe. Aborting.")
        return

    if fund_safe:
        send_xdai_to(
            web3=ethereum_client.w3,
            from_private_key=PrivateKey(SecretStr(from_private_key)),
            to_address=safe_address,
            value=xDai(fund_amount_xdai).as_xdai_wei,
        )

    safe_balance = get_balances(
        Web3.to_checksum_address(safe_address), ethereum_client.w3
    )
    logger.info(f"Safe balance {safe_balance}")


if __name__ == "__main__":
    typer.run(create_safe_for_agent)
