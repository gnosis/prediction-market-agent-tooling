import secrets

import typer
from eth_account import Account
from eth_typing import URI
from gnosis.eth import EthereumClient

from prediction_market_agent_tooling.tools.gnosis_rpc import GNOSIS_RPC_URL
from prediction_market_agent_tooling.tools.safe import create_safe


def create_safe_for_agent(
    from_private_key: str = typer.Option(),
    rpc_url: str | None = None,
    salt_nonce: int = secrets.randbits(256),
) -> None:
    """
        Helper script to create a Safe for an agent, usage:

        ```bash
        python scripts/create_safe_for_agent.py \
            --from-private-key your-private-key
            --rpc_url RPC URL [Optional, defaults to Gnosis Mainnet]
            --salt_nonce SALT_NONCE for reproducible Safe creation [Optional, defaults to random value]
        ```
        """

    ethereum_client = EthereumClient(URI(GNOSIS_RPC_URL))
    if rpc_url:
        ethereum_client = EthereumClient(URI(rpc_url))
    account = Account.from_key(from_private_key)
    create_safe(
        ethereum_client=ethereum_client,
        account=account,
        owners=[account.address],
        salt_nonce=salt_nonce,
        threshold=1,
    )


if __name__ == "__main__":
    typer.run(create_safe_for_agent)
