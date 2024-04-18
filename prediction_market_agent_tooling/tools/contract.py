import json
import time
import typing as t
from contextlib import contextmanager

from pydantic import BaseModel, field_validator
from web3 import Web3

from prediction_market_agent_tooling.config import PrivateCredentials
from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChainID,
    ChecksumAddress,
    Nonce,
    TxParams,
    TxReceipt,
    Wei,
)
from prediction_market_agent_tooling.tools.gnosis_rpc import (
    GNOSIS_NETWORK_ID,
    GNOSIS_RPC_URL,
)
from prediction_market_agent_tooling.tools.web3_utils import (
    call_function_on_contract,
    send_function_on_contract_tx,
    send_function_on_contract_tx_using_safe,
)


def abi_field_validator(value: str) -> ABI:
    if value.endswith(".json"):
        with open(value) as f:
            value = f.read()

    try:
        json.loads(value)  # Test if it's valid JSON content.
        return ABI(value)
    except json.decoder.JSONDecodeError:
        raise ValueError(f"Invalid ABI: {value}")


@contextmanager
def wait_until_nonce_changed(
    for_address: ChecksumAddress, timeout: int = 10, sleep_time: int = 1
) -> t.Generator[None, None, None]:
    current_nonce = ContractOnGnosisChain.get_transaction_count(for_address)
    yield
    start_monotonic = time.monotonic()
    while (
        time.monotonic() - start_monotonic < timeout
        and current_nonce == ContractOnGnosisChain.get_transaction_count(for_address)
    ):
        time.sleep(sleep_time)


class ContractBaseClass(BaseModel):
    """
    Base class holding the basic requirements and tools used for every contract.
    """

    CHAIN_ID: t.ClassVar[ChainID]
    CHAIN_RPC_URL: t.ClassVar[str]

    abi: ABI
    address: ChecksumAddress

    _abi_field_validator = field_validator("abi", mode="before")(abi_field_validator)

    def call(
        self,
        function_name: str,
        function_params: t.Optional[list[t.Any] | dict[str, t.Any]] = None,
        web3: Web3 | None = None,
    ) -> t.Any:
        """
        Used for reading from the contract.
        """
        web3 = web3 or self.get_web3()
        return call_function_on_contract(
            web3=web3,
            contract_address=self.address,
            contract_abi=self.abi,
            function_name=function_name,
            function_params=function_params,
        )

    def send(
        self,
        private_credentials: PrivateCredentials,
        function_name: str,
        function_params: t.Optional[list[t.Any] | dict[str, t.Any]] = None,
        tx_params: t.Optional[TxParams] = None,
        timeout: int = 180,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """
        Used for changing a state (writing) to the contract.
        """

        if private_credentials.safe_address is not None:
            return send_function_on_contract_tx_using_safe(
                web3=web3 or self.get_web3(),
                contract_address=self.address,
                contract_abi=self.abi,
                from_private_key=private_credentials.private_key,
                safe_address=private_credentials.safe_address,
                function_name=function_name,
                function_params=function_params,
                tx_params=tx_params,
                timeout=timeout,
            )
        return send_function_on_contract_tx(
            web3=web3 or self.get_web3(),
            contract_address=self.address,
            contract_abi=self.abi,
            from_private_key=private_credentials.private_key,
            function_name=function_name,
            function_params=function_params,
            tx_params=tx_params,
            timeout=timeout,
        )

    def send_with_value(
        self,
        private_credentials: PrivateCredentials,
        function_name: str,
        amount_wei: Wei,
        function_params: t.Optional[list[t.Any] | dict[str, t.Any]] = None,
        tx_params: t.Optional[TxParams] = None,
        timeout: int = 180,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """
        Used for changing a state (writing) to the contract, including sending chain's native currency.
        """
        return self.send(
            private_credentials=private_credentials,
            function_name=function_name,
            function_params=function_params,
            tx_params={"value": amount_wei, **(tx_params or {})},
            timeout=timeout,
            web3=web3,
        )

    @classmethod
    def get_transaction_count(cls, for_address: ChecksumAddress) -> Nonce:
        return cls.get_web3().eth.get_transaction_count(for_address)

    @classmethod
    def get_web3(cls) -> Web3:
        return Web3(Web3.HTTPProvider(cls.CHAIN_RPC_URL))


class ContractERC20BaseClass(ContractBaseClass):
    """
    Contract base class extended by ERC-20 standard methods.
    """

    def approve(
        self,
        private_credentials: PrivateCredentials,
        for_address: ChecksumAddress,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            private_credentials=private_credentials,
            function_name="approve",
            function_params=[
                for_address,
                amount_wei,
            ],
            tx_params=tx_params,
            web3=web3,
        )

    def deposit(
        self,
        private_credentials: PrivateCredentials,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send_with_value(
            private_credentials=private_credentials,
            function_name="deposit",
            amount_wei=amount_wei,
            tx_params=tx_params,
            web3=web3,
        )

    def withdraw(
        self,
        private_credentials: PrivateCredentials,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            private_credentials=private_credentials,
            function_name="withdraw",
            function_params=[amount_wei],
            tx_params=tx_params,
            web3=web3,
        )

    def balanceOf(self, for_address: ChecksumAddress, web3: Web3 | None = None) -> Wei:
        balance: Wei = self.call("balanceOf", [for_address], web3=web3)
        return balance


class ContractOnGnosisChain(ContractBaseClass):
    """
    Contract base class with Gnosis Chain configuration.
    """

    CHAIN_ID = GNOSIS_NETWORK_ID
    CHAIN_RPC_URL = GNOSIS_RPC_URL


class ContractERC20OnGnosisChain(ContractERC20BaseClass, ContractOnGnosisChain):
    """
    ERC-20 standard base class with Gnosis Chain configuration.
    """
