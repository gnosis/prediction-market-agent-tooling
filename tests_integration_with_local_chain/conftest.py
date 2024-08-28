import typing as t

import pytest
from ape.managers import ChainManager
from ape_test import TestAccount
from dotenv import load_dotenv
from gnosis.eth import EthereumClient
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type


@pytest.fixture(autouse=True, scope="session")
def load_env() -> None:
    load_dotenv()


@pytest.fixture(scope="session")
def local_web3(load_env: None, chain: ChainManager) -> t.Generator[Web3, None, None]:
    print("entering fixture local_web3")
    with chain.network_manager.parse_network_choice(
        "gnosis:mainnet_fork:foundry"
    ) as provider:
        w3 = Web3(Web3.HTTPProvider(provider.http_uri))
        yield w3

    print("exiting fixture local_web3")


@pytest.fixture(scope="module")
def local_ethereum_client(local_web3: Web3) -> EthereumClient:
    return EthereumClient()


@pytest.fixture(scope="session")
def test_keys(accounts: list[TestAccount]) -> APIKeys:
    account = accounts[0]

    # Using a standard Anvil account with enough xDAI.
    return APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(account.private_key), SAFE_ADDRESS=None
    )
