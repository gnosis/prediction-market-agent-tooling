from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.markets.omen.omen_constants import (
    METRI_SUPER_GROUP_CONTRACT_ADDRESS,
)

DEFAULT_SLIPPAGE_TOLERANCE = 0.01

SLIPPAGE_TOLERANCE_PER_TOKEN = {
    METRI_SUPER_GROUP_CONTRACT_ADDRESS: 0.1,
}


def get_slippage_tolerance_per_token(
    token: ChecksumAddress, default_slippage: float = DEFAULT_SLIPPAGE_TOLERANCE
) -> float:
    return SLIPPAGE_TOLERANCE_PER_TOKEN.get(token, default_slippage)
