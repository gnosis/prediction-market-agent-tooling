import json
import os
import time
import typing as t
from contextlib import contextmanager

from pydantic import BaseModel, field_validator
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


class ContractDepositableWrapperERC20BaseClass(ContractERC20BaseClass):
    """
    ERC-20 standard base class extended for wrapper tokens.
    Altough this is not a standard, it's seems to be a common pattern for wrapped tokens (at least it checks out for wxDai and wETH).
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
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="withdraw",
            function_params=[amount_wei],
            tx_params=tx_params,
            web3=web3,
        )


class ContractERC4626BaseClass(ContractERC20BaseClass):
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

    def deposit(
        self,
        api_keys: APIKeys,
        amount_wei: Wei,
        receiver: ChecksumAddress,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="deposit",
            function_params=[amount_wei, receiver],
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
    ) -> ContractERC20BaseClass | ContractDepositableWrapperERC20BaseClass:
        web3 = web3 or self.get_web3()
        contract = init_erc4626_or_wrappererc20_or_erc20_contract(
            self.asset(), web3=web3
        )
        assert not isinstance(
            contract, ContractERC4626OnGnosisChain
        ), "Asset token should be either Depositable Wrapper ERC-20 or ERC-20."  # Shrinking down possible types.
        return contract

    def get_asset_token_balance(
        self, for_address: ChecksumAddress, web3: Web3 | None = None
    ) -> Wei:
        asset_token_contract = self.get_asset_token_contract(web3=web3)
        return asset_token_contract.balanceOf(for_address, web3=web3)

    def deposit_asset_token(
        self, asset_value: Wei, api_keys: APIKeys, web3: Web3 | None = None
    ) -> TxReceipt:
        for_address = api_keys.bet_from_address
        web3 = web3 or self.get_web3()

        asset_token_contract = self.get_asset_token_contract(web3=web3)
        # Approve vault to withdraw the erc-20 token from the user.
        asset_token_contract.approve(api_keys, self.address, asset_value, web3=web3)

        # Deposit asset token (erc20) and we will receive shares in this vault.
        receipt = self.deposit(api_keys, asset_value, for_address, web3=web3)

        return receipt


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


def init_erc4626_or_wrappererc20_or_erc20_contract(
    address: ChecksumAddress,
    web3: Web3,
) -> (
    ContractERC20BaseClass
    | ContractERC4626BaseClass
    | ContractDepositableWrapperERC20BaseClass
):
    """
    Checks if the given contract is Depositable ERC-20, ERC-20 or ERC-4626 and returns the appropriate class instance.
    Throws an error if the contract is neither of them.
    """
    if contract_implements_function(address, "asset", web3=web3):
        return ContractERC4626BaseClass(address=address)

    elif contract_implements_function(
        address,
        "deposit",
        web3=web3,
    ):
        return ContractDepositableWrapperERC20BaseClass(address=address)

    elif contract_implements_function(
        address,
        "balanceOf",
        web3=web3,
        function_arg_types=["address"],
    ):
        return ContractERC20BaseClass(address=address)

    else:
        raise ValueError(
            f"Contract at {address} on Gnosis Chain is neither WrapperERC-20, ERC-20 nor ERC-4626."
        )


def auto_deposit_collateral_token(
    collateral_token_contract: (
        ContractERC20BaseClass
        | ContractERC4626BaseClass
        | ContractDepositableWrapperERC20BaseClass
    ),
    amount_wei: Wei,
    api_keys: APIKeys,
    web3: Web3 | None,
) -> None:
    for_address = api_keys.bet_from_address
    # This might be in shares, if it's an erc-4626 token.
    collateral_token_balance = collateral_token_contract.balanceOf(
        for_address=for_address, web3=web3
    )

    if isinstance(collateral_token_contract, ContractERC4626BaseClass):
        # In the more complex case, we need to deposit into the saving token, out of the erc-20 token.
        # We need to compare with shares, because if erc-4626 is used, the liquidity in market will be in shares as well.
        if collateral_token_balance < collateral_token_contract.convertToShares(
            amount_wei
        ):
            asset_token_contract = collateral_token_contract.get_asset_token_contract(
                web3=web3
            )

            # If the asset token is Depositable Wrapper ERC-20, we can deposit it, in case we don't have enough.
            if (
                collateral_token_contract.get_asset_token_balance(for_address, web3)
                < amount_wei
            ):
                if isinstance(
                    asset_token_contract, ContractDepositableWrapperERC20BaseClass
                ):
                    asset_token_contract.deposit(api_keys, amount_wei, web3=web3)
                else:
                    raise ValueError(
                        f"Not enough of the asset token, but it's not a depositable wrapper token that we can deposit automatically."
                    )

            collateral_token_contract.deposit_asset_token(amount_wei, api_keys, web3)

    elif isinstance(
        collateral_token_contract, ContractDepositableWrapperERC20BaseClass
    ):
        # If the collateral token is Depositable Wrapper ERC-20, it's a simple case where we can just deposit it, if needed.
        if collateral_token_balance < amount_wei:
            collateral_token_contract.deposit(api_keys, amount_wei, web3=web3)

    elif isinstance(collateral_token_contract, ContractERC20BaseClass):
        if collateral_token_balance < amount_wei:
            raise ValueError(
                f"Not enough of the collateral token, but it's not a wrapper token that we can deposit automatically."
            )

    else:
        raise RuntimeError("Bug in our logic! :(")


def asset_or_shares(
    collateral_token_contract: (
        ContractERC20BaseClass
        | ContractERC4626BaseClass
        | ContractDepositableWrapperERC20BaseClass
    ),
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
