import pytest
from web3 import Web3

from tests_integration.conftest import local_web3_at_block


def test_connect_local_chain(local_web3: Web3) -> None:
    assert local_web3.is_connected()


def test_connect_local_chain_at_block(load_env, request: pytest.FixtureRequest) -> None:
    # start connection
    historical_block = 33324170
    web3 = local_web3_at_block(request, historical_block, 8546)
    assert web3.is_connected()
    assert web3.eth.get_block_number() == historical_block

