import typing as t

import pytest
from ape.api import ProviderAPI
from ape.managers import ChainManager
from dotenv import load_dotenv
from eth_typing import ChecksumAddress
from gnosis.eth import EthereumClient
from web3 import Web3

from local_chain_utils import LocalNode, _local_node, get_anvil_test_accounts
from prediction_market_agent_tooling.config import APIKeys


@pytest.fixture(autouse=True, scope="session")
def load_env() -> None:
    load_dotenv()


@pytest.fixture(scope="session")
def local_web3_old(load_env: None) -> t.Generator[Web3, None, None]:
    # if not available, throw error since we need an RPC with historical state for almost all tests
    node = LocalNode("https://rpc.gnosis.gateway.fm")
    node_daemon = _local_node(node, True)
    yield node.w3
    if node_daemon:
        node_daemon.stop()


@pytest.fixture(scope="class")
def local_web3(
    load_env: None, chain: ChainManager
) -> t.Generator[ProviderAPI, None, None]:
    with chain.network_manager.fork(provider_name="foundry") as provider:
        print(provider)
        w3 = Web3(Web3.HTTPProvider(provider.http_uri))
        yield w3

    # clean-up
    chain.network_manager.active_provider.disconnect()


@pytest.fixture(scope="session")
def local_ethereum_client(local_web3: Web3) -> EthereumClient:
    return EthereumClient()


def is_contract(web3: Web3, contract_address: ChecksumAddress) -> bool:
    # From gnosis.eth.EthereumClient
    return bool(web3.eth.get_code(contract_address))


@pytest.fixture(scope="session")
def test_keys() -> APIKeys:
    account = get_anvil_test_accounts()[0]

    # Using a standard Anvil account with enough xDAI.
    return APIKeys(BET_FROM_PRIVATE_KEY=account.key.hex(), SAFE_ADDRESS=None)
