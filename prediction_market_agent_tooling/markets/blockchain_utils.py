from typing import Sequence

from web3 import Web3
from web3.constants import HASH_ZERO

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexBytes,
    HexStr,
    OutcomeStr,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import ProcessedMarket
from prediction_market_agent_tooling.markets.omen.data_models import (
    ContractPrediction,
    IPFSAgentResult,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    _AgentResultMappingContract,
)
from prediction_market_agent_tooling.tools.ipfs.ipfs_handler import IPFSHandler
from prediction_market_agent_tooling.tools.utils import BPS_CONSTANT
from prediction_market_agent_tooling.tools.web3_utils import ipfscidv0_to_byte32


def store_trades(
    contract: _AgentResultMappingContract,
    market_id: ChecksumAddress,
    outcomes: Sequence[OutcomeStr],
    traded_market: ProcessedMarket | None,
    keys: APIKeys,
    agent_name: str,
    web3: Web3 | None = None,
) -> None:
    if traded_market is None:
        logger.warning(f"No prediction for market {market_id}, not storing anything.")
        return None

    logger.info(
        f"Storing trades for market {market_id}, with outcomes {outcomes}, {traded_market=}."
    )

    probabilities = traded_market.answer.probabilities
    if not probabilities:
        logger.info("Skipping this since no probabilities available.")
        return None

    if all(outcome not in probabilities for outcome in outcomes):
        raise ValueError("No of the market's outcomes is in the probabilities.")

    reasoning = traded_market.answer.reasoning if traded_market.answer.reasoning else ""

    ipfs_hash_decoded = HexBytes(HASH_ZERO)
    if keys.enable_ipfs_upload:
        logger.info("Storing prediction on IPFS.")
        ipfs_hash = IPFSHandler(keys).store_agent_result(
            IPFSAgentResult(reasoning=reasoning, agent_name=agent_name)
        )
        ipfs_hash_decoded = ipfscidv0_to_byte32(ipfs_hash)

    # tx_hashes must be list of bytes32 (see Solidity contract).
    tx_hashes = [HexBytes(HexStr(i.id)) for i in traded_market.trades]

    # Dune dashboard expects the probs to be in the same order as on the market.
    probabilities_converted = [
        (outcome, int(probabilities.get(outcome, 0) * BPS_CONSTANT))
        for outcome in outcomes
    ]

    prediction = ContractPrediction(
        market=market_id,
        publisher=keys.bet_from_address,
        ipfs_hash=ipfs_hash_decoded,
        tx_hashes=tx_hashes,
        outcomes=[x[0] for x in probabilities_converted],
        estimated_probabilities_bps=[x[1] for x in probabilities_converted],
    )
    tx_receipt = contract.add_prediction(
        api_keys=keys,
        market_address=market_id,
        prediction=prediction,
        web3=web3,
    )
    logger.info(
        f"Added prediction to market {market_id}. - receipt {tx_receipt['transactionHash'].to_0x_hex()}."
    )
