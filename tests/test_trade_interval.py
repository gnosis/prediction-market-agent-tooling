from datetime import timedelta
from unittest.mock import Mock

import pytest

from prediction_market_agent_tooling.deploy.trade_interval import (
    FixedInterval,
    MarketLifetimeProportionalInterval,
)
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.tools.utils import utcnow


@pytest.fixture
def mock_market() -> Mock:
    mock_market = Mock(AgentMarket, wraps=AgentMarket)
    mock_market.created_time = utcnow()
    mock_market.close_time = mock_market.created_time + timedelta(days=10)
    return mock_market


def test_fixed_interval(mock_market: Mock) -> None:
    interval = timedelta(days=1)
    fixed_interval = FixedInterval(interval=interval)

    assert fixed_interval.get(mock_market) == interval


def test_market_lifetime_proportional_interval(mock_market: Mock) -> None:
    proportional_interval = MarketLifetimeProportionalInterval(max_trades=5)

    assert proportional_interval.get(mock_market) == timedelta(days=2)
