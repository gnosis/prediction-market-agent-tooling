from enum import Enum

from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.manifold.manifold import (
    ManifoldAgentMarket,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket


class MarketType(str, Enum):
    MANIFOLD = "manifold"
    OMEN = "omen"


MARKET_TYPE_MAP: dict[MarketType, type[AgentMarket]] = {
    MarketType.MANIFOLD: ManifoldAgentMarket,
    MarketType.OMEN: OmenAgentMarket,
}


def get_binary_markets(market_type: MarketType, limit: int = 20) -> list[AgentMarket]:
    cls = MARKET_TYPE_MAP.get(market_type)
    if cls:
        return cls.get_binary_markets(limit=limit)
    else:
        raise ValueError(f"Unknown market type: {market_type}")
