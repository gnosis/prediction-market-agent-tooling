# inspired by https://github.com/polywrap/AutoTx/
import re
import sys
from typing import Optional, cast

from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress, HexStr
from gnosis.eth import EthereumClient, EthereumNetwork
from gnosis.eth.constants import NULL_ADDRESS
from gnosis.eth.multicall import Multicall
from gnosis.safe import Safe, SafeTx, SafeOperation
from gnosis.safe.api import TransactionServiceApi
from gnosis.safe.api.base_api import SafeAPIException
from gnosis.safe.multi_send import MultiSend, MultiSendOperation, MultiSendTx
from hexbytes import HexBytes
from web3 import Web3
from web3.types import TxParams, TxReceipt

from prediction_market_agent_tooling.deploy.safe.constants import (
    MULTI_SEND_ADDRESS,
    GAS_PRICE_MULTIPLIER,
    MULTI_CALL_GNOSIS_ADDRESS,
    MASTER_COPY_ADDRESS,
    MASTER_COPY_L2_ADDRESS,
)
from prediction_market_agent_tooling.deploy.safe.deploy_safe_with_create2 import (
    deploy_safe_with_create2,
)
from prediction_market_agent_tooling.deploy.safe.utils import (
    get_erc20_balance,
    PreparedTx,
)
from prediction_market_agent_tooling.tools.gnosis_rpc import get_balance

ChainId = EthereumNetwork


class SafeManager:
    multisend: MultiSend | None = None
    safe_nonce: int | None = None
    gas_multiplier: float | None = GAS_PRICE_MULTIPLIER
    dev_account: LocalAccount | None = None
    network: ChainId | None = None
    transaction_service_url: str | None = None
    address: ChecksumAddress
    use_tx_service: bool

    def __init__(self, client: EthereumClient, agent: LocalAccount, safe: Safe | None):
        self.client = client
        self.web3 = self.client.w3
        self.agent = agent
        self.use_tx_service = False
        self.safe_nonce = None
        self.safe = safe
        if self.safe:
            self.address = safe.address

    @classmethod
    def deploy_safe(
        cls,
        client: EthereumClient,
        dev_account: LocalAccount,
        agent: LocalAccount,
        owners: list[str],
        threshold: int,
    ) -> "SafeManager":
        safe_address = deploy_safe_with_create2(client, dev_account, owners, threshold)

        manager = cls(
            client, agent, Safe(Web3.to_checksum_address(safe_address), client)
        )
        manager.dev_account = dev_account

        manager.multisend = MultiSend(
            client, address=Web3.to_checksum_address(MULTI_SEND_ADDRESS)
        )

        return manager

    @classmethod
    def connect(
        cls,
        client: EthereumClient,
        safe_address: ChecksumAddress,
        agent: LocalAccount,
    ) -> "SafeManager":
        safe = Safe(Web3.to_checksum_address(safe_address), client)

        manager = cls(client, agent, safe)

        manager.multisend = MultiSend(
            client, address=Web3.to_checksum_address(MULTI_SEND_ADDRESS)
        )

        return manager

    def connect_tx_service(
        self, network: ChainId, transaction_service_url: str
    ) -> None:
        self.use_tx_service = True
        self.network = network
        self.transaction_service_url = transaction_service_url

    def disconnect_tx_service(self) -> None:
        self.use_tx_service = False
        self.network = None
        self.transaction_service_url = None

    def connect_multisend(self, address: ChecksumAddress) -> None:
        self.multisend = MultiSend(self.client, address=address)

    def connect_multicall(self, address: ChecksumAddress) -> None:
        self.client.multicall = Multicall(self.client, address)

    def deploy_multicall(self) -> None:
        if not self.dev_account:
            raise ValueError(
                "Dev account not set. This function should not be called in production."
            )
        multicall_addr = MULTI_CALL_GNOSIS_ADDRESS
        self.connect_multicall(multicall_addr)

    def build_multisend_tx(
        self, txs: list[TxParams], safe_nonce: Optional[int] = None
    ) -> SafeTx:
        if not self.multisend:
            raise Exception("No multisend contract address has been set to SafeManager")

        multisend_txs = [
            MultiSendTx(
                MultiSendOperation.CALL,
                Web3.to_checksum_address(tx["to"]),
                tx["value"],
                tx["data"],
            )
            for tx in txs
        ]
        safe_multisend_data = self.multisend.build_tx_data(multisend_txs)

        safe_tx = self.safe.build_multisig_tx(
            to=Web3.to_checksum_address(self.multisend.address),
            value=sum(tx["value"] for tx in txs),
            data=safe_multisend_data,
            operation=SafeOperation.DELEGATE_CALL.value,
            safe_nonce=self.track_nonce(safe_nonce),
        )

        return safe_tx

    def build_tx(self, tx: TxParams, safe_nonce: Optional[int] = None) -> SafeTx:
        safe_tx = SafeTx(
            self.client,
            self.address,
            Web3.to_checksum_address(tx["to"]) if tx["to"] else None,
            tx["value"],
            cast(bytes, tx["data"]),
            0,
            0,
            0,
            self.gas_price(),
            None,
            self.address,
            safe_nonce=self.track_nonce(safe_nonce),
        )
        safe_tx.safe_tx_gas = self.safe.estimate_tx_gas(
            safe_tx.to, safe_tx.value, safe_tx.data, safe_tx.operation
        )
        safe_tx.base_gas = self.safe.estimate_tx_base_gas(
            safe_tx.to,
            safe_tx.value,
            safe_tx.data,
            safe_tx.operation,
            NULL_ADDRESS,
            safe_tx.safe_tx_gas,
        )

        return safe_tx

    def execute_tx(self, tx: TxParams, safe_nonce: Optional[int] = None) -> HexBytes:
        if not self.dev_account:
            raise ValueError(
                "Dev account not set. This function should not be called in production."
            )

        try:
            safe_tx = self.build_tx(tx, safe_nonce)

            safe_tx.sign(self.agent.key.hex())

            safe_tx.call(tx_sender_address=self.dev_account.address)

            tx_hash, _ = safe_tx.execute(
                tx_sender_private_key=self.dev_account.key.hex()
            )

            print(f"Executed safe tx hash: {tx_hash.hex()}")

            return tx_hash
        except Exception as e:
            extracted_message = re.search(r"revert: ([^,]+)", str(e))
            if extracted_message:
                raise Exception(extracted_message.group(0))

            raise Exception("Unknown error executing transaction", e)

    def execute_multisend_tx(
        self, txs: list[TxParams], safe_nonce: Optional[int] = None
    ) -> HexBytes:
        if not self.dev_account:
            raise ValueError(
                "Dev account not set. This function should not be called in production."
            )

        safe_tx = self.build_multisend_tx(txs, safe_nonce)

        safe_tx.sign(self.agent.key.hex())

        safe_tx.call(tx_sender_address=self.dev_account.address)

        tx_hash, _ = safe_tx.execute(tx_sender_private_key=self.dev_account.key.hex())

        return tx_hash

    def post_transaction(self, tx: TxParams, safe_nonce: Optional[int] = None) -> None:
        if not self.network:
            raise Exception("Network not defined for transaction service")

        try:
            ts_api = TransactionServiceApi(
                self.network,
                ethereum_client=self.client,
                base_url=self.transaction_service_url,
            )

            safe_tx = self.build_tx(tx, safe_nonce)
            safe_tx.sign(self.agent.key.hex())

            ts_api.post_transaction(safe_tx)
        except SafeAPIException as e:
            if "is not an owner or delegate" in str(e):
                sys.exit(
                    f"Agent with address {self.agent.address} is not a signer of the safe with address {self.address}. Please add it and try again"
                )

    def post_multisend_transaction(
        self, txs: list[TxParams], safe_nonce: Optional[int] = None
    ) -> None:
        if not self.network:
            raise Exception("Network not defined for transaction service")

        ts_api = TransactionServiceApi(
            self.network,
            ethereum_client=self.client,
            base_url=self.transaction_service_url,
        )

        tx = self.build_multisend_tx(txs, safe_nonce)
        tx.sign(self.agent.key.hex())

        ts_api.post_transaction(tx)

    def send_tx(self, tx: TxParams, safe_nonce: Optional[int] = None) -> str | None:
        if self.use_tx_service:
            self.post_transaction(tx, safe_nonce)
            return None
        else:
            hash = self.execute_tx(tx, safe_nonce)
            return hash.hex()

    def send_tx_batch(
        self,
        txs: list[PreparedTx],
        require_approval: bool,
        safe_nonce: Optional[int] = None,
    ) -> bool:  # Returns true if successful
        print("=" * 50)

        if not txs:
            print("No transactions to send.")
            return True

        start_nonce = self.track_nonce(safe_nonce)

        transactions_info = "\n".join(
            [
                f"{i + 1}. {tx.summary} (nonce: {start_nonce + i})"
                for i, tx in enumerate(txs)
            ]
        )

        print(f"Batched transactions:\n{transactions_info}")

        if self.use_tx_service:
            if require_approval:
                response = input(
                    "Do you want the above transactions to be sent to your smart account? (y/n): "
                )

                if response.lower() != "y":
                    print("Transactions not sent to your smart account (declined).")
                    return False
            else:
                print(
                    "Non-interactive mode enabled. Transactions will be sent to your smart account without approval."
                )

            print("Sending transactions to your smart account...")

            for i, tx in enumerate([prepared_tx.tx for prepared_tx in txs]):
                self.send_tx(tx, start_nonce + i)

            print("Transactions sent to your smart account for signing.")

            return True
        else:
            if require_approval:
                response = input(
                    "Do you want to execute the above transactions? (y/n): "
                )

                if response.lower() != "y":
                    print("Transactions not executed (declined).")
                    return False
            else:
                print(
                    "Non-interactive mode enabled. Transactions will be executed without approval."
                )

            print("Executing transactions...")

            for i, prepared_tx in enumerate([prepared_tx for prepared_tx in txs]):
                try:
                    self.send_tx(prepared_tx.tx, start_nonce + i)
                except Exception as e:
                    raise Exception(f"{prepared_tx.summary} failed with error: {e}")

            print("Transactions executed.")

            return True

    def send_empty_tx(self, safe_nonce: Optional[int] = None) -> str | None:
        tx: TxParams = {
            "to": self.address,
            "value": self.web3.to_wei(0, "ether"),
            "data": b"",
            "from": self.address,
        }

        return self.send_tx(tx, safe_nonce)

    def wait(self, tx_hash: HexBytes) -> TxReceipt:
        return self.web3.eth.wait_for_transaction_receipt(tx_hash)

    def balance_of(self, token_address: ChecksumAddress | None = None) -> float:
        if token_address is None:
            return get_balance(self.address)
        else:
            return get_erc20_balance(self.web3, token_address, self.address)

    def nonce(self) -> int:
        return self.safe.retrieve_nonce()

    def gas_price(self) -> int:
        return (
            self.web3.eth.gas_price
            if self.gas_multiplier is None
            else int(self.web3.eth.gas_price * self.gas_multiplier)
        )

    def track_nonce(self, safe_nonce: Optional[int] = None) -> int:
        if safe_nonce is None:
            if self.safe_nonce is None:
                self.safe_nonce = self.nonce()
            else:
                self.safe_nonce += 1
            return self.safe_nonce
        else:
            return safe_nonce

    @staticmethod
    def is_valid_safe(client: EthereumClient, address: ChecksumAddress) -> bool:
        w3 = client.w3
        if w3.eth.get_code(Web3.to_checksum_address(address)) != w3.to_bytes(
            hexstr=HexStr("0x")
        ):
            safe = Safe(Web3.to_checksum_address(address), client)
            master_copy_address = safe.retrieve_master_copy_address()
            return master_copy_address in [MASTER_COPY_ADDRESS, MASTER_COPY_L2_ADDRESS]
        else:
            return False
