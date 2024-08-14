from ape_test import TestAccount
from eth_account import Account
from numpy import isclose
from pydantic import SecretStr
from web3 import Web3
from web3.types import Wei

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import PrivateKey, xDai, xdai_type
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


def test_anvil_account_has_more_than_minimum_required_balance(
    local_web3: Web3,
    accounts: list[TestAccount],
) -> None:
    account_adr = Web3.to_checksum_address(accounts[0].address)
    assert is_minimum_required_balance(account_adr, xdai_type(0.5), local_web3)


def test_fresh_account_has_less_than_minimum_required_balance(
    local_web3: Web3,
    accounts: list[TestAccount],
) -> None:
    fresh_account_adr = Account.create().address
    account_adr = Web3.to_checksum_address(fresh_account_adr)
    assert not is_minimum_required_balance(account_adr, xdai_type(0.5), local_web3)
