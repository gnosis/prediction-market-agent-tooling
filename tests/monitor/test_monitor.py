import pytest

from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.monitor.monitor import monitor_agent
from prediction_market_agent_tooling.monitor.monitor_app import DEPLOYED_AGENT_TYPE_MAP


@pytest.mark.parametrize("market_type", list(MarketType))
def test_monitor_market(market_type: MarketType) -> None:
    cls = DEPLOYED_AGENT_TYPE_MAP[market_type]
    agents = cls.from_all_gcp_functions()
    if len(agents) == 0:
        pytest.skip(f"No deployed agents found for {market_type}")

    monitor_agent(agents[0])
