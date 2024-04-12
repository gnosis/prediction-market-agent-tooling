import typer
from eth_account import Account
from eth_typing import URI
from gnosis.eth import EthereumClient
from loguru import logger
from web3 import Web3

from prediction_market_agent_tooling.deploy.safe.safe_manager import SafeManager
from prediction_market_agent_tooling.gtypes import private_key_type
from prediction_market_agent_tooling.tools.safe import create_safe


def create_safe_for_agent(
    from_private_key: str = typer.Option(),
    rpc_url: str | None = None,
) -> None:
    """
        Helper script to create a market on Omen, usage:

        ```bash
        python scripts/create_safe_for_agent.py \
            --from-private-key your-private-key
            --rpc_url RPC URL
        ```
        """
    private_key = private_key_type(from_private_key)
    ethereum_client = None
    if rpc_url:
        ethereum_client = EthereumClient(URI(rpc_url))
    create_safe(private_key, ethereum_client)


if __name__ == "__main__":
    typer.run(create_safe_for_agent)
