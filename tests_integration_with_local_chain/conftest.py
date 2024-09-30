import typing as t

import pytest
import requests
from ape.managers import ChainManager
from ape_test import TestAccount
from dotenv import load_dotenv
from gnosis.eth import EthereumClient
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    HexAddress,
    private_key_type,
    xDai,
    xdai_type,
)
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


@pytest.fixture(autouse=True, scope="session")
def load_env() -> None:
    load_dotenv()


@pytest.fixture(scope="module")
def local_web3(
    load_env: None, chain: ChainManager, accounts: list[TestAccount]
) -> t.Generator[Web3, None, None]:
    print("entering fixture local_web3")

    if (tenderly_fork_rpc := APIKeys().TENDERLY_FORK_RPC) is not None:
        print("using tenderly rpc")
        w3 = Web3(Web3.HTTPProvider(tenderly_fork_rpc))
        print("funding test accounts on tenderly")
        fund_account_on_tenderly(
            tenderly_fork_rpc, [a.address for a in accounts], xdai_type(1000)
        )
        yield w3
    else:
        print("using foundry")
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


def fund_account_on_tenderly(
    fork_rpc: str, addresses: list[HexAddress], balance: xDai
) -> None:
    payload = {
        "jsonrpc": "2.0",
        "method": "tenderly_setBalance",
        "params": [addresses, f"0x{xdai_to_wei(balance):X}"],
    }
    response = requests.post(fork_rpc, json=payload)
    response.raise_for_status()
