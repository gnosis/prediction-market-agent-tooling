import os

import pytest

from local_chain_utils import LocalNode, _local_node
from web3 import Web3
import os
from dotenv import load_dotenv


@pytest.fixture(autouse=True, scope="session")
def load_env():
    load_dotenv()


@pytest.fixture(scope="session")
def local_web3(load_env) -> Web3:
    RPC_URL = os.getenv("GNOSIS_RPC_URL")
    # if not available, throw error since we need an RPC with historical state for almost all tests
    if not RPC_URL:
        raise EnvironmentError("RPC_URL not loaded into environment variables.")
    node = LocalNode(RPC_URL, 8545, None)
    node_daemon = _local_node(node, True)
    yield node.w3
    if node_daemon:
        node_daemon.stop()
