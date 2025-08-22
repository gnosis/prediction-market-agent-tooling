from typing import Sequence

from web3 import Web3
from web3.constants import HASH_ZERO

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexBytes,
    HexStr,
    OutcomeStr,
    OutcomeWei,
)
from prediction_market_agent_tooling.tools.contract import ConditionalTokenContract
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


def get_conditional_tokens_balance_base(
    condition_id: HexBytes,
    collateral_token_address: ChecksumAddress,
    conditional_token_contract: ConditionalTokenContract,
    from_address: ChecksumAddress,
    index_sets: list[int],
    parent_collection_id=HASH_ZERO,
    web3: Web3 | None = None,
) -> dict[tuple[HexBytes, int], OutcomeWei]:
    """
    Get the balance of conditional tokens for a given condition ID and account.

    Args:
        condition_id: The ID of the condition.
        collateral_token_address: The address of the collateral token.
        conditional_token_contract: The conditional token contract instance.
        from_address: The address to check the balance for.
        index_sets: List of index sets to check.
        parent_collection_id: The ID of the parent collection.
        web3: Optional Web3 instance.

    Returns:
        A dictionary mapping (collection_id, index_set) to the balance in wei.
    """
    balances = {}
    for index_set in index_sets:
        collection_id = conditional_token_contract.get_collection_id(
            parent_collection_id, condition_id, index_set, web3=web3
        )
        position_id = conditional_token_contract.get_position_id(
            collateral_token_address, collection_id, web3=web3
        )
        balance = conditional_token_contract.balance_of(
            from_address, position_id, web3=web3
        )
        balances[(collection_id, index_set)] = OutcomeWei(balance)
    return balances


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
