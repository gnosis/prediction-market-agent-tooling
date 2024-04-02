import os

import requests

from prediction_market_agent_tooling.gtypes import ChainID, HexAddress, Wei

GNOSIS_NETWORK_ID = ChainID(100)  # xDai network.
GNOSIS_RPC_URL = os.getenv("GNOSIS_RPC_URL", "https://gnosis-rpc.publicnode.com")


def get_balance(address: HexAddress) -> Wei:
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
