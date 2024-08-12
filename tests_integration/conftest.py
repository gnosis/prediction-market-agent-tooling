import typing as t

import pytest
from ape.managers import ChainManager
from dotenv import load_dotenv
from gnosis.eth import EthereumClient
from web3 import Web3

from local_chain_utils import get_anvil_test_accounts
from prediction_market_agent_tooling.config import APIKeys


@pytest.fixture(autouse=True, scope="session")
def load_env() -> None:
    load_dotenv()


@pytest.fixture(scope="module")
def local_web3(load_env: None, chain: ChainManager) -> t.Generator[Web3, None, None]:
    with chain.network_manager.parse_network_choice(
        "gnosis:mainnet_fork:foundry"
    ) as provider:
        w3 = Web3(Web3.HTTPProvider(provider.http_uri))
        yield w3

    # clean-up
    # We have to add this hacky solution to avoid an eth-ape bug (https://github.com/ApeWorX/ape/issues/2215)
    if chain.network_manager.active_provider:
        chain.network_manager.active_provider.disconnect()


@pytest.fixture(scope="module")
def local_ethereum_client(local_web3: Web3) -> EthereumClient:
    return EthereumClient()


@pytest.fixture(scope="session")
def test_keys() -> APIKeys:
    account = get_anvil_test_accounts()[0]

    # Using a standard Anvil account with enough xDAI.
    return APIKeys(BET_FROM_PRIVATE_KEY=account.key.hex(), SAFE_ADDRESS=None)
