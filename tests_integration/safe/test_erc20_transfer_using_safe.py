from eth_account import Account
from gnosis.safe import Safe
from web3 import Web3
from web3.types import Wei

from prediction_market_agent_tooling.config import PrivateCredentials
from prediction_market_agent_tooling.markets.omen.omen_contracts import OmenCollateralTokenContract
from prediction_market_agent_tooling.tools.web3_utils import send_xdai_to, xdai_to_wei
from tests_integration.local_chain_utils import get_anvil_test_accounts


def test_erc20_send_updates_balance(test_safe: Safe, test_credentials: PrivateCredentials,
                                    local_web3: Web3):

    # Deploy safe
    # send 10 xDAI to safe
    account = Account.from_key(test_credentials.private_key.get_secret_value())
    account2 = get_anvil_test_accounts()[1]


    collateral_token_contract = OmenCollateralTokenContract()
    # deposit from account 1
    amount_deposit = xdai_to_wei(Wei(10))
    collateral_token_contract.deposit(test_credentials, amount_deposit, web3=local_web3)
    assert collateral_token_contract.balanceOf(test_credentials.public_key, local_web3) >= amount_deposit
    # send wxDAI to Safe
    collateral_token_contract.transferFrom(
        private_credentials=test_credentials,
        sender=account.address,
        recipient=test_safe.address,
        amount_wei=amount_deposit,
        web3=local_web3,
    )
    # assert balance
    balance_safe = collateral_token_contract.balanceOf(test_safe.address, local_web3)
    assert balance_safe >= amount_deposit
    # approve account2 for spending safe
    test_credentials.safe_address = test_safe.address
    collateral_token_contract.approve(test_credentials, account2.address, amount_deposit, web3=local_web3)
    # send from safe -> account2
    collateral_token_contract.transferFrom(
        private_credentials=test_credentials,
        sender=test_safe.address,
        recipient=account2.address,
        amount_wei=amount_deposit,
        web3=local_web3,
    )
    # assert balance safe
    updated_balance_safe = collateral_token_contract.balanceOf(test_safe.address, local_web3)
    assert (balance_safe - updated_balance_safe) == amount_deposit
    # assert balance account2
    updated_balance_account2 = collateral_token_contract.balanceOf(account2.address, local_web3)
    assert updated_balance_account2 == amount_deposit