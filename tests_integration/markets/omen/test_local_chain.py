import pytest
from web3 import Web3

from prediction_market_agent_tooling.gtypes import xDai
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.web3_utils import send_xdai_to, xdai_to_wei
from tests_integration.conftest import local_web3_at_block
from tests_integration.local_chain_utils import get_anvil_test_accounts


def test_connect_local_chain(local_web3: Web3) -> None:
    assert local_web3.is_connected()


def test_connect_local_chain_at_block(load_env, request: pytest.FixtureRequest) -> None:
    # start connection
    historical_block = 33324170
    web3 = local_web3_at_block(request, historical_block, 8546)
    assert web3.is_connected()
    assert web3.eth.get_block_number() == historical_block


def test_send_xdai(local_web3: Web3) -> None:
    accounts = get_anvil_test_accounts()
    value = xdai_to_wei(xDai(10))
    from_account = accounts[0]
    to_account = accounts[1]
    initial_balance_from = get_balances(from_account.address, local_web3)
    initial_balance_to = get_balances(to_account.address, local_web3)
    send_xdai_to(
        from_address=from_account.address,
        to_address=to_account.address,
        value=value,
        web3=local_web3,
    )
    final_balance_from = get_balances(from_account.address, local_web3)
    final_balance_to = get_balances(to_account.address, local_web3)
    assert int(final_balance_to.xdai - initial_balance_to.xdai) == local_web3.from_wei(
        value, "ether"
    )
    assert int(
        initial_balance_from.xdai - final_balance_from.xdai
    ) == local_web3.from_wei(value, "ether")
