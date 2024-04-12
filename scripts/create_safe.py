from decimal import Decimal

from eth_account import Account
from eth_typing import URI
from gnosis.eth import EthereumClient
from gnosis.safe import Safe
from gnosis.safe.safe_signature import SafeSignature
from pydantic import SecretStr
from web3 import Web3
from web3.gas_strategies.time_based import fast_gas_price_strategy

from prediction_market_agent_tooling.deploy.safe.safe_manager import SafeManager
from prediction_market_agent_tooling.deploy.safe.utils import send_eth
from prediction_market_agent_tooling.gtypes import xDai, PrivateKey
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
    OmenFixedProductMarketMakerContract,
)
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


def approve_wxdai(
    spender: str, amount: xDai, from_private_key: SecretStr, w3: Web3, tx_params=None
):
    wxDAI = WrappedxDaiContract()
    approve_tx = wxDAI.approve(
        Web3.to_checksum_address(spender),
        xdai_to_wei(amount),
        from_private_key=PrivateKey(from_private_key),
        web3=w3,
        tx_params=tx_params,
    )

    signed_approve = w3.eth.account.sign_transaction(
        approve_tx, private_key=from_private_key.get_secret_value()
    )
    approve_tx_hash = w3.eth.send_raw_transaction(signed_approve.rawTransaction)
    return approve_tx_hash


def main():
    RPC_URL = "https://rpc.tenderly.co/fork/bc427d37-acad-41d2-8f21-45a32b12c2ec"
    # k = APIKeys()
    # client = EthereumClient()
    client = EthereumClient(URI(RPC_URL))
    client.w3.eth.set_gas_price_strategy(fast_gas_price_strategy)
    print(client.w3.is_connected())
    # sys.exit(1)

    # # Add liquidity to a market
    market_id = Web3.to_checksum_address("0x327dc303099f147f3c44e877d2217db5c9b94771")
    market = OmenFixedProductMarketMakerContract(address=market_id)
    market_contract = client.w3.eth.contract(address=market.address, abi=market.abi)
    funding_wei = xdai_to_wei(xDai(Decimal(1)))

    private_key_anvil1 = (
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    )
    private_key_anvil2 = (
        "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
    )
    account = Account.from_key(private_key_anvil1)
    account2 = Account.from_key(private_key_anvil2)
    # s = SafeManager(client, account, None)
    # owners = [Web3.to_checksum_address(account.address), account2.address]
    # m = s.deploy_safe(client, account, account, owners, 1)
    # already deployed
    safe = Safe(
        Web3.to_checksum_address("0xE1f1538ABa3d76Ae934D8945D47705d322087c73"), client
    )
    m = SafeManager(client, account, safe)
    m.dev_account = account
    safe = m.safe

    # s.execute_tx(unsent_billboard_tx)
    send_eth(account, safe.address, xdai_to_wei(xDai(Decimal(5))), client.w3)
    unsent_billboard_tx = market_contract.functions.addFunding(
        funding_wei, []
    ).build_transaction(
        {
            "from": account.address,
            "nonce": client.w3.eth.get_transaction_count(account.address),
            "gas": 750000,
        }
    )
    # unsent_tx = market_contract.functions.buy(
    #     funding_wei,
    #     1,
    #     0,
    # ).build_transaction(
    #     {
    #         "from": account.address,
    #         "nonce": client.w3.eth.get_transaction_count(account.address),
    #         "gas": 750000,
    #     }
    # )
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
    approve_hash1 = approve_wxdai(
        Web3.to_checksum_address(market_id),
        xDai(Decimal(10)),
        PrivateKey(SecretStr(account.key.hex())),
        client.w3,
    )
    # ToDo - Unclear how to approve someone to spend wxDAI on behalf ot the safe. GH issue opened.
    approve_hash2 = approve_wxdai(
        Web3.to_checksum_address(market_id),
        xDai(Decimal(10)),
        PrivateKey(SecretStr(account.key.hex())),
        client.w3,
        tx_params={"from": safe.address},
    )

    # ToDo - safe should have wxDAI

    # Send the raw transaction:
    # tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    # w3.eth.wait_for_transaction_receipt(tx_hash)
    # ToDo - execute buy tx via safe
    # rpc_client = EthereumClient(ethereum_node_url=URI(RPC_URL))
    # safe = Safe(safe_address, client)
    # deploy
    # s = SafeManager(client, account, safe)

    safe_tx = safe.build_multisig_tx(
        unsent_billboard_tx["to"],
        unsent_billboard_tx["value"],
        unsent_billboard_tx["data"],
        safe_tx_gas=750000,
        # gas_price=int(Wei(int(client.w3.eth.gas_price)) * 1.1),  # self.gas_price(),
    )
    safe_tx.sign(account.key.hex())
    # safe_tx.call()  # check it works
    safe_tx.execute(account.key.hex(), tx_gas=7500000)
    print("done")


if __name__ == "__main__":
    main()
