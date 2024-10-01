import os

from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.contract import DebuggingContract

RUN_PAID_TESTS = os.environ.get("RUN_PAID_TESTS", "0") == "1"


def mint_new_block(keys: APIKeys, web3: Web3) -> None:
    """
    Mints a new block on the web3's blockchain.
    Useful for tests that debends on chain's timestamp, this will update it.
    """
    DebuggingContract().inc(keys, web3)
