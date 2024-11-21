import diskcache as dc
import tenacity
from eth_typing import HexStr
from tenacity import wait_exponential
from web3 import Web3

from prediction_market_agent_tooling.loggers import logger


class TransactionBlockCache:
    def __init__(self, web3: Web3):
        self.block_number_cache = dc.Cache("block_cache_dir")
        self.block_timestamp_cache = dc.Cache("timestamp_cache_dir")
        self.web3 = web3

    @tenacity.retry(
        wait=wait_exponential(multiplier=1, min=1, max=4),
        stop=tenacity.stop_after_attempt(7),
        after=lambda x: logger.debug(f"fetch tx failed, {x.attempt_number=}."),
    )
    def fetch_block_number(self, transaction_hash: str) -> int:
        tx = self.web3.eth.get_transaction(HexStr(transaction_hash))
        return tx["blockNumber"]

    @tenacity.retry(
        wait=wait_exponential(multiplier=1, min=1, max=4),
        stop=tenacity.stop_after_attempt(7),
        after=lambda x: logger.debug(f"fetch tx failed, {x.attempt_number=}."),
    )
    def fetch_block_timestamp(self, block_number: int) -> int:
        block = self.web3.eth.get_block(block_number)
        return block["timestamp"]

    def get_block_number(self, tx_hash: str) -> int:
        if tx_hash in self.block_number_cache:
            return int(self.block_number_cache[tx_hash])

        block_number = self.fetch_block_number(tx_hash)
        self.block_number_cache[tx_hash] = block_number
        return block_number

    def get_block_timestamp(self, block_number: int) -> int:
        if block_number in self.block_timestamp_cache:
            return int(self.block_timestamp_cache[block_number])

        block_timestamp = self.fetch_block_timestamp(block_number)
        self.block_timestamp_cache[block_number] = block_timestamp
        return block_timestamp
