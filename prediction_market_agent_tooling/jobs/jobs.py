from prediction_market_agent_tooling.jobs.jobs_models import OmenJobMarket
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    FilterBy,
    OmenSubgraphHandler,
    SortBy,
)

JOBS_CATEGORY = "jobs"


def get_jobs(limit: int | None = None) -> list[OmenJobMarket]:
    markets = OmenSubgraphHandler().get_omen_binary_markets_simple(
        limit=limit,
        filter_by=FilterBy.OPEN,
        sort_by=SortBy.CLOSING_SOONEST,
        category=JOBS_CATEGORY,
    )
    return [OmenJobMarket.from_omen_market(market) for market in markets]
