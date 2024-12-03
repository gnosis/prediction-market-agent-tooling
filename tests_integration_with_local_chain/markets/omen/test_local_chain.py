import time

from ape_test import TestAccount
from eth_account import Account
from numpy import isclose
from web3 import Web3
from web3.types import Wei

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type, xDai, xdai_type
from prediction_market_agent_tooling.markets.omen.omen import get_total_balance
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.contract import DebuggingContract
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import (
    send_xdai_to,
    wei_to_xdai,
    xdai_to_wei,
)
from tests.utils import mint_new_block


def test_connect_local_chain(local_web3: Web3) -> None:
    assert local_web3.is_connected()


def test_send_xdai(local_web3: Web3, accounts: list[TestAccount]) -> None:
    value = xdai_to_wei(xDai(10))
    from_account = accounts[0]
    to_account = accounts[1]
    initial_balance_from = get_balances(from_account.address, local_web3)
    initial_balance_to = get_balances(to_account.address, local_web3)

    send_xdai_to(
        web3=local_web3,
        from_private_key=private_key_type(from_account.private_key),
        to_address=to_account.address,
        value=value,
    )

    final_balance_from = get_balances(from_account.address, local_web3)
    final_balance_to = get_balances(to_account.address, local_web3)
    assert int(final_balance_to.xdai - initial_balance_to.xdai) == local_web3.from_wei(
        value, "ether"
    )
    assert int(
        initial_balance_from.xdai - final_balance_from.xdai
    ) == local_web3.from_wei(value, "ether")


def test_send_xdai_from_locked_account(
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    from_account = Account.from_key(test_keys.bet_from_private_key.get_secret_value())
    fund_value = xdai_to_wei(xDai(10))
    transfer_back_value = xdai_to_wei(xDai(5))
    random_locked_account = local_web3.eth.account.create()
    # we fund the random account for later sending
    send_xdai_to(
        web3=local_web3,
        from_private_key=private_key_type(from_account.key.hex()),
        to_address=random_locked_account.address,
        value=fund_value,
    )

    balance_random = get_balances(random_locked_account.address, local_web3)
    assert xdai_to_wei(balance_random.xdai) == fund_value
    send_xdai_to(
        web3=local_web3,
        from_private_key=private_key_type(random_locked_account.key.hex()),
        to_address=from_account.address,
        value=transfer_back_value,
    )
    balance_random = get_balances(random_locked_account.address, local_web3)
    # We use isclose due to gas costs minimally affecting the balance
    assert isclose(
        balance_random.xdai,
        wei_to_xdai(Wei(fund_value - transfer_back_value)),
        rtol=0.001,
    )


def test_anvil_account_has_more_than_minimum_required_balance(
    local_web3: Web3,
    accounts: list[TestAccount],
) -> None:
    account_adr = Web3.to_checksum_address(accounts[0].address)
    assert get_total_balance(account_adr, local_web3) > xdai_type(0.5)


def test_fresh_account_has_less_than_minimum_required_balance(local_web3: Web3) -> None:
    fresh_account_adr = Account.create().address
    account_adr = Web3.to_checksum_address(fresh_account_adr)
    assert get_total_balance(account_adr, local_web3) < xdai_type(0.5)


def test_now(local_web3: Web3, test_keys: APIKeys) -> None:
    # we need to mint a new block to update timestamp
    mint_new_block(test_keys, local_web3)
    allowed_difference = 15  # seconds
    chain_timestamp = DebuggingContract().getNow(local_web3)
    utc_timestamp = int(utcnow().timestamp())
    assert (
        abs(chain_timestamp - utc_timestamp) <= allowed_difference
    ), f"chain_timestamp and utc_timestamp differ by more than {allowed_difference} seconds: {chain_timestamp=} {utc_timestamp=}"


def test_now_failed(local_web3: Web3, test_keys: APIKeys) -> None:
    # Sleep a little to let the local chain go out of sync without updating the block
    allowed_difference = 3  # seconds
    time.sleep(allowed_difference + 1)  # safety margin for assertion
    chain_timestamp = DebuggingContract().getNow(local_web3)
    utc_timestamp = int(utcnow().timestamp())
    assert (
        abs(chain_timestamp - utc_timestamp) >= allowed_difference
    ), f"without minting a new block, timestamps should differ by more than {allowed_difference} seconds: {chain_timestamp=} {utc_timestamp=}"


def test_now_datetime(local_web3: Web3, test_keys: APIKeys) -> None:
    # we need to mint a new block to update timestamp
    mint_new_block(test_keys, local_web3)
    allowed_difference = 15  # seconds
    chain_datetime = DebuggingContract().get_now(local_web3)
    utc_datetime = utcnow()
    actual_difference = (utc_datetime - chain_datetime).total_seconds()
    assert (
        actual_difference <= allowed_difference
    ), f"chain_datetime and utc_datetime differ by more than {allowed_difference} seconds: {chain_datetime=} {utc_datetime=} {actual_difference=}"


def test_send_xdai_with_data(local_web3: Web3, accounts: list[TestAccount]) -> None:
    value = xdai_to_wei(xDai(10))
    message = "Hello there!"
    from_account = accounts[0]
    to_account = accounts[1]

    tx_receipt = send_xdai_to(
        web3=local_web3,
        from_private_key=private_key_type(from_account.private_key),
        to_address=to_account.address,
        value=value,
        data_text=message,
    )

    # Check that we can get the original message
    transaction = local_web3.eth.get_transaction(tx_receipt.transactionHash)
    transaction_message = local_web3.to_text(transaction.input)
    assert transaction_message == message

    # Check that the value is correct
    assert transaction.value == value
