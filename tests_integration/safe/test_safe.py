import pytest
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import URI
from gnosis.eth import EthereumClient
from gnosis.safe import Safe
from loguru import logger
from web3 import Web3

from prediction_market_agent_tooling.config import PrivateCredentials
from prediction_market_agent_tooling.markets.data_models import Currency, TokenAmount
from prediction_market_agent_tooling.markets.omen.data_models import OMEN_TRUE_OUTCOME
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.safe import create_safe
from prediction_market_agent_tooling.tools.web3_utils import send_xdai_to, xdai_to_wei
from tests_integration.conftest import local_web3_at_block


def test_create_safe(
    local_ethereum_client: EthereumClient, test_credentials: PrivateCredentials
) -> None:
    account = Account.from_key(test_credentials.private_key.get_secret_value())
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


def print_current_block(web3: Web3) -> None:
    logger.debug(f"current block {web3.eth.block_number}")


def test_send_function_on_contract_tx_using_safe(
    request: pytest.FixtureRequest,
    test_credentials: PrivateCredentials,
) -> None:
    historical_block = 33527254
    port = 8546
    web3 = local_web3_at_block(request, historical_block, port)
    local_ethereum_client = EthereumClient(URI(f"http://localhost:{port}"))
    print(f"is connected {web3.is_connected()} {web3.provider}")
    # local_ethereum_client = EthereumClient(URI(RPC_URL))
    print_current_block(web3)
    logger.debug(
        f"provider {web3.provider.endpoint_uri} connected {web3.is_connected()}"
    )

    # Deploy safe
    account = Account.from_key(test_credentials.private_key.get_secret_value())
    safe = create_test_safe(local_ethereum_client, account)
    # Fund safe if needed
    print_current_block(web3)
    initial_safe_balance = local_ethereum_client.get_balance(safe.address)
    if initial_safe_balance < xdai_to_wei(10):
        send_xdai_to(
            local_ethereum_client.w3,
            Web3.to_checksum_address(account.address),
            safe.address,
            xdai_to_wei(10),
        )

    print_current_block(web3)
    safe_balance = local_ethereum_client.get_balance(safe.address)
    logger.debug(f"safe balance {safe_balance} xDai")
    # Bet on Omen market
    market_id = Web3.to_checksum_address("0x753d3b31bf1038d5b5aa81015b7b3a6a71e3a6e4")
    subgraph = OmenSubgraphHandler()
    omen_market = subgraph.get_omen_market_by_market_id(market_id)
    omen_agent_market = OmenAgentMarket.from_data_model(omen_market)
    amount = TokenAmount(amount=5, currency=Currency.xDai)
    initial_yes_token_balance = omen_agent_market.get_token_balance(
        safe.address, OMEN_TRUE_OUTCOME, web3=local_ethereum_client.w3
    )
    print_current_block(web3)
    logger.debug(f"initial Yes token balance {initial_yes_token_balance}")
    bet_tx_hash = omen_agent_market.place_bet(
        True, amount, web3=local_ethereum_client.w3
    )
    print_current_block(web3)
    logger.debug(f"placed bet tx hash {bet_tx_hash}")
    final_yes_token_balance = omen_agent_market.get_token_balance(
        safe.address, OMEN_TRUE_OUTCOME, web3=local_ethereum_client.w3
    )
    logger.debug(f"final Yes token balance {final_yes_token_balance}")
    print_current_block(web3)
    assert initial_yes_token_balance.amount < final_yes_token_balance.amount
