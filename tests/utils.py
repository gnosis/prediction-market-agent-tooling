from web3 import Web3
from web3.types import RPCEndpoint

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.contract import DebuggingContract

RUN_PAID_TESTS = APIKeys().RUN_PAID_TESTS


def mint_new_block(keys: APIKeys, web3: Web3) -> None:
    """
    Mints a new block on the web3's blockchain.
    Useful for tests that debends on chain's timestamp, this will update it.
    """
    DebuggingContract().inc(keys, web3)


def advance_chain_time(web3: Web3, seconds: int, keys: APIKeys) -> None:
    """Advance the local chain's timestamp by the given number of seconds and mine a block."""
    web3.provider.make_request(RPCEndpoint("evm_increaseTime"), [seconds])
    mint_new_block(keys, web3)
