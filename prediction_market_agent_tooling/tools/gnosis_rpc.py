import os
import requests
from web3.types import Wei

GNOSIS_RPC_URL = os.getenv("GNOSIS_RPC_URL", "https://gnosis-rpc.publicnode.com")


def get_balance(address: str) -> Wei:
    response = requests.post(
        GNOSIS_RPC_URL,
        json={
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [address, "latest"],
            "id": 1,
        },
        headers={"content-type": "application/json"},
    ).json()
    balance = Wei(int(response["result"], 16))  # Convert hex value to int.
    return balance
