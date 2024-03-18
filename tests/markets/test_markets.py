import pytest

from prediction_market_agent_tooling.markets.markets import (
    MARKET_TYPE_TO_AGENT_MARKET,
    MarketType,
)


@pytest.mark.parametrize("market_type", list(MarketType))
def test_market_mapping_contains_all_types(market_type: MarketType) -> None:
    assert (
        market_type in MARKET_TYPE_TO_AGENT_MARKET
    ), f"Add {market_type} to the MARKET_TYPE_TO_AGENT_MARKET."
