import os

import pytest
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress
from pydantic import SecretStr

from local_chain_utils import LocalNode, _local_node
from web3 import Web3
import os
from dotenv import load_dotenv

from prediction_market_agent_tooling.config import PrivateCredentials
from prediction_market_agent_tooling.gtypes import PrivateKey


@pytest.fixture(autouse=True, scope="session")
def load_env():
    load_dotenv()


@pytest.fixture(scope="session")
def local_chain_accounts() -> list[LocalAccount]:
    anvil_private_keys = [
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
        "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
        "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
        "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
        "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
        "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
        "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
        "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
        "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
    ]
    return [Account.from_key(i) for i in anvil_private_keys]


@pytest.fixture(scope="session")
def local_web3(load_env) -> Web3:
    RPC_URL = os.getenv("GNOSIS_RPC_URL")
    # if not available, throw error since we need an RPC with historical state for almost all tests
    if not RPC_URL:
        raise EnvironmentError("RPC_URL not loaded into environment variables.")
    node = LocalNode(RPC_URL)
    node_daemon = _local_node(node, True)
    yield node.w3
    if node_daemon:
        node_daemon.stop()


# ToDo - Turn this pattern into way to initialize chain with a block number
@pytest.fixture()
def my_chain():
    def _user_creds(block: int):
        # initialize chain
        return {"block": block}

    yield _user_creds
    print("finished")


def is_contract(web3: Web3, contract_address: ChecksumAddress) -> bool:
    # From gnosis.eth.EthereumClient
    return bool(web3.eth.get_code(contract_address))


@pytest.fixture(scope="session")
def test_credentials(local_chain_accounts: list[LocalAccount]) -> PrivateCredentials:
    account = local_chain_accounts[0]

    # Using a standard Anvil account with enough xDAI.
    private_credentials = PrivateCredentials(
        private_key=PrivateKey(SecretStr(account.key.hex())), safe_address=None
    )
    return private_credentials
