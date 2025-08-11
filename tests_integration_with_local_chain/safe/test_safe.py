from eth_account import Account
from pydantic import SecretStr
from safe_eth.eth import EthereumClient
from safe_eth.safe.safe import SafeV141
from web3 import Web3
from web3.constants import ADDRESS_ZERO, HASH_ZERO

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import USD, OutcomeStr, PrivateKey
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_TRUE_OUTCOME,
    ContractPrediction,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    FilterBy,
    OmenAgentMarket,
    SortBy,
    binary_omen_buy_outcome_tx,
)
from prediction_market_agent_tooling.markets.omen.omen_constants import (
    SDAI_CONTRACT_ADDRESS,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenAgentResultMappingContract,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.web3_utils import send_xdai_to, xDai
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
    if initial_safe_balance < xDai(10).as_xdai_wei.as_wei:
        send_xdai_to(
            web3=local_web3,
            from_private_key=PrivateKey(SecretStr(account.key.to_0x_hex())),
            to_address=test_safe.address,
            value=xDai(10).as_xdai_wei,
        )

    print_current_block(local_web3)
    safe_balance = local_ethereum_client.get_balance(test_safe.address)
    logger.debug(f"safe balance {safe_balance} xDai")
    # Fetch existing market with enough liquidity
    markets = OmenSubgraphHandler().get_omen_markets_simple(
        limit=1,
        filter_by=FilterBy.OPEN,
        sort_by=SortBy.NONE,
        collateral_token_address_in=tuple([SDAI_CONTRACT_ADDRESS]),
    )
    # Check that there is a market with enough liquidity
    assert len(markets) == 1
    omen_market = markets[0]
    omen_agent_market = OmenAgentMarket.from_data_model(omen_market)
    amount = USD(2)
    test_keys.SAFE_ADDRESS = test_safe.address
    initial_yes_token_balance = omen_agent_market.get_token_balance(
        test_safe.address, OMEN_TRUE_OUTCOME, web3=local_web3
    )
    logger.debug(f"initial Yes token balance {initial_yes_token_balance}")
    binary_omen_buy_outcome_tx(
        api_keys=test_keys,
        amount=amount,
        market=omen_agent_market,
        outcome=OMEN_TRUE_OUTCOME,
        auto_deposit=True,
        web3=local_web3,
    )
    print_current_block(local_web3)

    final_yes_token_balance = omen_agent_market.get_token_balance(
        test_safe.address, OMEN_TRUE_OUTCOME, web3=local_web3
    )
    logger.debug(f"final Yes token balance {final_yes_token_balance}")
    print_current_block(local_web3)
    assert initial_yes_token_balance < final_yes_token_balance


def test_add_prediction_with_safe(
    local_ethereum_client: EthereumClient,
    local_web3: Web3,
    test_keys: APIKeys,
    test_safe: SafeV141,
) -> None:
    test_keys.SAFE_ADDRESS = test_safe.address
    dummy_transaction_hash = "0x3750ffa211dab39b4d0711eb27b02b56a17fa9d257ee549baa3110725fd1d41b"  # web3-private-key-ok
    dummy_market_address = Web3.to_checksum_address(ADDRESS_ZERO)
    p = ContractPrediction(
        market=dummy_market_address,
        tx_hashes=[HexBytes(dummy_transaction_hash)],
        outcomes=[OutcomeStr("test")],
        estimated_probabilities_bps=[5454],
        ipfs_hash=HexBytes(HASH_ZERO),
        publisher=test_keys.bet_from_address,
    )

    contract = OmenAgentResultMappingContract()

    tx_receipt = contract.add_prediction(
        api_keys=test_keys,
        market_address=dummy_market_address,
        prediction=p,
        web3=local_web3,
    )

    # We expect a new prediction to exist under the Safe address key.
    predictions = contract.get_predictions(
        market_address=dummy_market_address, web3=local_web3
    )
    predictions_from_safe_address = [
        i for i in predictions if i.publisher_checksummed == test_keys.bet_from_address
    ]
    assert len(predictions_from_safe_address) == 1
    actual_prediction = predictions_from_safe_address[0]
    assert actual_prediction == p
