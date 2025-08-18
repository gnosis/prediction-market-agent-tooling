from datetime import timedelta

from web3 import Web3

from prediction_market_agent_tooling.chains import GNOSIS_CHAIN_ID
from prediction_market_agent_tooling.markets.seer.seer_api import get_seer_transactions
from prediction_market_agent_tooling.tools.utils import utcnow


def test_get_seer_transactions_for_agent() -> None:
    addr = Web3.to_checksum_address("0xd32cbeb0acbee86670b5de60ab50596b667b4f69")
    start_date = utcnow() - timedelta(days=30)
    txs = get_seer_transactions(addr, GNOSIS_CHAIN_ID, start_date)
    assert len(txs) > 0
