from datetime import timedelta

from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.utils import utcnow


def test_get_markets() -> None:
    limit = 10
    created_after = utcnow() - timedelta(days=14)
    markets = PolymarketAgentMarket.get_markets(
        limit=limit,
        created_after=created_after,
        filter_by=FilterBy.RESOLVED,
        sort_by=SortBy.NEWEST,
    )

    assert len(markets) == limit
    assert all([m.is_resolved() for m in markets])


def test_open_markets() -> None:
    limit = 20
    created_after = utcnow() - timedelta(days=14)
    markets = PolymarketAgentMarket.get_markets(
        limit=limit, filter_by=FilterBy.OPEN, created_after=created_after
    )
    assert len(markets) == limit
    assert not all([m.is_closed() for m in markets])
