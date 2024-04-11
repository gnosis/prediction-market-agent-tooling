import os

from dotenv import load_dotenv
from eth_account import Account
from eth_typing import URI
from gnosis.eth import EthereumClient
from gnosis.eth.constants import NULL_ADDRESS
from gnosis.eth.contracts import (
    get_safe_contract,
    get_safe_V1_4_1_contract,
)
from gnosis.safe import ProxyFactory
from web3 import Web3

from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


def main():
    print("start")
    load_dotenv()
    print(f"priv key {os.environ['BET_FROM_PRIVATE_KEY']}")

    # addresses.MASTER_COPIES[EthereumNetwork.MAINNET]
    MASTER_COPY_141 = Web3.to_checksum_address(
        "0x41675C099F32341bf84BFc5382aF534df5C7461a"
    )
    FALLBACK_HANDLER = Web3.to_checksum_address(
        "0xFD0732DC9E303F09FCEF3A7388AD10A83459EC99"
    )
    # CHAIN_RPC_URL = "https://rpc.tenderly.co/fork/afb295ce-87ed-4bad-a38f-f7e3b32d2932"
    # CHAIN_RPC_URL = "https://gnosis-rpc.publicnode.com"
    CHAIN_RPC_URL = "http://localhost:8545"
    PROXY_FACTORY_ADDRESS = Web3.to_checksum_address(
        "0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67"
    )

    web3 = Web3(Web3.HTTPProvider("http://localhost:8545"))

    safe_141 = get_safe_contract(web3, MASTER_COPY_141)
    account_dev = Web3.to_checksum_address("0xC073C043189b79b18508cA9330f49B007D345605")
    safe_1412 = get_safe_V1_4_1_contract(web3, MASTER_COPY_141)

    print(safe_1412)

    print(safe_141)
    # from safe-cli
    safe_creation_tx_data = HexBytes(
        safe_1412.functions.setup(
            [account_dev],
            1,
            NULL_ADDRESS,
            b"",
            FALLBACK_HANDLER,
            NULL_ADDRESS,
            0,
            NULL_ADDRESS,
        ).build_transaction({"gas": 1, "gasPrice": 1})["data"]
    )
    salt_nonce = 42
    ethereum_client = EthereumClient(URI(CHAIN_RPC_URL))
    proxy_factory = ProxyFactory(PROXY_FACTORY_ADDRESS, ethereum_client)
    expected_safe_address = proxy_factory.calculate_proxy_address(
        MASTER_COPY_141, safe_creation_tx_data, salt_nonce
    )
    account = Account.from_key(os.environ["BET_FROM_PRIVATE_KEY"])
    ethereum_tx_sent = proxy_factory.deploy_proxy_contract_with_nonce(
        account, MASTER_COPY_141, safe_creation_tx_data, salt_nonce
    )
    print(
        f"Sent tx with tx-hash={ethereum_tx_sent.tx_hash.hex()} "
        f"Safe={ethereum_tx_sent.contract_address} is being created"
    )
    print(f"Tx parameters={ethereum_tx_sent.tx}")
    # ToDo - Use dev account for this
    # ToDo - Fund the safe from dev account, send from safe to another account
    print("end")


if __name__ == "__main__":
    main()
