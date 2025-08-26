from enum import Enum
from typing import TypeVar

from prediction_market_agent_tooling.jobs.jobs_models import JobAgentMarket
from prediction_market_agent_tooling.jobs.omen.omen_jobs import OmenJobAgentMarket
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.manifold.manifold import (
    ManifoldAgentMarket,
)
from prediction_market_agent_tooling.markets.metaculus.metaculus import (
    MetaculusAgentMarket,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket

T = TypeVar("T", bound=AgentMarket)


class MarketType(str, Enum):
    # Note: Always keep the omen market first, as it is the main market for us.
    OMEN = "omen"
    MANIFOLD = "manifold"
    POLYMARKET = "polymarket"
    METACULUS = "metaculus"
    SEER = "seer"

    @staticmethod
    def from_market(market: AgentMarket) -> "MarketType":
        return AGENT_MARKET_TO_MARKET_TYPE[type(market)]

    @property
    def market_class(self) -> type[AgentMarket]:
        if self not in MARKET_TYPE_TO_AGENT_MARKET:
            raise ValueError(f"Unknown market type: {self}")
        return MARKET_TYPE_TO_AGENT_MARKET[self]

    @property
    def job_class(self) -> type[JobAgentMarket]:
        if self not in JOB_MARKET_TYPE_TO_JOB_AGENT_MARKET:
            raise ValueError(f"Unknown market type: {self}")
        return JOB_MARKET_TYPE_TO_JOB_AGENT_MARKET[self]

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


MARKET_TYPE_TO_AGENT_MARKET: dict[MarketType, type[AgentMarket]] = {
    MarketType.MANIFOLD: ManifoldAgentMarket,
    MarketType.OMEN: OmenAgentMarket,
    MarketType.POLYMARKET: PolymarketAgentMarket,
    MarketType.METACULUS: MetaculusAgentMarket,
    MarketType.SEER: SeerAgentMarket,
}

AGENT_MARKET_TO_MARKET_TYPE: dict[type[AgentMarket], MarketType] = {
    v: k for k, v in MARKET_TYPE_TO_AGENT_MARKET.items()
}

JOB_MARKET_TYPE_TO_JOB_AGENT_MARKET: dict[MarketType, type[JobAgentMarket]] = {
    MarketType.OMEN: OmenJobAgentMarket,
}
