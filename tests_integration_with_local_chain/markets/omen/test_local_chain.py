import pytest
from ape_test import TestAccount
from eth_account import Account
from numpy import isclose
from pydantic import SecretStr
from web3 import Web3
from web3.types import Wei

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    PrivateKey,
    xDai,
    xdai_type,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    is_minimum_required_balance,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.web3_utils import (
    send_xdai_to,
    wei_to_xdai,
    xdai_to_wei,
)


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
        from_private_key=PrivateKey(SecretStr(from_account.private_key)),
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
        from_private_key=PrivateKey(SecretStr(from_account.key.hex())),
        to_address=random_locked_account.address,
        value=fund_value,
    )

    balance_random = get_balances(random_locked_account.address, local_web3)
    assert xdai_to_wei(balance_random.xdai) == fund_value
    send_xdai_to(
        web3=local_web3,
        from_private_key=PrivateKey(SecretStr(random_locked_account.key.hex())),
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


@pytest.mark.parametrize(
    "address, expected",
    [
        (
            Web3.to_checksum_address(
                "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
            ),  # anvil test account 0
            True,
        ),
        (
            Web3.to_checksum_address("0x184ca44A6c3cfc05bCF7246ac14101Ddb9423eAa"),
            False,
        ),
    ],
)
def test_is_minimum_required_balance(
    address: ChecksumAddress, expected: bool, local_web3: Web3
) -> None:
    assert is_minimum_required_balance(address, xdai_type(0.5), local_web3) == expected
