from web3 import Web3
from web3.constants import HASH_ZERO

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import HexBytes, HexStr
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import ProcessedTradedMarket
from prediction_market_agent_tooling.markets.omen.data_models import (
    ContractPrediction,
    IPFSAgentResult,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenAgentResultMappingContract,
)
from prediction_market_agent_tooling.tools.ipfs.ipfs_handler import IPFSHandler
from prediction_market_agent_tooling.tools.utils import BPS_CONSTANT
from prediction_market_agent_tooling.tools.web3_utils import ipfscidv0_to_byte32

# max uint16 for easy prediction identification (if market does not have YES outcome)
UINT16_MAX = 2**16 - 1  # = 65535


def store_trades(
    market_id: str,
    traded_market: ProcessedTradedMarket | None,
    keys: APIKeys,
    agent_name: str,
    web3: Web3 | None = None,
) -> None:
    if traded_market is None:
        logger.warning(f"No prediction for market {market_id}, not storing anything.")
        return None

    yes_probability = traded_market.answer.get_yes_probability()
    if not yes_probability:
        logger.info("Skipping this since no yes_probability available.")
        return None
    reasoning = traded_market.answer.reasoning if traded_market.answer.reasoning else ""

    ipfs_hash_decoded = HexBytes(HASH_ZERO)
    if keys.enable_ipfs_upload:
        logger.info("Storing prediction on IPFS.")
        ipfs_hash = IPFSHandler(keys).store_agent_result(
            IPFSAgentResult(reasoning=reasoning, agent_name=agent_name)
        )
        ipfs_hash_decoded = ipfscidv0_to_byte32(ipfs_hash)

    # tx_hashes must be list of bytes32 (see Solidity contract).
    tx_hashes = [
        HexBytes(HexStr(i.id)) for i in traded_market.trades if i.id is not None
    ]

    estimated_probability_bps = int(yes_probability * BPS_CONSTANT)

    prediction = ContractPrediction(
        publisher=keys.bet_from_address,
        ipfs_hash=ipfs_hash_decoded,
        tx_hashes=tx_hashes,
        estimated_probability_bps=estimated_probability_bps,
    )
    tx_receipt = OmenAgentResultMappingContract().add_prediction(
        api_keys=keys,
        market_address=Web3.to_checksum_address(market_id),
        prediction=prediction,
        web3=web3,
    )
    logger.info(
        f"Added prediction to market {market_id}. - receipt {tx_receipt['transactionHash'].hex()}."
    )
