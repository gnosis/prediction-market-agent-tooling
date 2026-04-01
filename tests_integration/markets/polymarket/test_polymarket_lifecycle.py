from prediction_market_agent_tooling.markets.polymarket.api import (
    PolymarketOrderByEnum,
    get_polymarkets_with_pagination,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def test_get_binary_market() -> None:
    """Fetch a known active market by ID via the Gamma API."""
    markets_data = get_polymarkets_with_pagination(
        limit=1,
        active=True,
        closed=False,
        order_by=PolymarketOrderByEnum.VOLUME_24HR,
    )
    assert markets_data, "No active markets found"
    event_id = markets_data[0].id

    market = PolymarketAgentMarket.get_binary_market(id=event_id)

    assert isinstance(market, PolymarketAgentMarket)
    assert market.id == event_id
    assert len(market.outcomes) == 2
    assert market.condition_id is not None
