import math

import pytest
from ape import accounts as ape_accounts
from ape_test import TestAccount
from eth_typing import ChecksumAddress
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type, xdai_type
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.contract import SimpleTreasuryContract
from prediction_market_agent_tooling.tools.web3_utils import send_xdai_to, xdai_to_wei
from tests_integration_with_local_chain.conftest import (
    execute_tx_from_impersonated_account,
)


@pytest.fixture
def labs_deployer() -> ChecksumAddress:
    return Web3.to_checksum_address("0x32aABa58DE76BdbA912FC14Fcc11b8Aa6227aeE9")


@pytest.fixture(scope="function")
def simple_treasury_contract() -> SimpleTreasuryContract:
    return SimpleTreasuryContract()


def test_required_nft_balance(
    local_web3: Web3, simple_treasury_contract: SimpleTreasuryContract
) -> None:
    initial_required_nft_balance = simple_treasury_contract.required_nft_balance(
        web3=local_web3
    )
    # Initial value after deployment is 3
    assert initial_required_nft_balance == 3


def test_owner(
    local_web3: Web3,
    labs_deployer: ChecksumAddress,
    simple_treasury_contract: SimpleTreasuryContract,
) -> None:
    owner = simple_treasury_contract.owner(web3=local_web3)
    assert owner == labs_deployer


def test_withdraw(
    local_web3: Web3,
    accounts: list[TestAccount],
    labs_deployer: ChecksumAddress,
    simple_treasury_contract: SimpleTreasuryContract,
) -> None:
    executor = accounts[0]
    initial_balance_executor = get_balances(executor.address, web3=local_web3).xdai
    amount_transferred = xdai_type(5)
    # Transfer all the balance to the treasury
    send_xdai_to(
        web3=local_web3,
        from_private_key=private_key_type(executor.private_key),
        to_address=simple_treasury_contract.address,
        value=xdai_to_wei(amount_transferred),
    )
    required_nfts = simple_treasury_contract.required_nft_balance(web3=local_web3)
    nft = simple_treasury_contract.nft_contract(local_web3)
    for token_id in range(required_nfts):
        # We transfer nfts to the executor for it to call withdraw.
        token_owner = nft.owner_of(token_id=token_id, web3=local_web3)
        # Impersonate accounts (only works with local chain because unsigned transactions are executed)
        with ape_accounts.use_sender(token_owner) as s:
            execute_tx_from_impersonated_account(
                web3=local_web3,
                impersonated_account=s,
                contract_address=nft.address,
                contract_abi=nft.abi,
                function_name="safeTransferFrom",
                function_params=[s.address, executor.address, token_id],
            )

    # deposit money into treasury
    assert nft.balanceOf(executor.address, web3=local_web3) == required_nfts
    # call withdraw
    keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(executor.private_key), SAFE_ADDRESS=None
    )
    simple_treasury_contract.withdraw(api_keys=keys, web3=local_web3)
    final_balance_executor = get_balances(executor.address, web3=local_web3).xdai

    # Assert treasury is empty
    final_treasury_balance = get_balances(
        simple_treasury_contract.address, web3=local_web3
    ).xdai
    assert int(final_treasury_balance) == 0
    # Assert executor got the treasury amount
    assert math.isclose(final_balance_executor, initial_balance_executor, abs_tol=0.1)
