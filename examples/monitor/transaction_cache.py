import diskcache as dc
import tenacity
from eth_typing import HexStr
from tenacity import wait_exponential
from web3 import Web3

from prediction_market_agent_tooling.loggers import logger


class TransactionBlockCache:

    def __init__(self, web3: Web3):
        self.cache = dc.Cache("block_cache_dir")
        self.web3 = web3

    @tenacity.retry(
        wait=wait_exponential(multiplier=1, min=1, max=4),
        stop=tenacity.stop_after_attempt(7),
        after=lambda x: logger.debug(f"fetch tx failed, {x.attempt_number=}."),
    )
    def fetch_block_number(self, transaction_hash: str) -> int:
        tx = self.web3.eth.get_transaction(HexStr(transaction_hash))
        return tx['blockNumber']

    def get_block_number(self, tx_hash: str) -> int:
        if tx_hash in self.cache:
            return self.cache[tx_hash]

        block_number = self.fetch_block_number(tx_hash)
        self.cache[tx_hash] = block_number
        return block_number
