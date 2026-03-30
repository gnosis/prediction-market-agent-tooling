from unittest.mock import Mock

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import USD
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)

# Known USDC whale on Polygon — should have a non-zero balance
USDC_WHALE_ADDRESS = "0x5a58505a96D1dbf8dF91cB21B54419FC36e93fdE"

# Random address with no USDC on Polygon
EMPTY_ADDRESS = "0xE3a5F17BC84F63545E0e893810A7a4b89BaDC134"


def test_get_trade_balance_whale() -> None:
    mock_keys = Mock(spec=APIKeys)
    mock_keys.public_key = USDC_WHALE_ADDRESS

    balance = PolymarketAgentMarket.get_trade_balance(api_keys=mock_keys)
    assert isinstance(balance, USD)
    assert balance >= USD(0)


def test_get_trade_balance_empty_address() -> None:
    mock_keys = Mock(spec=APIKeys)
    mock_keys.public_key = EMPTY_ADDRESS

    balance = PolymarketAgentMarket.get_trade_balance(api_keys=mock_keys)
    assert balance == USD(0)
