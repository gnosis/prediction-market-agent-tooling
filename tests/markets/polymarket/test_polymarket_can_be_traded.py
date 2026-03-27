import pytest

from prediction_market_agent_tooling.gtypes import USD
from prediction_market_agent_tooling.markets.polymarket.constants import (
    POLYMARKET_MIN_LIQUIDITY_USD,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)

ABOVE_THRESHOLD = USD(POLYMARKET_MIN_LIQUIDITY_USD.value + 0.01)


@pytest.mark.parametrize(
    "active, closed, liquidity, expected",
    [
        (True, False, USD(10), True),
        (True, True, USD(10), False),
        (False, False, USD(10), False),
        (True, False, POLYMARKET_MIN_LIQUIDITY_USD, False),
        (True, False, ABOVE_THRESHOLD, True),
        (True, False, USD(0), False),
    ],
    ids=[
        "active_open_liquid",
        "closed",
        "inactive",
        "liquidity_at_threshold",
        "liquidity_above_threshold",
        "no_liquidity",
    ],
)
def test_can_be_traded(
    mock_polymarket_market: PolymarketAgentMarket,
    active: bool,
    closed: bool,
    liquidity: USD,
    expected: bool,
) -> None:
    market = mock_polymarket_market.model_copy(
        update={
            "active_flag_from_polymarket": active,
            "closed_flag_from_polymarket": closed,
            "liquidity_usd": liquidity,
        }
    )
    assert market.can_be_traded() == expected
