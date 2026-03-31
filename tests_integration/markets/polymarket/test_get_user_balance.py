from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)

# Known USDC whale on Polygon — should have a non-zero balance
USDC_WHALE_ADDRESS = "0x5a58505a96D1dbf8dF91cB21B54419FC36e93fdE"

# Random address with no USDC on Polygon
EMPTY_ADDRESS = "0xE3a5F17BC84F63545E0e893810A7a4b89BaDC134"


def test_get_user_balance_whale() -> None:
    balance = PolymarketAgentMarket.get_user_balance(USDC_WHALE_ADDRESS)
    assert isinstance(balance, float)
    assert balance >= 0


def test_get_user_balance_empty() -> None:
    balance = PolymarketAgentMarket.get_user_balance(EMPTY_ADDRESS)
    assert balance == 0.0
