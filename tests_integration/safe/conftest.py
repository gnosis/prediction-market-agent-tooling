import pytest
from eth_account import Account
from gnosis.eth import EthereumClient
from gnosis.safe import Safe
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.safe import create_safe


def print_current_block(web3: Web3) -> None:
    logger.debug(f"current block {web3.eth.block_number}")


@pytest.fixture(scope="session")
def test_safe(local_web3: Web3, test_keys: APIKeys) -> Safe:
    web3 = local_web3
    print_current_block(web3)
    # local_ethereum_client = EthereumClient(URI(f"http://localhost:{port}"))
    local_ethereum_client = EthereumClient()
    logger.debug(f"is connected {web3.is_connected()} {web3.provider}")
    print_current_block(web3)
    logger.debug(
        f"provider {web3.provider.endpoint_uri} connected {web3.is_connected()}"
    )

    # Deploy safe
    account = Account.from_key(test_keys.bet_from_private_key.get_secret_value())
    safe_address = create_safe(
        ethereum_client=local_ethereum_client,
        account=account,
        owners=[account.address],
        salt_nonce=42,
        threshold=1,
    )
    deployed_safe = Safe(safe_address, local_ethereum_client)
    return deployed_safe
