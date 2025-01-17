import time

from eth_typing import ChecksumAddress
from web3 import Web3

from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.monitor.nft_game.models import ERC721Transfer
from prediction_market_agent_tooling.tools.contract import (
    ContractOwnableERC721BaseClass,
)


def fetch_nft_transfers(
    web3: Web3,
    nft_contract_address: ChecksumAddress,
    from_block: int = 37341108,
    to_block: int | None = None,
) -> list[ERC721Transfer]:
    s = ContractOwnableERC721BaseClass(address=nft_contract_address)
    nft_c = s.get_web3_contract(web3=web3)

    # fetch transfer events in the last block
    start = time.time()
    logs = nft_c.events.Transfer().get_logs(fromBlock=from_block, toBlock=to_block)
    logger.debug(f"elapsed {time.time() - start}")
    logger.debug(f"fetched {len(logs)} NFT transfers")

    events = [ERC721Transfer.from_event_log(log) for log in logs]
    return events


def extract_messages_exchanged():
    # ToDo
    pass


def extract_balances_per_block():
    # ToDo
    pass
