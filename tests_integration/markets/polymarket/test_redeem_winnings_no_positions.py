from unittest.mock import Mock

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)

# Random address with no Polymarket positions
EMPTY_ADDRESS = "0xE3a5F17BC84F63545E0e893810A7a4b89BaDC134"


def test_redeem_winnings_no_positions() -> None:
    """Verify redeem_winnings completes gracefully when user has no redeemable positions."""
    mock_keys = Mock(spec=APIKeys)
    mock_keys.bet_from_address = EMPTY_ADDRESS

    # Should complete without error — empty position list means the loop body never runs
    PolymarketAgentMarket.redeem_winnings(api_keys=mock_keys)
