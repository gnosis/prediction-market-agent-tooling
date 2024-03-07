import json
import typing as t

from pydantic import BaseModel, field_validator
from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChainID,
    ChecksumAddress,
    PrivateKey,
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
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
        function_name: str,
        function_params: t.Optional[list[t.Any] | dict[str, t.Any]] = None,
        tx_params: t.Optional[TxParams] = None,
        timeout: int = 180,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """
        Used for changing a state (writing) to the contract.
        """
        web3 = web3 or self.get_web3()
        return send_function_on_contract_tx(
            web3=web3,
            contract_address=self.address,
            contract_abi=self.abi,
            from_address=from_address,
            from_private_key=from_private_key,
            function_name=function_name,
            function_params=function_params,
            tx_params=tx_params,
            timeout=timeout,
        )

    def send_with_value(
        self,
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
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
            from_address=from_address,
            from_private_key=from_private_key,
            function_name=function_name,
            function_params=function_params,
            tx_params={"value": amount_wei, **(tx_params or {})},
            timeout=timeout,
            web3=web3,
        )

    def get_web3(self) -> Web3:
        return Web3(Web3.HTTPProvider(self.CHAIN_RPC_URL))


class ContractERC20BaseClass(ContractBaseClass):
    """
    Contract base class extended by ERC-20 standard methods.
    """

    def approve(
        self,
        for_address: ChecksumAddress,
        amount_wei: Wei,
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        return self.send(
            from_address=from_address,
            from_private_key=from_private_key,
            function_name="approve",
            function_params=[
                for_address,
                amount_wei,
            ],
            tx_params=tx_params,
        )

    def deposit(
        self,
        amount_wei: Wei,
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        return self.send_with_value(
            from_address=from_address,
            from_private_key=from_private_key,
            function_name="deposit",
            amount_wei=amount_wei,
            tx_params=tx_params,
        )

    def withdraw(
        self,
        amount_wei: Wei,
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        return self.send(
            from_address=from_address,
            from_private_key=from_private_key,
            function_name="withdraw",
            function_params=[amount_wei],
            tx_params=tx_params,
        )

    def balanceOf(self, for_address: ChecksumAddress) -> Wei:
        balance: Wei = self.call("balanceOf", [for_address])
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
