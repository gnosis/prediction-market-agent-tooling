import os

import pytest
from eth_account import Account
from gnosis.eth import EthereumClient
from gnosis.safe import Safe
from loguru import logger
from web3 import Web3

from prediction_market_agent_tooling.config import PrivateCredentials
from prediction_market_agent_tooling.gtypes import xDai
from prediction_market_agent_tooling.markets.data_models import Currency, TokenAmount
from prediction_market_agent_tooling.markets.omen.data_models import OMEN_TRUE_OUTCOME
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket, binary_omen_buy_outcome_tx
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.safe import create_safe
from prediction_market_agent_tooling.tools.web3_utils import send_xdai_to, xdai_to_wei
from tests_integration.local_chain_utils import fork_reset_state
from tests_integration.safe.conftest import print_current_block


def test_create_safe(
    local_ethereum_client: EthereumClient, test_credentials: PrivateCredentials,
        test_safe: Safe
) -> None:
    account = Account.from_key(test_credentials.private_key.get_secret_value())
    version = test_safe.retrieve_version()
    assert version == "1.4.1"
    assert local_ethereum_client.is_contract(test_safe.address)
    assert test_safe.retrieve_owners() == [account.address]





#@pytest.mark.skip(reason="not yet working on Github CI/CD pipeline")
def test_send_function_on_contract_tx_using_safe(
    request: pytest.FixtureRequest,
        local_ethereum_client: EthereumClient,
    local_web3: Web3,
    test_credentials: PrivateCredentials,
) -> None:
    # ToDo - Use fixture test_safe

    RPC_URL = os.getenv("GNOSIS_RPC_URL")
    historical_block = 33579187
    # port = 8546
    # web3 = local_web3_at_block(request, historical_block, port)
    fork_reset_state(
        local_web3,
        url=RPC_URL,
        block=historical_block,
    )
    print_current_block(local_web3)
    # Deploy Safe
    # Deploy safe
    account = Account.from_key(test_credentials.private_key.get_secret_value())
    safe_address = create_safe(
        ethereum_client=local_ethereum_client,
        account=account,
        owners=[account.address],
        salt_nonce=42,
        threshold=1,
    )
    test_safe = Safe(safe_address, local_ethereum_client)
    # local_ethereum_client = EthereumClient(URI(f"http://localhost:{port}"))
    print(f"is connected {local_web3.is_connected()} {local_web3.provider}")
    # local_ethereum_client = EthereumClient(URI(RPC_URL))
    print_current_block(local_web3)
    logger.debug(
        f"provider {local_web3.provider.endpoint_uri} connected {local_web3.is_connected()}"
    )

    # Deploy test_safe
    account = Account.from_key(test_credentials.private_key.get_secret_value())
    # Fund safe with xDAI if needed
    print_current_block(local_web3)
    initial_safe_balance = local_ethereum_client.get_balance(test_safe.address)
    if initial_safe_balance < xdai_to_wei(10):
        send_xdai_to(
            local_ethereum_client.w3,
            Web3.to_checksum_address(account.address),
            test_safe.address,
            xdai_to_wei(10),
        )

    print_current_block(local_web3)
    safe_balance = local_ethereum_client.get_balance(test_safe.address)
    logger.debug(f"safe balance {safe_balance} xDai")
    # Bet on Omen market
    market_id = Web3.to_checksum_address("0x753d3b31bf1038d5b5aa81015b7b3a6a71e3a6e4")
    subgraph = OmenSubgraphHandler()
    omen_market = subgraph.get_omen_market_by_market_id(market_id)
    omen_agent_market = OmenAgentMarket.from_data_model(omen_market)
    amount = TokenAmount(amount=5, currency=Currency.xDai)
    test_credentials.safe_address = test_safe.address
    initial_yes_token_balance = omen_agent_market.get_token_balance(
        test_safe.address, OMEN_TRUE_OUTCOME, web3=local_web3
    )
    #print_current_block(web3)
    #mine_block(web3)
    #print_current_block(web3)
    logger.debug(f"initial Yes token balance {initial_yes_token_balance}")
    bet_tx_hash = binary_omen_buy_outcome_tx(
        private_credentials=test_credentials,
        amount=xDai(amount.amount),
        market=omen_agent_market,
        binary_outcome=True,
        auto_deposit=True,
        web3=local_web3,
    )

    #bet_tx_hash = omen_agent_market.place_bet(True, amount, web3=web3)
    #print_current_block(web3)
    #mine_block(web3)
    print_current_block(local_web3)
    logger.debug(f"placed bet tx hash {bet_tx_hash}")

    final_yes_token_balance = omen_agent_market.get_token_balance(
        test_safe.address, OMEN_TRUE_OUTCOME, web3=local_web3
    )
    logger.debug(f"final Yes token balance {final_yes_token_balance}")
    print_current_block(local_web3)
    assert initial_yes_token_balance.amount < final_yes_token_balance.amount
