from ape_test.accounts import TestAccount
from eth_account import Account
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxParams

from prediction_market_agent_tooling.config import RPCConfig, APIKeys
from prediction_market_agent_tooling.gtypes import xDai
from prediction_market_agent_tooling.markets.polymarket.constants import (
    CTF_EXCHANGE_POLYMARKET,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
)
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import parse_function_params


def test_is_approved_for_all(eoa_accounts: list[TestAccount]) -> None:
    owner = eoa_accounts[0]
    # ToDo - Create new ape-foundry config for Polygon
    c = PolymarketConditionalTokenContract()
    web3 = Web3(Web3.HTTPProvider(check_not_none(RPCConfig().polygon_rpc_url)))
    is_approved = c.isApprovedForAll(
        owner=owner.address, for_address=CTF_EXCHANGE_POLYMARKET, web3=web3
    )
    assert not is_approved


def execute_write_transaction(w3: Web3, from_address: str, private_key: str) -> None:
    """
    Builds, signs, and sends a transaction to a smart contract write function.
    """
    try:
        print("\nBuilding the transaction...")
        # Get the latest nonce for your account
        nonce = w3.eth.get_transaction_count(from_address)

        # Build the transaction object. This calls the 'yourWriteFunctionName'
        # with the specified argument.
        tx_params = {
            "from": from_address,
            "nonce": nonce,
            "gas": 200000,  # Set a reasonable gas limit
            "gasPrice": w3.eth.gas_price,  # Let web3.py determine the gas price
        }

        contract = PolymarketConditionalTokenContract().get_web3_contract(w3)
        function_name = "setApprovalForAll"
        function_params = [CTF_EXCHANGE_POLYMARKET, True]
        function_call = contract.functions[function_name](
            *parse_function_params(function_params)
        )  # type: ignore # TODO: Fix Mypy, as this works just OK.
        transaction: TxParams = function_call.build_transaction(tx_params)

        print("Signing the transaction...")
        signed_tx = w3.eth.account.sign_transaction(transaction, private_key)

        print("Sending the transaction...")
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        print(f"Transaction sent! Hash: {tx_hash.hex()}")
        print("Waiting for transaction receipt...")

        # Wait for the transaction to be mined
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        print("\n--- Transaction Receipt ---")
        print(f"Status: {'Success' if tx_receipt['status'] == 1 else 'Failed'}")
        print(f"Block Number: {tx_receipt['blockNumber']}")
        print(f"Gas Used: {tx_receipt['gasUsed']}")
        print(f"PolygonScan URL: https://polygonscan.com/tx/{tx_hash.hex()}")

    except ValueError as ve:
        # This can catch issues with transaction parameters (e.g., gas too low, nonce issues)
        print(f"ValueError during transaction: {ve}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def test_set_approval_for_all(test_keys: APIKeys) -> None:
    # owner = eoa_accounts[0]
    # from foundry
    owner = Account.from_key(
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    )
    # ToDo - Create new ape-foundry config for Polygon
    c = PolymarketConditionalTokenContract()
    w3 = Web3(Web3.HTTPProvider("http://localhost:8546"))

    w3.provider.make_request(
        "anvil_setBalance", [test_keys.public_key, hex(xDai(1).as_xdai_wei.value)]
    )

    # Inject the PoA middleware. This is the crucial step to resolve the ExtraDataLengthError.
    # It should be injected in the first position (index 0).
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    # Create a contract instance

    # execute_write_transaction(
    #     from_address=owner.address, w3=w3, private_key=owner.key.hex()
    # )

    c.setApprovalForAll(
        api_keys=test_keys,
        for_address=CTF_EXCHANGE_POLYMARKET,
        approve=True,
        web3=w3,
    )
    is_approved = c.isApprovedForAll(
        owner=owner.address, for_address=CTF_EXCHANGE_POLYMARKET, web3=w3
    )
    assert is_approved
