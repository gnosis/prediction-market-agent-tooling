import json
import os
import time
import typing as t
from abc import ABC, abstractmethod
from contextlib import contextmanager

from pydantic import BaseModel, field_validator
from typing_extensions import Unpack
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
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
from prediction_market_agent_tooling.tools.utils import check_not_none
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
        api_keys: APIKeys,
        function_name: str,
        function_params: t.Optional[list[t.Any] | dict[str, t.Any]] = None,
        tx_params: t.Optional[TxParams] = None,
        timeout: int = 180,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """
        Used for changing a state (writing) to the contract.
        """

        if api_keys.SAFE_ADDRESS:
            return send_function_on_contract_tx_using_safe(
                web3=web3 or self.get_web3(),
                contract_address=self.address,
                contract_abi=self.abi,
                from_private_key=api_keys.bet_from_private_key,
                safe_address=api_keys.SAFE_ADDRESS,
                function_name=function_name,
                function_params=function_params,
                tx_params=tx_params,
                timeout=timeout,
            )
        return send_function_on_contract_tx(
            web3=web3 or self.get_web3(),
            contract_address=self.address,
            contract_abi=self.abi,
            from_private_key=api_keys.bet_from_private_key,
            function_name=function_name,
            function_params=function_params,
            tx_params=tx_params,
            timeout=timeout,
        )

    def send_with_value(
        self,
        api_keys: APIKeys,
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
            api_keys=api_keys,
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


class ContractProxyBaseClass(ContractBaseClass):
    """
    Contract base class for proxy contracts.
    """

    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "../abis/proxy.abi.json"
        )
    )

    def implementation(self, web3: Web3 | None = None) -> ChecksumAddress:
        address = self.call("implementation", web3=web3)
        return Web3.to_checksum_address(address)


class ContractERC20BaseClass(ContractBaseClass):
    """
    Contract base class extended by ERC-20 standard methods.
    """

    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "../abis/erc20.abi.json"
        )
    )

    def approve(
        self,
        api_keys: APIKeys,
        for_address: ChecksumAddress,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="approve",
            function_params=[
                for_address,
                amount_wei,
            ],
            tx_params=tx_params,
            web3=web3,
        )

    def transferFrom(
        self,
        api_keys: APIKeys,
        sender: ChecksumAddress,
        recipient: ChecksumAddress,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="transferFrom",
            function_params=[sender, recipient, amount_wei],
            tx_params=tx_params,
            web3=web3,
        )

    def balanceOf(self, for_address: ChecksumAddress, web3: Web3 | None = None) -> Wei:
        balance: Wei = self.call("balanceOf", [for_address], web3=web3)
        return balance

    def allowance(
        self, owner: ChecksumAddress, spender: ChecksumAddress, web3: Web3 | None = None
    ) -> Wei:
        allowance: Wei = self.call("allowance", [owner, spender], web3=web3)
        return allowance


class ExtraDepositParams(t.TypedDict):
    receiver: ChecksumAddress


class ExtraWithdrawParams(t.TypedDict):
    receiver: ChecksumAddress
    owner: ChecksumAddress


class AbstractCollateral(ABC, ContractERC20BaseClass):
    @abstractmethod
    def deposit(
        self,
        api_keys: APIKeys,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
        **kwargs: Unpack[ExtraDepositParams],
    ) -> TxReceipt:
        pass

    @abstractmethod
    def withdraw(
        self,
        api_keys: APIKeys,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
        **kwargs: Unpack[ExtraWithdrawParams],
    ) -> TxReceipt:
        pass


class ContractDepositableWrapperERC20BaseClass(AbstractCollateral):
    """
    ERC-20-wrapper standard base class. It has deposit/withdraw method for wrapping/unwrapping.
    Although this is not a standard, it's seems to be a common pattern for wrapped tokens (at least it checks out for wxDai and wETH).
    """

    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../abis/depositablewrapper_erc20.abi.json",
        )
    )

    def deposit(
        self,
        api_keys: APIKeys,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
        **kwargs: Unpack[ExtraDepositParams],
    ) -> TxReceipt:
        return self.send_with_value(
            api_keys=api_keys,
            function_name="deposit",
            amount_wei=amount_wei,
            tx_params=tx_params,
            web3=web3,
        )

    def withdraw(
        self,
        api_keys: APIKeys,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
        **kwargs: Unpack[ExtraWithdrawParams],
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="withdraw",
            function_params=[amount_wei],
            tx_params=tx_params,
            web3=web3,
        )


class ContractERC4626BaseClass(AbstractCollateral):
    """
    Class for ERC-4626, which is a superset for ERC-20.
    """

    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "../abis/erc4626.abi.json"
        )
    )

    def asset(self, web3: Web3 | None = None) -> ChecksumAddress:
        address = self.call("asset", web3=web3)
        return Web3.to_checksum_address(address)

    def approve_if_allowance_not_enough(
        self, api_keys: APIKeys, amount_wei: Wei, web3: Web3 | None = None
    ) -> None:
        asset_token = self.get_asset_token_contract(web3=web3)
        # We check if this contract is able to spend the user's ERC20 tokens that serve as `asset` on the ERC4626.
        allowance = asset_token.allowance(
            owner=api_keys.bet_from_address, spender=self.address, web3=web3
        )
        if allowance < amount_wei:
            asset_token.approve(api_keys, self.address, amount_wei, web3=web3)

    def deposit(
        self,
        api_keys: APIKeys,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
        **kwargs: Unpack[ExtraDepositParams],
    ) -> TxReceipt:
        # We check if this contract is able to spend the user's ERC20 tokens that serve as `asset` on the ERC4626.
        self.approve_if_allowance_not_enough(
            api_keys=api_keys, amount_wei=amount_wei, web3=web3
        )

        receiver = kwargs.get("receiver", None)
        check_not_none(receiver)

        return self.send(
            api_keys=api_keys,
            function_name="deposit",
            function_params=[amount_wei, receiver],
            tx_params=tx_params,
            web3=web3,
        )

    def withdraw(
        self,
        api_keys: APIKeys,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
        **kwargs: Unpack[ExtraWithdrawParams],
    ) -> TxReceipt:
        owner: ChecksumAddress = check_not_none(kwargs.get("owner", None))
        receiver: ChecksumAddress = check_not_none(kwargs.get("receiver", None))
        return self.send(
            api_keys=api_keys,
            function_name="withdraw",
            function_params=[amount_wei, receiver, owner],
            tx_params=tx_params,
            web3=web3,
        )

    def convertToShares(self, assets: Wei, web3: Web3 | None = None) -> Wei:
        shares: Wei = self.call("convertToShares", [assets], web3=web3)
        return shares

    def convertToAssets(self, shares: Wei, web3: Web3 | None = None) -> Wei:
        assets: Wei = self.call("convertToAssets", [shares], web3=web3)
        return assets

    def get_asset_token_contract(
        self, web3: Web3 | None = None
    ) -> ContractERC20BaseClass:
        # Underlying asset is always an ERC20-like contract.
        return ContractERC20BaseClass(address=self.asset())

    def get_asset_token_balance(
        self, for_address: ChecksumAddress, web3: Web3 | None = None
    ) -> Wei:
        asset_token_contract = self.get_asset_token_contract(web3=web3)
        return asset_token_contract.balanceOf(for_address, web3=web3)


class ContractOnGnosisChain(ContractBaseClass):
    """
    Contract base class with Gnosis Chain configuration.
    """

    CHAIN_ID = GNOSIS_NETWORK_ID
    CHAIN_RPC_URL = GNOSIS_RPC_URL


class ContractProxyOnGnosisChain(ContractProxyBaseClass, ContractOnGnosisChain):
    """
    Proxy contract base class with Gnosis Chain configuration.
    """


class ContractERC20OnGnosisChain(ContractERC20BaseClass, ContractOnGnosisChain):
    """
    ERC-20 standard base class with Gnosis Chain configuration.
    """


class ContractDepositableWrapperERC20OnGnosisChain(
    ContractDepositableWrapperERC20BaseClass, ContractOnGnosisChain
):
    """
    Depositable Wrapper ERC-20 standard base class with Gnosis Chain configuration.
    """


class ContractERC4626OnGnosisChain(ContractERC4626BaseClass, ContractOnGnosisChain):
    """
    ERC-4626 standard base class with Gnosis Chain configuration.
    """


def contract_implements_function(
    contract_address: ChecksumAddress,
    function_name: str,
    web3: Web3,
    function_arg_types: list[str] | None = None,
    look_for_proxy_contract: bool = True,
) -> bool:
    """Keccak is used here because we don't know beforehand which ABI corresponds to a (possibly unverified) smart
    contract."""
    function_signature = f"{function_name}({','.join(function_arg_types or [])})"
    function_hash = web3.keccak(text=function_signature)[0:4].hex()[2:]
    contract_code = web3.eth.get_code(contract_address).hex()
    implements = function_hash in contract_code

    if (
        not implements
        and look_for_proxy_contract
        and contract_implements_function(
            contract_address, "implementation", web3, look_for_proxy_contract=False
        )
    ):
        implementation_address = ContractProxyOnGnosisChain(
            address=contract_address
        ).implementation()
        implements = contract_implements_function(
            implementation_address,
            function_name=function_name,
            web3=web3,
            function_arg_types=function_arg_types,
            look_for_proxy_contract=False,
        )
    return implements


AbstractCollateralType = t.TypeVar("AbstractCollateralType", bound=AbstractCollateral)


def init_collateral_contract(
    address: ChecksumAddress,
    web3: Web3,
) -> AbstractCollateral:
    """
    Checks if the given contract is ERC-4626 or WrapperERC-20 or ERC-20 and returns the appropriate class instance.
    Throws an error if the contract is neither of them.
    The checks below could be made more elegant if we have verified contracts, but using keccak via web3.eth.get_code() allows us
    to also check unverified contracts.
    #
    """
    if contract_implements_function(address, "asset", web3=web3):
        return ContractERC4626BaseClass(address=address)

    elif contract_implements_function(
        address,
        "deposit",
        web3=web3,
    ):
        return ContractDepositableWrapperERC20BaseClass(address=address)

    else:
        raise ValueError(
            f"Contract at {address} on Gnosis Chain is neither WrapperERC-20 nor ERC-20."
        )


def auto_deposit_collateral_token(
    collateral_token_contract: AbstractCollateral,
    amount_wei: Wei,
    api_keys: APIKeys,
    web3: Web3 | None,
) -> None:
    for_address = api_keys.bet_from_address

    collateral_token_balance = collateral_token_contract.balanceOf(
        for_address=for_address, web3=web3
    )

    # If not enough collateral tokens, call deposit() to increase the balance.
    if collateral_token_balance < amount_wei:
        missing_balance = Wei(amount_wei - collateral_token_balance)
        collateral_token_contract.deposit(
            api_keys=api_keys,
            amount_wei=missing_balance,
            receiver=for_address,
            web3=web3,
        )


def asset_or_shares(
    collateral_token_contract: AbstractCollateral,
    amount_wei: Wei,
) -> Wei:
    return (
        collateral_token_contract.convertToShares(amount_wei)
        if isinstance(collateral_token_contract, ContractERC4626BaseClass)
        else amount_wei
    )


def to_gnosis_chain_contract(
    contract: (
        ContractDepositableWrapperERC20BaseClass
        | ContractERC4626BaseClass
        | ContractERC20BaseClass
    ),
) -> (
    ContractDepositableWrapperERC20OnGnosisChain
    | ContractERC4626OnGnosisChain
    | ContractERC20OnGnosisChain
):
    if isinstance(contract, ContractERC4626BaseClass):
        return ContractERC4626OnGnosisChain(address=contract.address)
    elif isinstance(contract, ContractDepositableWrapperERC20BaseClass):
        return ContractDepositableWrapperERC20OnGnosisChain(address=contract.address)
    elif isinstance(contract, ContractERC20BaseClass):
        return ContractERC20OnGnosisChain(address=contract.address)
    else:
        raise ValueError("Unsupported contract type")
