import diskcache as dc
import tenacity
from eth_typing import HexStr
from tenacity import wait_exponential
from web3 import Web3

from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.cache import persistent_inmemory_cache


class TransactionBlockCache:

    def __init__(self, web3: Web3):
        self.cache = dc.Cache("block_cache_dir")
        self.web3 = web3

    @persistent_inmemory_cache
    @tenacity.retry(
        wait=wait_exponential(multiplier=1, min=1, max=4),
        stop=tenacity.stop_after_attempt(7),
        after=lambda x: logger.debug(f"fetch tx failed, {x.attempt_number=}."),
    )
    def get_block_number(self, transaction_hash: str) -> int:
        tx = self.web3.eth.get_transaction(HexStr(transaction_hash))
        return tx['blockNumber']
