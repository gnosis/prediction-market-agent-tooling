from decimal import Decimal
from typing import Any, Optional, TypeVar

import tenacity
from web3 import Web3
from web3.types import Nonce, TxParams, TxReceipt, Wei

from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChecksumAddress,
    HexAddress,
    HexStr,
    PrivateKey,
    xDai,
    xdai_type,
)

ONE_NONCE = Nonce(1)
ONE_XDAI = xdai_type(1)


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
    wait=tenacity.wait_chain(*[tenacity.wait_fixed(n) for n in range(1, 6)])
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


@tenacity.retry(
    # Retry only for the transaction nonce errors (as it can get correct one next time),
    # add other retrieable errors gradually to be safe.
    retry=tenacity.retry_if_exception_message(match=".*wrong transaction nonce.*"),
    wait=tenacity.wait_chain(*[tenacity.wait_fixed(n) for n in range(1, 6)]),
)
def send_function_on_contract_tx(
    web3: Web3,
    *,
    contract_address: ChecksumAddress,
    contract_abi: ABI,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    function_name: str,
    function_params: Optional[list[Any] | dict[str, Any]] = None,
    tx_params: Optional[TxParams] = None,
    timeout: int = 180,
) -> TxReceipt:
    contract = web3.eth.contract(address=contract_address, abi=contract_abi)

    # Fill in required defaults, if not provided.
    tx_params = tx_params or {}
    tx_params["nonce"] = tx_params.get(
        "nonce", web3.eth.get_transaction_count(from_address)
    )
    tx_params["from"] = tx_params.get("from", from_address)

    # Build the transaction.
    function_call = contract.functions[function_name](*parse_function_params(function_params))  # type: ignore # TODO: Fix Mypy, as this works just OK.
    tx = function_call.build_transaction(tx_params)
    # Sign with the private key.
    signed_tx = web3.eth.account.sign_transaction(
        tx, private_key=from_private_key.get_secret_value()
    )
    # Send the signed transaction.
    send_tx = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
    # And wait for the receipt.
    receipt_tx = web3.eth.wait_for_transaction_receipt(send_tx, timeout=timeout)
    # Verify it didn't fail.
    check_tx_receipt(receipt_tx)
    return receipt_tx
