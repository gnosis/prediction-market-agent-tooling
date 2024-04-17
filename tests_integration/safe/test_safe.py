import pytest
from eth_account import Account
from eth_account.signers.local import LocalAccount
from gnosis.eth import EthereumClient
from gnosis.safe import Safe
from web3 import Web3
from web3.gas_strategies.time_based import fast_gas_price_strategy

from prediction_market_agent_tooling.markets.data_models import Currency, TokenAmount
from prediction_market_agent_tooling.markets.omen.data_models import OMEN_TRUE_OUTCOME
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.safe import create_safe
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei
from tests.utils import RUN_PAID_TESTS
from tests_integration.safe.test_constants import ANVIL_PKEY1


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_create_safe(local_ethereum_client: EthereumClient) -> None:
    # ToDo - Implement this when this issue has been merged (https://github.com/gnosis/prediction-market-agent-tooling/issues/99)
    #  Start local chain (fork Gnosis)
    #  Call create safe - for inspiration -> https://github.com/karpatkey/roles_royce/blob/2529d244ed8502d34f9daa9f70fa80e7b1123937/tests/utils.py#L77
    # create_safe(from_private_key=private_key_anvil1)
    #  Assert safe is valid, safe version 1.4.1
    #  Stop local chain

    account = Account.from_key(ANVIL_PKEY1)
    deployed_safe = create_test_safe(local_ethereum_client, account)
    version = deployed_safe.retrieve_version()
    assert version == "1.4.1"
    assert local_ethereum_client.is_contract(deployed_safe.address)
    assert deployed_safe.retrieve_owners() == [account.address]


def create_test_safe(ethereum_client: EthereumClient, deployer: LocalAccount):
    safe_address = create_safe(
        ethereum_client=ethereum_client,
        account=deployer,
        owners=[deployer.address],
        salt_nonce=42,
        threshold=1,
    )
    deployed_safe = Safe(safe_address, ethereum_client)
    return deployed_safe


@pytest.fixture()
def local_ethereum_client():
    return EthereumClient()


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_send_function_on_contract_tx_using_safe(
    local_ethereum_client: EthereumClient,
) -> None:
    # Deploy safe
    account = Account.from_key(ANVIL_PKEY1)
    safe = create_test_safe(local_ethereum_client, account)
    # Fund safe
    local_ethereum_client.w3.eth.set_gas_price_strategy(fast_gas_price_strategy)
    gas_price = local_ethereum_client.w3.eth.generate_gas_price()

    initial_safe_balance = local_ethereum_client.get_balance(safe.address)
    if initial_safe_balance < xdai_to_wei(2):
        local_ethereum_client.send_eth_to(
            account.key.hex(), safe.address, gas_price, xdai_to_wei(2)
        )

    # Bet on Omen market

    market_id = Web3.to_checksum_address("0x753d3b31bf1038d5b5aa81015b7b3a6a71e3a6e4")
    subgraph = OmenSubgraphHandler()
    omen_market = subgraph.get_omen_market_by_market_id(market_id)
    omen_agent_market = OmenAgentMarket.from_data_model(omen_market)
    amount = TokenAmount(amount=1, currency=Currency.xDai)
    initial_yes_token_balance = omen_agent_market.get_token_balance(
        safe.address, OMEN_TRUE_OUTCOME, web3=local_ethereum_client.w3
    )
    omen_agent_market.buy_tokens(True, amount, web3=local_ethereum_client.w3)
    # assert balance is smaller
    # ToDo - Check if outcome token amount increased
    final_yes_token_balance = omen_agent_market.get_token_balance(
        safe.address, OMEN_TRUE_OUTCOME, web3=local_ethereum_client.w3
    )
    assert initial_yes_token_balance.amount < final_yes_token_balance.amount
    print("done")