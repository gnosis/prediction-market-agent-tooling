import typing as t
from enum import Enum

from prediction_market_agent_tooling.jobs.jobs_models import JobAgentMarket
from prediction_market_agent_tooling.jobs.omen.omen_jobs import OmenJobAgentMarket
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
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
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


class MarketType(str, Enum):
    # Note: Always keep the omen market first, as it is the main market for us.
    OMEN = "omen"
    MANIFOLD = "manifold"
    POLYMARKET = "polymarket"
    METACULUS = "metaculus"
    SEER = "seer"

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
    def is_blockchain_market(self) -> bool:
        return self in [MarketType.OMEN, MarketType.POLYMARKET, MarketType.SEER]


MARKET_TYPE_TO_AGENT_MARKET: dict[MarketType, type[AgentMarket]] = {
    MarketType.MANIFOLD: ManifoldAgentMarket,
    MarketType.OMEN: OmenAgentMarket,
    MarketType.POLYMARKET: PolymarketAgentMarket,
    MarketType.METACULUS: MetaculusAgentMarket,
    MarketType.SEER: SeerAgentMarket,
}


JOB_MARKET_TYPE_TO_JOB_AGENT_MARKET: dict[MarketType, type[JobAgentMarket]] = {
    MarketType.OMEN: OmenJobAgentMarket,
}


def get_binary_markets(
    limit: int,
    market_type: MarketType,
    filter_by: FilterBy = FilterBy.OPEN,
    sort_by: SortBy = SortBy.NONE,
    excluded_questions: set[str] | None = None,
    created_after: DatetimeUTC | None = None,
    fetch_scalar_markets: bool = False,
) -> t.Sequence[AgentMarket]:
    agent_market_class = MARKET_TYPE_TO_AGENT_MARKET[market_type]
    markets = agent_market_class.get_markets(
        limit=limit,
        sort_by=sort_by,
        filter_by=filter_by,
        created_after=created_after,
        excluded_questions=excluded_questions,
        fetch_scalar_markets=fetch_scalar_markets,
    )
    return markets
