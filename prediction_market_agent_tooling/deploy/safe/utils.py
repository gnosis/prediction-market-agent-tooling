import os

from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress
from gnosis.eth import EthereumClient
from gnosis.eth.multicall import Multicall
from hexbytes import HexBytes
from web3 import Web3
from web3.types import TxParams, TxReceipt, Wei

from prediction_market_agent_tooling.gtypes import ABI
from prediction_market_agent_tooling.tools.contract import abi_field_validator


class PreparedTx:
    summary: str
    tx: TxParams

    def __init__(self, summary: str, tx: TxParams):
        self.summary = summary
        self.tx = tx


def send_tx(w3: Web3, tx: TxParams, account: LocalAccount) -> bytes:
    tx["from"] = account.address
    if "nonce" not in tx:
        tx["nonce"] = w3.eth.get_transaction_count(
            account.address, block_identifier="pending"
        )

    if "gasPrice" not in tx and "maxFeePerGas" not in tx:
        tx["gasPrice"] = w3.eth.gas_price

    if "gas" not in tx:
        tx["gas"] = w3.eth.estimate_gas(tx)

    signed_tx = account.sign_transaction(tx)  # type: ignore
    tx_hash = w3.eth.send_raw_transaction(bytes(signed_tx.rawTransaction))
    print("Send TX: ", tx_hash.hex())
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    assert tx_receipt["status"] == 1, "Error with tx %s - %s" % (tx_hash.hex(), tx)
    return tx_hash


def deploy_multicall(client: EthereumClient, account: LocalAccount) -> str:
    multicall_address = os.getenv("MULTICALL_ADDRESS")
    multicall_address = deploy(client, account)
    return multicall_address


def deploy(client: EthereumClient, account: LocalAccount) -> str:
    tx = Multicall.deploy_contract(client, account)

    if not tx.contract_address:
        raise ValueError("Multicall contract address is not set")

    client.w3.eth.wait_for_transaction_receipt(HexBytes(tx.tx_hash))

    print("Deployed Multicall to: ", tx.contract_address)

    return tx.contract_address


def get_erc20_balance(
    web3: Web3, token_address: ChecksumAddress, account: ChecksumAddress
) -> float:
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/erc20.abi.json",
        )
    )
    erc20 = web3.eth.contract(address=token_address, abi=abi)
    decimals: int = erc20.functions.decimals().call()
    balance: int = erc20.functions.balanceOf(account).call()
    return balance / 10**decimals  # type: ignore


def send_eth(
    account: LocalAccount, to: ChecksumAddress, value: Wei, web3: Web3
) -> tuple[str, TxReceipt]:
    tx: TxParams = {
        "from": account.address,
        "to": to,
        "value": value,
        "nonce": web3.eth.get_transaction_count(account.address),
        "maxFeePerGas": 2000000000,
        "maxPriorityFeePerGas": 1000000000,
        "chainId": web3.eth.chain_id,
    }

    gas = web3.eth.estimate_gas(tx)
    tx.update({"gas": gas})

    signed_tx = account.sign_transaction(tx)  # type: ignore
    web3.eth.send_raw_transaction(signed_tx.rawTransaction)
    receipt = web3.eth.wait_for_transaction_receipt(signed_tx.hash)
    return receipt["transactionHash"].hex(), receipt
