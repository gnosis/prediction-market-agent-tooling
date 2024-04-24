
import pytest
from dotenv import load_dotenv
from eth_typing import ChecksumAddress
from gnosis.eth import EthereumClient
from local_chain_utils import LocalNode, _local_node, get_anvil_test_accounts
from pydantic import SecretStr
from web3 import Web3

from prediction_market_agent_tooling.config import PrivateCredentials
from prediction_market_agent_tooling.gtypes import PrivateKey
from prediction_market_agent_tooling.tools.gnosis_rpc import GNOSIS_RPC_URL


@pytest.fixture(autouse=True, scope="session")
def load_env():
    load_dotenv()


@pytest.fixture(scope="session")
def local_web3(load_env) -> Web3:
    # if not available, throw error since we need an RPC with historical state for almost all tests
    node = LocalNode(GNOSIS_RPC_URL)
    node_daemon = _local_node(node, True)
    yield node.w3
    if node_daemon:
        node_daemon.stop()


def local_web3_at_block(
    request: pytest.FixtureRequest, block: int, port: int = 8546
) -> Web3:
    node = LocalNode(GNOSIS_RPC_URL, port=port, default_block=block)
    node_daemon = _local_node(node, True)
    # for auto-closing connection
    request.addfinalizer(node_daemon.stop)
    return node.w3


@pytest.fixture(scope="session")
def local_ethereum_client(local_web3: Web3) -> EthereumClient:
    return EthereumClient()


def is_contract(web3: Web3, contract_address: ChecksumAddress) -> bool:
    # From gnosis.eth.EthereumClient
    return bool(web3.eth.get_code(contract_address))


@pytest.fixture(scope="session")
def test_credentials() -> PrivateCredentials:
    account = get_anvil_test_accounts()[0]

    # Using a standard Anvil account with enough xDAI.
    private_credentials = PrivateCredentials(
        private_key=PrivateKey(SecretStr(account.key.hex())), safe_address=None
    )
    return private_credentials
