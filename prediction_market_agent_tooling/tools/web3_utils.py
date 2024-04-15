from decimal import Decimal
from typing import Any, Optional, TypeVar

import tenacity
from eth_account import Account
from eth_typing import URI, Address
from gnosis.eth import EthereumClient
from gnosis.safe.safe import SafeV141
from loguru import logger
from pydantic.types import SecretStr
from web3 import Web3
from web3.constants import HASH_ZERO
from web3.types import Nonce, TxParams, TxReceipt, Wei

from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChecksumAddress,
    HexAddress,
    HexBytes,
    HexStr,
    PrivateKey,
    xDai,
    xdai_type,
)

ONE_NONCE = Nonce(1)
ONE_XDAI = xdai_type(1)
ZERO_BYTES = HexBytes(HASH_ZERO)


def private_key_to_public_key(private_key: SecretStr) -> ChecksumAddress:
    account = Account.from_key(private_key.get_secret_value())
    return verify_address(account.address)


def wei_to_xdai(wei: Wei) -> xDai:
    return xDai(Decimal((Web3.from_wei(wei, "ether"))))


def xdai_to_wei(native: xDai) -> Wei:
    return Web3.to_wei(native, "ether")


RemoveOrAddFractionAmountType = TypeVar("RemoveOrAddFractionAmountType", bound=int)


def verify_address(address: str) -> ChecksumAddress:
    if not Web3.is_checksum_address(address):
        raise ValueError(
            f"The address {address} is not a valid checksum address, please fix your input."
        )
    return ChecksumAddress(HexAddress(HexStr(address)))


def remove_fraction(
    amount: RemoveOrAddFractionAmountType, fraction: float
) -> RemoveOrAddFractionAmountType:
    """Removes the given fraction from the given integer-bounded amount and returns the value as an original type."""
    if 0 <= fraction <= 1:
        keep_percentage = 1 - fraction
        return type(amount)(int(amount * keep_percentage))
    raise ValueError(f"The given fraction {fraction!r} is not in the range [0, 1].")


def add_fraction(
    amount: RemoveOrAddFractionAmountType, fraction: float
) -> RemoveOrAddFractionAmountType:
    """Adds the given fraction to the given integer-bounded amount and returns the value as an original type."""
    if 0 <= fraction <= 1:
        keep_percentage = 1 + fraction
        return type(amount)(int(amount * keep_percentage))
    raise ValueError(f"The given fraction {fraction!r} is not in the range [0, 1].")


def check_tx_receipt(receipt: TxReceipt) -> None:
    if receipt["status"] != 1:
        raise ValueError(
            f"Transaction failed with status code {receipt['status']}. Receipt: {receipt}"
        )


def parse_function_params(params: Optional[list[Any] | dict[str, Any]]) -> list[Any]:
    if params is None:
        return []
    if isinstance(params, list):
        return params
    if isinstance(params, dict):
        return list(params.values())
    raise ValueError(f"Invalid type for function parameters: {type(params)}")


@tenacity.retry(
    wait=tenacity.wait_chain(*[tenacity.wait_fixed(n) for n in range(1, 6)]),
    stop=tenacity.stop_after_attempt(5),
    after=lambda x: logger.debug(
        f"call_function_on_contract failed, {x.attempt_number=}."
    ),
)
def call_function_on_contract(
    web3: Web3,
    contract_address: ChecksumAddress,
    contract_abi: ABI,
    function_name: str,
    function_params: Optional[list[Any] | dict[str, Any]] = None,
) -> Any:
    contract = web3.eth.contract(address=contract_address, abi=contract_abi)
    output = contract.functions[function_name](*parse_function_params(function_params)).call()  # type: ignore # TODO: Fix Mypy, as this works just OK.
    return output


def prepare_tx(
    web3: Web3,
    contract_address: ChecksumAddress,
    contract_abi: ABI,
    from_address: ChecksumAddress | None,
    function_name: str,
    function_params: Optional[list[Any] | dict[str, Any]] = None,
    tx_params: Optional[TxParams] = None,
) -> TxParams:
    contract = web3.eth.contract(address=contract_address, abi=contract_abi)

    # Fill in required defaults, if not provided.
    tx_params_new = TxParams()
    if tx_params:
        tx_params_new.update(tx_params)

    if not tx_params_new["from"] and not from_address:
        raise ValueError(
            "Cannot have both tx_params[`from`] and from_address not defined."
        )

    if not tx_params_new["from"]:
        tx_params_new["from"] = Address.fromhex(from_address)

    if not tx_params_new["nonce"]:
        tx_params_new["nonce"] = web3.eth.get_transaction_count(tx_params_new["from"])

    # Build the transaction.
    function_call = contract.functions[function_name](*parse_function_params(function_params))  # type: ignore
    tx_params_new = function_call.build_transaction(tx_params_new)
    gas = web3.eth.estimate_gas(tx_params_new)
    tx_params_new["gas"] = gas
    return tx_params_new


@tenacity.retry(
    # Retry only for the transaction errors that match the given patterns,
    # add other retrieable errors gradually to be safe.
    retry=tenacity.retry_if_exception_message(
        match="(.*wrong transaction nonce.*)|(.*Invalid.*)|(.*OldNonce.*)"
    ),
    wait=tenacity.wait_chain(*[tenacity.wait_fixed(n) for n in range(1, 10)]),
    stop=tenacity.stop_after_attempt(9),
    after=lambda x: logger.debug(
        f"send_function_on_contract_tx failed, {x.attempt_number=}."
    ),
)
def send_function_on_contract_tx(
    web3: Web3,
    contract_address: ChecksumAddress,
    contract_abi: ABI,
    from_private_key: PrivateKey,
    function_name: str,
    function_params: Optional[list[Any] | dict[str, Any]] = None,
    tx_params: Optional[TxParams] = None,
    timeout: int = 180,
) -> TxReceipt:
    public_key = private_key_to_public_key(from_private_key)

    tx_params = prepare_tx(
        web3=web3,
        contract_address=contract_address,
        contract_abi=contract_abi,
        from_address=public_key,
        function_name=function_name,
        function_params=function_params,
        tx_params=tx_params,
    )
    # Sign with the private key.
    signed_tx = web3.eth.account.sign_transaction(
        tx_params, private_key=from_private_key.get_secret_value()
    )
    # Send the signed transaction.
    send_tx = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
    # And wait for the receipt.
    receipt_tx = web3.eth.wait_for_transaction_receipt(send_tx, timeout=timeout)
    # Verify it didn't fail.
    check_tx_receipt(receipt_tx)
    return receipt_tx


@tenacity.retry(
    # Retry only for the transaction errors that match the given patterns,
    # add other retrieable errors gradually to be safe.
    retry=tenacity.retry_if_exception_message(
        match="(.*wrong transaction nonce.*)|(.*Invalid.*)|(.*OldNonce.*)"
    ),
    wait=tenacity.wait_chain(*[tenacity.wait_fixed(n) for n in range(1, 10)]),
    stop=tenacity.stop_after_attempt(9),
    after=lambda x: logger.debug(
        f"send_function_on_contract_tx failed, {x.attempt_number=}."
    ),
)
def send_function_on_contract_tx_using_safe(
    web3: Web3,
    contract_address: ChecksumAddress,
    contract_abi: ABI,
    from_private_key: PrivateKey,
    safe_address: ChecksumAddress,
    function_name: str,
    function_params: Optional[list[Any] | dict[str, Any]] = None,
    tx_params: Optional[TxParams] = None,
    timeout: int = 180,
) -> TxReceipt:
    if not safe_address:
        raise ValueError("Safe address not set.")

    tx_params = prepare_tx(
        web3=web3,
        contract_address=contract_address,
        contract_abi=contract_abi,
        from_address=safe_address,
        function_name=function_name,
        function_params=function_params,
        tx_params=tx_params,
    )

    if not web3.HTTPProvider.endpoint_uri:
        raise EnvironmentError(f"RPC_URL not available in web3 object.")
    ethereum_client = EthereumClient(
        ethereum_node_url=URI(web3.HTTPProvider.endpoint_uri)
    )
    s = SafeV141(safe_address, ethereum_client)
    safe_tx = s.build_multisig_tx(
        to=Web3.to_checksum_address(tx_params["to"]),
        data=HexBytes(tx_params["data"]),
        value=tx_params["value"],
    )
    safe_tx.sign(from_private_key.get_secret_value())
    safe_tx.call()  # simulate call
    tx_hash, tx = safe_tx.execute(from_private_key.get_secret_value())
    receipt_tx = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
    check_tx_receipt(receipt_tx)
    return receipt_tx
