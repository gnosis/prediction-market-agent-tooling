import os

from eth_typing import ChecksumAddress
from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChainID, Wei
from prediction_market_agent_tooling.tools.contract import ContractBaseClass

GNOSIS_NETWORK_ID = ChainID(100)  # xDai network.
GNOSIS_RPC_URL = os.getenv("GNOSIS_RPC_URL", "https://gnosis-rpc.publicnode.com")


def get_balance(address: ChecksumAddress, web3: Web3 | None = None) -> Wei:
    web3 = web3 or ContractBaseClass.get_web3()
    return Wei(web3.eth.get_balance(address))
