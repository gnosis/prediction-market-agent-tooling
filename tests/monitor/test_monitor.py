import pytest

from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.monitor.monitor import monitor_agent
from prediction_market_agent_tooling.monitor.monitor_app import (
    MARKET_TYPE_TO_DEPLOYED_AGENT,
)


@pytest.mark.parametrize("market_type", list(MarketType))
def test_monitor_mapping_contains_all_types(market_type: MarketType) -> None:
    assert (
        market_type in MARKET_TYPE_TO_DEPLOYED_AGENT
    ), f"Add {market_type} to the MARKET_TYPE_TO_DEPLOYED_AGENT."


@pytest.mark.parametrize("market_type", list(MarketType))
def test_monitor_market(market_type: MarketType) -> None:
    cls = MARKET_TYPE_TO_DEPLOYED_AGENT[market_type]
    agents = cls.from_all_gcp_functions()
    if len(agents) == 0:
        pytest.skip(f"No deployed agents found for {market_type}")

    monitor_agent(agents[0])
