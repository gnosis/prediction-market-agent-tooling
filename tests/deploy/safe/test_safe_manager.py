from decimal import Decimal

import web3.eth
from eth_account import Account
from gnosis.eth import EthereumClient
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.safe.safe_manager import SafeManager
from prediction_market_agent_tooling.deploy.safe.utils import send_eth
from prediction_market_agent_tooling.gtypes import xDai
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
)
from gnosis.safe import Safe, addresses
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


def test_safe_creation():
    RPC_URL = "https://light-distinguished-isle.xdai.quiknode.pro/398333e0cb68ee18d38f5cda5deecd5676754923/"
    local_w3 = Web3(Web3.HTTPProvider(RPC_URL))
    k = APIKeys()

    client = EthereumClient()
    ganache_key1 = "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"
    ganache_key2 = "0x6cbed15c793ce57650b9877cf6fa156fbef513c4e6134f022a85b1ffdd59b2a1"
    ganache1 = Account.from_key(ganache_key1)
    ganache2 = Account.from_key(ganache_key2)
    account = ganache1
    s = SafeManager(client, account, None)
    owners = [Web3.to_checksum_address(account.address), ganache2.address]
    # ToDo - Deploy 1.4.1
    m = s.deploy_safe(client, account, account, owners, 1)
    print(m)
    safe_contract = Safe(m.address, client)
    is_valid = m.is_valid_safe(client, m.safe.address)
    assert m.safe.get_version() == "1.4.1"
    assert is_valid
    # send 100 xDAI to Safe
    send_eth(ganache1, m.safe.address, xdai_to_wei(xDai(Decimal(1))), client.w3)
    # assert balance
    print(f"version {m.safe.retrieve_version()}")
    # get balance from conditional tokens
    balance_safe = client.w3.eth.get_balance(m.safe.address)
    # balance_safe = get_balances(m.safe.address)
    assert balance_safe == 1e18
    print(f"balance_safe {balance_safe}")
    # # executeTx - send wxDAI
    # wxdai = WrappedxDaiContract()
    # wxdai_contract = client.w3.eth.contract(address=wxdai.address, abi=wxdai.abi)
    #
    # tx_params = wxdai_contract.functions.approve(
    #     m.safe.address, xdai_to_wei(xDai(Decimal(2)))
    # ).build_transaction({"from": account.address})
    # tx_hash = m.execute_tx(tx_params)
    # print(f"approved {tx_hash}")
    #
    # # check that allowance changed
    # tx_params = wxdai_contract.functions.allowance(account.address, m.safe.address)
    # allowance_wxdai = tx_params.call()
    # print(f"allowance wxDAI {allowance_wxdai}")
    # assert allowance_wxdai == 2e18
    # ToDo - execute tx

    # m.build_multisend_tx(tx_params)
