from prediction_market_agent_tooling.markets.polymarket.api import (
    PolymarketOrderByEnum,
    get_polymarkets_with_pagination,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def test_get_binary_market() -> None:
    """Fetch a known active market by condition_id via get_binary_market."""
    markets_data = get_polymarkets_with_pagination(
        limit=1,
        active=True,
        closed=False,
        order_by=PolymarketOrderByEnum.VOLUME_24HR,
    )
    assert markets_data, "No active markets found"
    event = markets_data[0]
    inner_markets = check_not_none(event.markets)
    condition_id = inner_markets[0].conditionId

    market = PolymarketAgentMarket.get_binary_market(id=condition_id.to_0x_hex())

    assert isinstance(market, PolymarketAgentMarket)
    assert market.condition_id == condition_id
    assert len(market.outcomes) == 2
