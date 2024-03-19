from datetime import datetime
from enum import Enum

from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.manifold.manifold import (
    ManifoldAgentMarket,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)


class MarketType(str, Enum):
    MANIFOLD = "manifold"
    OMEN = "omen"
    POLYMARKET = "polymarket"


MARKET_TYPE_TO_AGENT_MARKET: dict[MarketType, type[AgentMarket]] = {
    MarketType.MANIFOLD: ManifoldAgentMarket,
    MarketType.OMEN: OmenAgentMarket,
    MarketType.POLYMARKET: PolymarketAgentMarket,
}


def get_binary_markets(
    limit: int,
    market_type: MarketType,
    filter_by: FilterBy = FilterBy.OPEN,
    sort_by: SortBy = SortBy.NONE,
    excluded_questions: set[str] | None = None,
    created_after: datetime | None = None,
) -> list[AgentMarket]:
    agent_market_class = MARKET_TYPE_TO_AGENT_MARKET[market_type]
    markets = agent_market_class.get_binary_markets(
        limit=limit,
        sort_by=sort_by,
        filter_by=filter_by,
        created_after=created_after,
        excluded_questions=excluded_questions,
    )
    return markets
