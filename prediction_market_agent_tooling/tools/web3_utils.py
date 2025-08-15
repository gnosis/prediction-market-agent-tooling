import binascii
import secrets
from typing import Any, Optional

import base58
import tenacity
from eth_account import Account
from eth_typing import URI
from eth_utils.currency import MAX_WEI, MIN_WEI
from pydantic.types import SecretStr
from safe_eth.eth import EthereumClient
from safe_eth.eth.ethereum_client import TxSpeed
from safe_eth.safe.safe import SafeV141
from web3 import Web3
from web3.constants import HASH_ZERO
from web3.types import AccessList, AccessListEntry, Nonce, TxParams, TxReceipt

from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChecksumAddress,
    HexAddress,
    HexBytes,
    HexStr,
    IPFSCIDVersion0,
    PrivateKey,
    Web3Wei,
    private_key_type,
    xDai,
    xDaiWei,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools._generic_value import _GenericValue

ONE_NONCE = Nonce(1)
ONE_XDAI = xDai(1)
ZERO_BYTES = HexBytes(HASH_ZERO)
NOT_REVERTED_ICASE_REGEX_PATTERN = "(?i)(?!.*reverted.*)"


def generate_private_key() -> PrivateKey:
    return private_key_type("0x" + secrets.token_hex(32))


def private_key_to_public_key(private_key: SecretStr) -> ChecksumAddress:
    account = Account.from_key(private_key.get_secret_value())
    return verify_address(account.address)


def verify_address(address: str) -> ChecksumAddress:
    if not Web3.is_checksum_address(address):
        raise ValueError(
            f"The address {address} is not a valid checksum address, please fix your input."
        )
    return ChecksumAddress(HexAddress(HexStr(address)))


def check_tx_receipt(receipt: TxReceipt) -> None:
    if receipt["status"] != 1:
        raise ValueError(
            f"Transaction failed with status code {receipt['status']}. Receipt: {receipt}"
        )


def unwrap_generic_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, _GenericValue):
        return value.value
    elif isinstance(value, list):
        return [unwrap_generic_value(v) for v in value]
    elif isinstance(value, tuple):
        return tuple(unwrap_generic_value(v) for v in value)
    elif isinstance(value, dict):
        return {k: unwrap_generic_value(v) for k, v in value.items()}
    return value


def parse_function_params(
    params: Optional[list[Any] | tuple[Any] | dict[str, Any]]
) -> list[Any] | tuple[Any]:
    params = unwrap_generic_value(params)
    if params is None:
        return []
    if isinstance(params, list):
        return [unwrap_generic_value(i) for i in params]
    if isinstance(params, tuple):
        return tuple(unwrap_generic_value(i) for i in params)
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
    output = contract.functions[function_name](
        *parse_function_params(function_params)
    ).call()
    return output


def prepare_tx(
    web3: Web3,
    contract_address: ChecksumAddress,
    contract_abi: ABI,
    from_address: ChecksumAddress | None,
    function_name: str,
    function_params: Optional[list[Any] | dict[str, Any]] = None,
    access_list: Optional[AccessList] = None,
    tx_params: Optional[TxParams] = None,
) -> TxParams:
    tx_params_new = _prepare_tx_params(web3, from_address, access_list, tx_params)
    contract = web3.eth.contract(address=contract_address, abi=contract_abi)
    # Build the transaction.
    function_call = contract.functions[function_name](
        *parse_function_params(function_params)
    )
    built_tx_params: TxParams = function_call.build_transaction(tx_params_new)
    return built_tx_params


def _prepare_tx_params(
    web3: Web3,
    from_address: ChecksumAddress | None,
    access_list: Optional[AccessList] = None,
    tx_params: Optional[TxParams] = None,
) -> TxParams:
    # Fill in required defaults, if not provided.
    tx_params_new = TxParams()
    if tx_params:
        tx_params_new.update(tx_params)

    if not tx_params_new.get("from") and not from_address:
        raise ValueError(
            "Cannot have both tx_params[`from`] and from_address not defined."
        )

    if not tx_params_new.get("from") and from_address:
        tx_params_new["from"] = from_address

    if not tx_params_new.get("nonce"):
        from_checksummed = Web3.to_checksum_address(tx_params_new["from"])
        tx_params_new["nonce"] = web3.eth.get_transaction_count(from_checksummed)

    if not tx_params_new.get("chainId"):
        tx_params_new["chainId"] = web3.eth.chain_id

    if access_list is not None:
        tx_params_new["accessList"] = access_list

    return tx_params_new


@tenacity.retry(
    # Don't retry on `reverted` messages, as they would always fail again.
    # TODO: Check this, see https://github.com/gnosis/prediction-market-agent-tooling/issues/625.
    # retry=tenacity.retry_if_exception_message(match=NOT_REVERTED_ICASE_REGEX_PATTERN),
    wait=tenacity.wait_chain(*[tenacity.wait_fixed(n) for n in range(1, 6)]),
    stop=tenacity.stop_after_attempt(5),
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

    receipt_tx = sign_send_and_get_receipt_tx(
        web3, tx_params, from_private_key, timeout
    )
    return receipt_tx


@tenacity.retry(
    # Don't retry on `reverted` messages, as they would always fail again.
    # TODO: Check this, see https://github.com/gnosis/prediction-market-agent-tooling/issues/625.
    # retry=tenacity.retry_if_exception_message(match=NOT_REVERTED_ICASE_REGEX_PATTERN),
    wait=tenacity.wait_chain(*[tenacity.wait_fixed(n) for n in range(1, 6)]),
    stop=tenacity.stop_after_attempt(5),
    after=lambda x: logger.debug(
        f"send_function_on_contract_tx_using_safe failed, {x.attempt_number=}."
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
    if not web3.provider.endpoint_uri:  # type: ignore
        raise EnvironmentError("RPC_URL not available in web3 object.")
    ethereum_client = EthereumClient(ethereum_node_url=URI(web3.provider.endpoint_uri))  # type: ignore
    s = SafeV141(safe_address, ethereum_client)
    safe_master_copy_address = s.retrieve_master_copy_address()
    eoa_public_key = private_key_to_public_key(from_private_key)
    # See https://ethereum.stackexchange.com/questions/123750/how-to-implement-eip-2930-access-list for details,
    # required to not go out-of-gas when calling a contract functions using Safe.
    access_list = AccessList(
        [
            AccessListEntry(
                {
                    "address": eoa_public_key,
                    "storageKeys": [HASH_ZERO],
                }
            ),
            AccessListEntry(
                {
                    "address": safe_address,
                    "storageKeys": [HASH_ZERO],
                }
            ),
            AccessListEntry(
                {
                    "address": safe_master_copy_address,
                    "storageKeys": [],
                }
            ),
        ]
    )
    tx_params = prepare_tx(
        web3=web3,
        contract_address=contract_address,
        contract_abi=contract_abi,
        from_address=safe_address,
        function_name=function_name,
        function_params=function_params,
        access_list=access_list,
        tx_params=tx_params,
    )
    safe_tx = s.build_multisig_tx(
        to=Web3.to_checksum_address(tx_params["to"]),
        data=HexBytes(tx_params["data"]),
        value=tx_params["value"],
    )
    safe_tx.sign(from_private_key.get_secret_value())
    safe_tx.call()  # simulate call
    eoa_nonce = web3.eth.get_transaction_count(eoa_public_key)
    tx_hash, tx = safe_tx.execute(
        from_private_key.get_secret_value(),
        tx_nonce=eoa_nonce,
        eip1559_speed=TxSpeed.FAST,
    )
    receipt_tx = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
    check_tx_receipt(receipt_tx)
    return receipt_tx


def sign_send_and_get_receipt_tx(
    web3: Web3,
    tx_params_new: TxParams,
    from_private_key: PrivateKey,
    timeout: int = 180,
) -> TxReceipt:
    # Sign with the private key.
    signed_tx = web3.eth.account.sign_transaction(
        tx_params_new, private_key=from_private_key.get_secret_value()
    )
    # Send the signed transaction.
    send_tx = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
    # And wait for the receipt.
    receipt_tx = web3.eth.wait_for_transaction_receipt(send_tx, timeout=timeout)
    # Verify it didn't fail.
    check_tx_receipt(receipt_tx)
    return receipt_tx


def send_xdai_to(
    web3: Web3,
    from_private_key: PrivateKey,
    to_address: ChecksumAddress,
    value: xDaiWei,
    data_text: Optional[str | bytes] = None,
    tx_params: Optional[TxParams] = None,
    timeout: int = 180,
) -> TxReceipt:
    from_address = private_key_to_public_key(from_private_key)

    tx_params_new: TxParams = {"value": value.value, "to": to_address}
    if data_text is not None:
        tx_params_new["data"] = (
            Web3.to_bytes(text=data_text)
            if not isinstance(data_text, bytes)
            else data_text
        )
    if tx_params:
        tx_params_new.update(tx_params)
    tx_params_new = _prepare_tx_params(web3, from_address, tx_params=tx_params_new)

    # We need gas and gasPrice here (and not elsewhere) because we are not calling
    # contract.functions.myFunction().build_transaction, which autofills some params
    # with defaults, incl. gas and gasPrice.
    gas = web3.eth.estimate_gas(tx_params_new)
    tx_params_new["gas"] = int(
        gas * 1.5
    )  # We conservatively overestimate gas here, knowing it will be returned if unused
    tx_params_new["gasPrice"] = web3.eth.gas_price

    receipt_tx = sign_send_and_get_receipt_tx(
        web3, tx_params_new, from_private_key, timeout
    )
    return receipt_tx


def ipfscidv0_to_byte32(cid: IPFSCIDVersion0) -> HexBytes:
    """
    Convert ipfscidv0 to 32 bytes.
    Modified from https://github.com/emg110/ipfs2bytes32/blob/main/python/ipfs2bytes32.py
    """
    decoded = base58.b58decode(cid)
    sliced_decoded = decoded[2:]
    return HexBytes(binascii.b2a_hex(sliced_decoded).decode("utf-8"))


def byte32_to_ipfscidv0(hex: HexBytes) -> IPFSCIDVersion0:
    """
    Convert 32 bytes hex to ipfscidv0.
    Modified from https://github.com/emg110/ipfs2bytes32/blob/main/python/ipfs2bytes32.py
    """
    completed_binary_str = b"\x12 " + hex
    return IPFSCIDVersion0(base58.b58encode(completed_binary_str).decode("utf-8"))


@tenacity.retry(
    wait=tenacity.wait_chain(*[tenacity.wait_fixed(n) for n in range(1, 6)]),
    stop=tenacity.stop_after_attempt(5),
    after=lambda x: logger.debug(
        f"get_receipt_block_timestamp failed, {x.attempt_number=}."
    ),
)
def get_receipt_block_timestamp(receipt_tx: TxReceipt, web3: Web3) -> int:
    block_number = receipt_tx["blockNumber"]
    block = web3.eth.get_block(block_number)
    block_timestamp: int = block["timestamp"]
    return block_timestamp


def is_valid_wei(value: Web3Wei) -> bool:
    return MIN_WEI <= value <= MAX_WEI
