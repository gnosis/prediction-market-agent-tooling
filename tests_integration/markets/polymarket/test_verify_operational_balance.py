from unittest.mock import Mock

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)

# Vitalik's address — known to exist on Polygon with some balance
KNOWN_POLYGON_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

# Fresh address with no POL
EMPTY_POLYGON_ADDRESS = "0x0000000000000000000000000000000000000001"


def test_verify_operational_balance_known_address() -> None:
    mock_keys = Mock(spec=APIKeys)
    mock_keys.public_key = KNOWN_POLYGON_ADDRESS

    result = PolymarketAgentMarket.verify_operational_balance(api_keys=mock_keys)
    assert isinstance(result, bool)


def test_verify_operational_balance_empty_address() -> None:
    mock_keys = Mock(spec=APIKeys)
    mock_keys.public_key = EMPTY_POLYGON_ADDRESS

    result = PolymarketAgentMarket.verify_operational_balance(api_keys=mock_keys)
    assert result is False
