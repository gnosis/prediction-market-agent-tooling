import typing as t

import pytest
import requests
from ape.managers import ChainManager
from ape_test import TestAccount
from dotenv import load_dotenv
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import URI
from safe_eth.eth import EthereumClient
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    HexAddress,
    PrivateKey,
    private_key_type,
    xDai,
    xdai_type,
)
from prediction_market_agent_tooling.tools.web3_utils import send_xdai_to, xdai_to_wei


@pytest.fixture(autouse=True, scope="session")
def load_env() -> None:
    load_dotenv()


@pytest.fixture(scope="session")
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
    return EthereumClient(URI(local_web3.provider.endpoint_uri))  # type: ignore


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


def create_and_fund_random_account(
    web3: Web3, private_key: PrivateKey, deposit_amount: xDai = xDai(10)
) -> LocalAccount:
    fresh_account: LocalAccount = Account.create()
    send_xdai_to(
        web3=web3,
        from_private_key=private_key,
        to_address=fresh_account.address,
        value=xdai_to_wei(deposit_amount),
    )
    return fresh_account
