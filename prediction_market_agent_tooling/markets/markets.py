from enum import Enum

from prediction_market_agent_tooling.markets.agent_market import AgentMarket
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
