from datetime import timedelta

from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.utils import utcnow


def test_get_markets() -> None:
    limit = 10
    # We assume there are 10 markets on Polymarkets created in the last 14 days
    created_after = utcnow() - timedelta(days=14)
    markets = PolymarketAgentMarket.get_markets(
        limit=limit, created_after=created_after
    )

    assert len(markets) == limit
