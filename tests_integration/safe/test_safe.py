from eth_account import Account
from gnosis.eth import EthereumClient
from gnosis.safe import Safe
from loguru import logger
from web3 import Web3

from prediction_market_agent_tooling.config import PrivateCredentials
from prediction_market_agent_tooling.gtypes import xDai
from prediction_market_agent_tooling.markets.data_models import Currency, TokenAmount
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_TRUE_OUTCOME,
    OmenMarket,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    binary_omen_buy_outcome_tx,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei
from tests_integration.local_chain_utils import send_xdai_to_for_tests
from tests_integration.safe.conftest import print_current_block


def test_create_safe(
    local_ethereum_client: EthereumClient,
    test_credentials: PrivateCredentials,
    test_safe: Safe,
) -> None:
    account = Account.from_key(test_credentials.private_key.get_secret_value())
    version = test_safe.retrieve_version()
    assert version == "1.4.1"
    assert local_ethereum_client.is_contract(test_safe.address)
    assert test_safe.retrieve_owners() == [account.address]


def test_send_function_on_contract_tx_using_safe(
    local_ethereum_client: EthereumClient,
    local_web3: Web3,
    test_credentials: PrivateCredentials,
    test_safe: Safe,
) -> None:
    print_current_block(local_web3)

    logger.debug(f"is connected {local_web3.is_connected()} {local_web3.provider}")
    print_current_block(local_web3)
    logger.debug(
        f"provider {local_web3.provider.endpoint_uri} connected {local_web3.is_connected()}"
    )

    account = Account.from_key(test_credentials.private_key.get_secret_value())
    # Fund safe with xDAI if needed
    initial_safe_balance = local_ethereum_client.get_balance(test_safe.address)
    if initial_safe_balance < xdai_to_wei(10):
        send_xdai_to_for_tests(
            web3=local_ethereum_client.w3,
            from_address=Web3.to_checksum_address(account.address),
            to_address=test_safe.address,
            value=xdai_to_wei(10),
        )

    print_current_block(local_web3)
    safe_balance = local_ethereum_client.get_balance(test_safe.address)
    logger.debug(f"safe balance {safe_balance} xDai")
    # Fetch existing market with enough liquidity
    min_liquidity_wei = xdai_to_wei(xDai(5))
    markets = fetch_omen_open_binary_market_with_enough_liquidity(1, min_liquidity_wei)
    # Check that there is a market with enough liquidity
    assert len(markets) == 1
    omen_market = markets[0]
    omen_agent_market = OmenAgentMarket.from_data_model(omen_market)
    amount = TokenAmount(amount=2, currency=Currency.xDai)
    test_credentials.safe_address = test_safe.address
    initial_yes_token_balance = omen_agent_market.get_token_balance(
        test_safe.address, OMEN_TRUE_OUTCOME, web3=local_web3
    )
    logger.debug(f"initial Yes token balance {initial_yes_token_balance}")
    bet_tx_hash = binary_omen_buy_outcome_tx(
        private_credentials=test_credentials,
        amount=xDai(amount.amount),
        market=omen_agent_market,
        binary_outcome=True,
        auto_deposit=True,
        web3=local_web3,
    )
    print_current_block(local_web3)
    logger.debug(f"placed bet tx hash {bet_tx_hash}")

    final_yes_token_balance = omen_agent_market.get_token_balance(
        test_safe.address, OMEN_TRUE_OUTCOME, web3=local_web3
    )
    logger.debug(f"final Yes token balance {final_yes_token_balance}")
    print_current_block(local_web3)
    assert initial_yes_token_balance.amount < final_yes_token_balance.amount


def fetch_omen_open_binary_market_with_enough_liquidity(
    limit=1, liquidity_bigger_than=xdai_to_wei(xDai(5))
) -> list[OmenMarket]:
    return OmenSubgraphHandler().get_omen_binary_markets(
        limit=limit, resolved=False, liquidity_bigger_than=liquidity_bigger_than
    )
