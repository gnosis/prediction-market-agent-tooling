import typing as t

import pytest
import requests
from ape import accounts as ape_accounts
from ape.managers import ChainManager
from ape_test import TestAccount
from dotenv import load_dotenv
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import URI, ChecksumAddress
from safe_eth.eth import EthereumClient
from web3 import Web3
from web3.types import TxReceipt

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ABI,
    HexAddress,
    PrivateKey,
    private_key_type,
    xDai,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.web3_utils import prepare_tx, send_xdai_to


@pytest.fixture(autouse=True, scope="session")
def load_env() -> None:
    load_dotenv()


@pytest.fixture(scope="session")
def local_web3(load_env: None, chain: ChainManager) -> t.Generator[Web3, None, None]:
    print("entering fixture local_web3")

    if (tenderly_fork_rpc := APIKeys().TENDERLY_FORK_RPC) is not None:
        print("using tenderly rpc")
        w3 = Web3(Web3.HTTPProvider(tenderly_fork_rpc))
        print("funding test accounts on tenderly")
        eoa_accounts: list[TestAccount] = keep_only_eoa_accounts(
            ape_accounts.test_accounts, w3
        )
        fund_account_on_tenderly(
            tenderly_fork_rpc, [a.address for a in eoa_accounts], xDai(1000)
        )
        yield w3
    else:
        print("using foundry")
        with chain.network_manager.parse_network_choice(
            "gnosis:mainnet_fork:foundry"
        ) as provider:
            w3 = Web3(Web3.HTTPProvider(provider.http_uri))
            yield w3

    print("exiting fixture local_web3")


@pytest.fixture(scope="session")
def eoa_accounts(local_web3: Web3) -> list[TestAccount]:
    # We filter out accounts that are smart accounts because our methods `send_xdai_to` fails in that case (we are using
    # legacy transactions)
    # For ex, see https://gnosis.blockscout.com/address/0x70997970C51812dc3A010C7d01b50e0d17dc79C8?tab=contract_code
    # This account corresponds to foundry account # 1
    return keep_only_eoa_accounts(ape_accounts.test_accounts, local_web3)


def keep_only_eoa_accounts(
    accounts: list[TestAccount], web3: Web3
) -> list[TestAccount]:
    return list(
        filter(
            lambda acc: web3.eth.get_code(account=acc.address).hex() == "0x", accounts
        )
    )


@pytest.fixture(scope="module")
def local_ethereum_client(local_web3: Web3) -> EthereumClient:
    return EthereumClient(URI(local_web3.provider.endpoint_uri))  # type: ignore


@pytest.fixture(scope="session")
def test_keys(eoa_accounts: list[TestAccount]) -> APIKeys:
    account = eoa_accounts[0]

    # Using a standard Anvil account with enough xDAI.
    return APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(account.private_key), SAFE_ADDRESS=None
    )


def fund_account_on_tenderly(
    fork_rpc: str, addresses: list[HexAddress], balance: xDai
) -> None:
    payload = {
        "jsonrpc": "2.0",
        "method": "tenderly_setBalance",
        "params": [addresses, f"0x{balance.as_xdai_wei.value:X}"],
    }
    response = requests.post(fork_rpc, json=payload)
    response.raise_for_status()


def create_and_fund_random_account(
    web3: Web3, private_key: PrivateKey, deposit_amount: xDai = xDai(10)
) -> LocalAccount:
    fresh_account: LocalAccount = Account.create()
    send_xdai_to(
        web3=web3,
        from_private_key=private_key,
        to_address=fresh_account.address,
        value=deposit_amount.as_xdai_wei,
    )
    return fresh_account


def execute_tx_from_impersonated_account(
    web3: Web3,
    impersonated_account: LocalAccount,
    contract_address: ChecksumAddress,
    contract_abi: ABI,
    function_name: str,
    function_params: t.Optional[list[t.Any] | dict[str, t.Any]] = None,
) -> TxReceipt:
    with ape_accounts.use_sender(impersonated_account.address) as s:
        tx_params = prepare_tx(
            web3=web3,
            contract_address=contract_address,
            contract_abi=contract_abi,
            from_address=s.address,
            function_name=function_name,
            function_params=function_params,
        )

        send_tx = web3.eth.send_transaction(tx_params)
        # And wait for the receipt.
        tx_receipt = web3.eth.wait_for_transaction_receipt(send_tx)
        return tx_receipt


@pytest.fixture(scope="session")
def omen_subgraph_handler() -> OmenSubgraphHandler:
    return OmenSubgraphHandler()
