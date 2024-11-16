from eth_account import Account
from pydantic import SecretStr
from safe_eth.eth import EthereumClient
from safe_eth.safe.safe import SafeV141
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import PrivateKey, xDai
from prediction_market_agent_tooling.loggers import logger
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
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import (
    Wei,
    send_xdai_to,
    xdai_to_wei,
    xdai_type,
)
from tests_integration_with_local_chain.safe.conftest import print_current_block


def test_create_safe(
    local_ethereum_client: EthereumClient,
    test_keys: APIKeys,
    test_safe: SafeV141,
) -> None:
    account = Account.from_key(test_keys.bet_from_private_key.get_secret_value())
    version = test_safe.retrieve_version()
    assert version == "1.4.1"
    assert local_ethereum_client.is_contract(test_safe.address)
    test_keys.SAFE_ADDRESS = test_safe.address
    is_owner = test_keys.check_if_is_safe_owner(local_ethereum_client)
    assert is_owner
    assert test_safe.retrieve_owners() == [account.address]


def test_send_function_on_contract_tx_using_safe(
    local_ethereum_client: EthereumClient,
    local_web3: Web3,
    test_keys: APIKeys,
    test_safe: SafeV141,
) -> None:
    print_current_block(local_web3)

    logger.debug(f"is connected {local_web3.is_connected()} {local_web3.provider}")
    print_current_block(local_web3)

    account = Account.from_key(test_keys.bet_from_private_key.get_secret_value())
    # Fund safe with xDAI if needed
    initial_safe_balance = local_ethereum_client.get_balance(test_safe.address)
    if initial_safe_balance < xdai_to_wei(xdai_type(10)):
        send_xdai_to(
            web3=local_web3,
            from_private_key=PrivateKey(SecretStr(account.key.hex())),
            to_address=test_safe.address,
            value=xdai_to_wei(xdai_type(10)),
        )

    print_current_block(local_web3)
    safe_balance = local_ethereum_client.get_balance(test_safe.address)
    logger.debug(f"safe balance {safe_balance} xDai")
    # Fetch existing market with enough liquidity
    min_liquidity_wei = xdai_to_wei(xdai_type(5))
    markets = fetch_omen_open_binary_market_with_enough_liquidity(1, min_liquidity_wei)
    # Check that there is a market with enough liquidity
    assert len(markets) == 1
    omen_market = markets[0]
    omen_agent_market = OmenAgentMarket.from_data_model(omen_market)
    amount = TokenAmount(amount=2, currency=Currency.xDai)
    test_keys.SAFE_ADDRESS = test_safe.address
    initial_yes_token_balance = omen_agent_market.get_token_balance(
        test_safe.address, OMEN_TRUE_OUTCOME, web3=local_web3
    )
    logger.debug(f"initial Yes token balance {initial_yes_token_balance}")
    binary_omen_buy_outcome_tx(
        api_keys=test_keys,
        amount=xDai(amount.amount),
        market=omen_agent_market,
        binary_outcome=True,
        auto_deposit=True,
        web3=local_web3,
    )
    print_current_block(local_web3)

    final_yes_token_balance = omen_agent_market.get_token_balance(
        test_safe.address, OMEN_TRUE_OUTCOME, web3=local_web3
    )
    logger.debug(f"final Yes token balance {final_yes_token_balance}")
    print_current_block(local_web3)
    assert initial_yes_token_balance.amount < final_yes_token_balance.amount


def fetch_omen_open_binary_market_with_enough_liquidity(
    limit: int = 1, liquidity_bigger_than: Wei = xdai_to_wei(xdai_type(5))
) -> list[OmenMarket]:
    return OmenSubgraphHandler().get_omen_binary_markets(
        limit=limit,
        question_opened_after=utcnow(),
        liquidity_bigger_than=liquidity_bigger_than,
    )
