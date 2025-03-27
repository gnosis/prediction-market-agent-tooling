from web3 import Web3
from web3.constants import HASH_ZERO

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexBytes,
    HexStr,
    xDai,
    xdai_type,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import ProcessedTradedMarket
from prediction_market_agent_tooling.markets.omen.data_models import (
    ContractPrediction,
    IPFSAgentResult,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenAgentResultMappingContract,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.ipfs.ipfs_handler import IPFSHandler
from prediction_market_agent_tooling.tools.utils import BPS_CONSTANT
from prediction_market_agent_tooling.tools.web3_utils import ipfscidv0_to_byte32


def get_total_balance(
    address: ChecksumAddress,
    web3: Web3 | None = None,
    sum_xdai: bool = True,
    sum_wxdai: bool = True,
) -> xDai:
    """
    Checks if the total balance of xDai and wxDai in the wallet is above the minimum required balance.
    """
    current_balances = get_balances(address, web3)
    # xDai and wxDai have equal value and can be exchanged for almost no cost, so we can sum them up.
    total_balance = 0.0
    if sum_xdai:
        total_balance += current_balances.xdai
    if sum_wxdai:
        total_balance += current_balances.wxdai
    return xdai_type(total_balance)


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

    reasoning = traded_market.answer.reasoning if traded_market.answer.reasoning else ""

    ipfs_hash_decoded = HexBytes(HASH_ZERO)
    if keys.enable_ipfs_upload:
        logger.info("Storing prediction on IPFS.")
        ipfs_hash = IPFSHandler(keys).store_agent_result(
            IPFSAgentResult(reasoning=reasoning, agent_name=agent_name)
        )
        ipfs_hash_decoded = ipfscidv0_to_byte32(ipfs_hash)

    # tx_hashes must be list of bytes32 (see Solidity contract).
    # For regular tx hashes that's fine, but for other types of IDs we take the first 32 bytes (orderDigest).
    tx_hashes = [
        HexBytes(HexStr(i.id[:32])) for i in traded_market.trades if i.id is not None
    ]
    prediction = ContractPrediction(
        publisher=keys.bet_from_address,
        ipfs_hash=ipfs_hash_decoded,
        tx_hashes=tx_hashes,
        estimated_probability_bps=int(traded_market.answer.p_yes * BPS_CONSTANT),
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
