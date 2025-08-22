from enum import Enum
from typing import Type, TypeVar

from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.manifold.manifold import (
    ManifoldAgentMarket,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket

T = TypeVar("T", bound=AgentMarket)


class MarketType(str, Enum):
    OMEN = "omen"
    MANIFOLD = "manifold"
    POLYMARKET = "polymarket"
    SEER = "seer"

    @classmethod
    def from_market(cls, market: AgentMarket) -> "MarketType":
        """Get the market type from a market instance."""
        if isinstance(market, OmenAgentMarket):
            return MarketType.OMEN
        elif isinstance(market, ManifoldAgentMarket):
            return MarketType.MANIFOLD
        elif isinstance(market, PolymarketAgentMarket):
            return MarketType.POLYMARKET
        elif isinstance(market, SeerAgentMarket):
            return MarketType.SEER
        else:
            raise ValueError(f"Unknown market type: {type(market).__name__}")

    def market_class(self) -> Type[AgentMarket]:
        """Get the market class for this market type."""
        if self == MarketType.OMEN:
            return OmenAgentMarket
        elif self == MarketType.MANIFOLD:
            return ManifoldAgentMarket
        elif self == MarketType.POLYMARKET:
            return PolymarketAgentMarket
        elif self == MarketType.SEER:
            return SeerAgentMarket
        else:
            raise ValueError(f"Unknown market type: {self}")

    def job_class(self):
        """Get the job class for this market type."""
        if self == MarketType.OMEN:
            from prediction_market_agent_tooling.jobs.omen.omen_jobs import (
                OmenJobAgentMarket,
            )

            return OmenJobAgentMarket
        else:
            raise ValueError(f"No job class for market type: {self}")

    @property
    def is_trading_market(self) -> bool:
        return self in [
            MarketType.OMEN,
            MarketType.POLYMARKET,
            MarketType.SEER,
            MarketType.MANIFOLD,
        ]

    @property
    def is_blockchain_market(self) -> bool:
        return self in [MarketType.OMEN, MarketType.POLYMARKET, MarketType.SEER]
