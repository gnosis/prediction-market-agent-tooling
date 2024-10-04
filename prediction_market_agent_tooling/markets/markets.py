import typing as t
from datetime import timedelta
from enum import Enum

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.manifold.api import (
    get_authenticated_user,
    get_manifold_bets,
    get_manifold_market,
)
from prediction_market_agent_tooling.markets.manifold.manifold import (
    ManifoldAgentMarket,
)
from prediction_market_agent_tooling.markets.metaculus.metaculus import (
    MetaculusAgentMarket,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.utils import (
    DatetimeUTC,
    should_not_happen,
    utcnow,
)


class MarketType(str, Enum):
    # Note: Always keep the omen market first, as it is the main market for us.
    OMEN = "omen"
    MANIFOLD = "manifold"
    POLYMARKET = "polymarket"
    METACULUS = "metaculus"

    @property
    def market_class(self) -> type[AgentMarket]:
        if self not in MARKET_TYPE_TO_AGENT_MARKET:
            raise ValueError(f"Unknown market type: {self}")
        return MARKET_TYPE_TO_AGENT_MARKET[self]


MARKET_TYPE_TO_AGENT_MARKET: dict[MarketType, type[AgentMarket]] = {
    MarketType.MANIFOLD: ManifoldAgentMarket,
    MarketType.OMEN: OmenAgentMarket,
    MarketType.POLYMARKET: PolymarketAgentMarket,
    MarketType.METACULUS: MetaculusAgentMarket,
}


def get_binary_markets(
    limit: int,
    market_type: MarketType,
    filter_by: FilterBy = FilterBy.OPEN,
    sort_by: SortBy = SortBy.NONE,
    excluded_questions: set[str] | None = None,
    created_after: DatetimeUTC | None = None,
) -> t.Sequence[AgentMarket]:
    agent_market_class = MARKET_TYPE_TO_AGENT_MARKET[market_type]
    markets = agent_market_class.get_binary_markets(
        limit=limit,
        sort_by=sort_by,
        filter_by=filter_by,
        created_after=created_after,
        excluded_questions=excluded_questions,
    )
    return markets


def have_bet_on_market_since(
    keys: APIKeys, market: AgentMarket, since: timedelta
) -> bool:
    start_time = utcnow() - since
    recently_betted_questions = (
        set(
            get_manifold_market(b.contractId).question
            for b in get_manifold_bets(
                user_id=get_authenticated_user(
                    keys.manifold_api_key.get_secret_value()
                ).id,
                start_time=start_time,
                end_time=None,
            )
        )
        if isinstance(market, ManifoldAgentMarket)
        else (
            set(
                b.title
                for b in OmenSubgraphHandler().get_bets(
                    better_address=keys.bet_from_address,
                    start_time=start_time,
                )
            )
            if isinstance(market, OmenAgentMarket)
            else should_not_happen(f"Uknown market: {market}")
        )
    )
    return market.question in recently_betted_questions
