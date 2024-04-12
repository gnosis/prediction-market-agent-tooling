from decimal import Decimal

from eth_account import Account
from eth_typing import URI
from gnosis.eth import EthereumClient
from pydantic import SecretStr
from web3 import Web3
from web3.gas_strategies.time_based import fast_gas_price_strategy
from web3.types import Wei

from prediction_market_agent_tooling.deploy.safe.safe_manager import SafeManager
from prediction_market_agent_tooling.deploy.safe.utils import send_eth
from prediction_market_agent_tooling.gtypes import xDai, PrivateKey
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
    OmenFixedProductMarketMakerContract,
)
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


def test_safe_creation():
    RPC_URL = "https://rpc.tenderly.co/fork/187186c1-794b-4a23-9d83-c4d25a9c2181"
    # k = APIKeys()

    # client = EthereumClient()
    client = EthereumClient(URI(RPC_URL))
    client.w3.eth.set_gas_price_strategy(fast_gas_price_strategy)

    # ganache_key1 = "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"
    # ganache_key2 = "0x6cbed15c793ce57650b9877cf6fa156fbef513c4e6134f022a85b1ffdd59b2a1"
    # ganache1 = Account.from_key(ganache_key1)
    # ganache2 = Account.from_key(ganache_key2)
    # account = ganache1
    # safe_address = Web3.to_checksum_address(
    #     "0x86BcE0e9D0577184bE2D5d7588B316e3Be1Cf2f8"
    # )
    # s = SafeManager(client, account, None)
    # owners = [Web3.to_checksum_address(account.address), ganache2.address]
    #
    # m = s.deploy_safe(client, account, account, owners, 1)
    # print(m.address, m)

    # safe_contract = Safe(m.address, client)
    # is_valid = m.is_valid_safe(client, m.safe.address)
    # assert m.safe.get_version() == "1.4.1"
    # assert is_valid
    # # send 100 xDAI to Safe
    # send_eth(ganache1, m.safe.address, xdai_to_wei(xDai(Decimal(1))), client.w3)
    # # assert balance
    # print(f"version {m.safe.retrieve_version()}")
    # # get balance from conditional tokens
    #
    # balance_safe = client.w3.eth.get_balance(m.safe.address)
    # # balance_safe = get_balances(m.safe.address)
    # assert balance_safe == 1e18
    # print(f"balance_safe {balance_safe}")
    #
    # print(f"balance ganache1 {client.w3.eth.get_balance(ganache1.address)}")
    #
    # # Add liquidity to a market
    market_id = Web3.to_checksum_address("0x327dc303099f147f3c44e877d2217db5c9b94771")
    market = OmenFixedProductMarketMakerContract(address=market_id)
    market_contract = client.w3.eth.contract(address=market.address, abi=market.abi)
    funding_wei = xdai_to_wei(xDai(Decimal(1)))
    # from_address = ganache1.address
    # tx_params = {}
    # print(f"nonce 1 {client.w3.eth.get_transaction_count(from_address)}")
    # print(f"nonce 2 {local_w3.eth.get_transaction_count(from_address)}")
    # tx_params["nonce"] = tx_params.get(
    #     "nonce", client.w3.eth.get_transaction_count(from_address)
    # )
    # tx_params["from"] = tx_params.get("from", from_address)
    #
    # # Build the transaction.
    # built_tx = market.buy(
    #     funding_wei,
    #     1,
    #     OmenOutcomeToken(0),
    #     from_private_key=PrivateKey(SecretStr(ganache1.key.hex())),
    #     web3=local_w3,
    # )
    #
    # # function_call = market_contract.functions.addFunding(funding_wei, []).build_transaction()  # type: ignore # TODO: Fix Mypy, as this works just OK.
    # # signed_tx = function_call.build_transaction(tx_params)
    # tx_hash = m.execute_tx(built_tx)
    # m.safe.estimate_tx_base_gas(
    #     built_tx["to"],
    #     built_tx["value"],
    #     built_tx["data"],
    # )
    #
    # # signed_tx = market.addFunding(
    # #    funding_wei, from_private_key=PrivateKey(SecretStr(ganache1.key.hex()))
    # # )
    # # funding_tx_hash = m.execute_tx(signed_tx)
    #
    # # ToDo - check if liquidity was added
    # balance = market.balanceOf(ganache1.address, client.w3)
    # assert balance == funding_wei
    #
    # # # executeTx - send wxDAI
    # # wxdai = WrappedxDaiContract()
    # # wxdai_contract = client.w3.eth.contract(address=wxdai.address, abi=wxdai.abi)
    # #
    # # tx_params = wxdai_contract.functions.approve(
    # #     m.safe.address, xdai_to_wei(xDai(Decimal(2)))
    # # ).build_transaction({"from": account.address})
    # # tx_hash = m.execute_tx(tx_params)
    # # print(f"approved {tx_hash}")
    # #
    # # # check that allowance changed
    # # tx_params = wxdai_contract.functions.allowance(account.address, m.safe.address)
    # # allowance_wxdai = tx_params.call()
    # # print(f"allowance wxDAI {allowance_wxdai}")
    # # assert allowance_wxdai == 2e18
    # # ToDo - execute tx
    # m.build_multisend_tx(tx_params)

    #########################
    # tx params
    # w3 = Web3(Web3.HTTPProvider(RPC_URL))
    # tx_params = {}
    # tx_params["nonce"] = tx_params.get(
    #     "nonce", client.w3.eth.get_transaction_count(from_address)
    # )
    # tx_params["from"] = tx_params.get("from", from_address)
    # simply send and execute tx
    private_key_anvil1 = (
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    )
    private_key_anvil2 = (
        "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
    )
    account = Account.from_key(private_key_anvil1)
    account2 = Account.from_key(private_key_anvil2)

    # deploy safe
    # s = SafeManager(client, account, None)

    # m = s.deploy_safe(client, account, account, owners, 1)
    # print(m.address, m)
    # safe_address_local
    # safe_address = Web3.to_checksum_address(
    #    "0xd4E3A21De256886581a9Ab8084b82dA94beA2d6E"
    # )
    s = SafeManager(client, account, None)
    owners = [Web3.to_checksum_address(account.address), account2.address]
    m = s.deploy_safe(client, account, account, owners, 1)
    m.dev_account = account
    safe = m.safe

    # s.execute_tx(unsent_billboard_tx)
    send_eth(account, safe.address, xdai_to_wei(xDai(Decimal(5))), client.w3)
    unsent_billboard_tx = market_contract.functions.buy(
        funding_wei,
        1,
        0,
    ).build_transaction(
        {
            "from": account.address,
            "nonce": client.w3.eth.get_transaction_count(account.address),
            "gas": 700000,
        }
    )
    # signed_tx = client.w3.eth.account.sign_transaction(
    #    unsent_billboard_tx, private_key=account.key
    # )
    # ToDo - not enough wxDAI
    wxDAI = WrappedxDaiContract()
    deposit_tx = wxDAI.deposit(
        xdai_to_wei(xDai(Decimal(1))),
        from_private_key=PrivateKey(SecretStr(account.key.hex())),
        web3=client.w3,
    )
    signed_deposit = client.w3.eth.account.sign_transaction(
        deposit_tx, private_key=account.key
    )
    deposit_tx_hash = client.w3.eth.send_raw_transaction(signed_deposit.rawTransaction)
    # Allowance
    approve_tx = wxDAI.approve(
        Web3.to_checksum_address(market_id),
        xdai_to_wei(xDai(Decimal(10))),
        from_private_key=PrivateKey(SecretStr(account.key.hex())),
        web3=client.w3,
    )
    signed_approve = client.w3.eth.account.sign_transaction(
        approve_tx, private_key=account.key
    )
    approve_tx_hash = client.w3.eth.send_raw_transaction(signed_approve.rawTransaction)

    # Send the raw transaction:
    # tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    # w3.eth.wait_for_transaction_receipt(tx_hash)
    # ToDo - execute buy tx via safe
    # rpc_client = EthereumClient(ethereum_node_url=URI(RPC_URL))
    # safe = Safe(safe_address, client)
    # deploy
    # s = SafeManager(client, account, safe)
    result = m.execute_tx(unsent_billboard_tx)
    print(f"result {result}")
    # safe_tx = safe.build_multisig_tx(
    #     unsent_billboard_tx["to"],
    #     unsent_billboard_tx["value"],
    #     unsent_billboard_tx["data"],
    #     gas_price=int(Wei(int(client.w3.eth.gas_price)) * 1.1),  # self.gas_price(),
    # )
    # safe_tx.sign(private_key=account.key.hex())
    # safe_tx.call()  # check it works
    # safe_tx.execute(account.key.hex(), tx_gas=700000)
    print("done")
