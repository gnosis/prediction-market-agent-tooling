from prediction_market_agent_tooling.gtypes import xDai
from prediction_market_agent_tooling.jobs.jobs_models import OmenJob
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    FilterBy,
    OmenSubgraphHandler,
    SortBy,
)

JOBS_CATEGORY = "jobs"


def get_jobs(max_bond: xDai, limit: int | None = None) -> list[OmenJob]:
    markets = OmenSubgraphHandler().get_omen_binary_markets_simple(
        limit=limit,
        filter_by=FilterBy.OPEN,
        sort_by=SortBy.CLOSING_SOONEST,
        category=JOBS_CATEGORY,
    )
    return [OmenJob.from_omen_market(market, max_bond) for market in markets]
