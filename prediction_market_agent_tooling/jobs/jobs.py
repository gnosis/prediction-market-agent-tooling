import typing as t

from prediction_market_agent_tooling.jobs.jobs_models import JobAgentMarket
from prediction_market_agent_tooling.jobs.omen.omen_jobs import OmenJobAgentMarket
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.markets import MarketType

JOB_MARKET_TYPE_TO_JOB_AGENT_MARKET: dict[MarketType, type[JobAgentMarket]] = {
    MarketType.OMEN: OmenJobAgentMarket,
}


@t.overload
def get_jobs(
    market_type: t.Literal[MarketType.OMEN],
    limit: int | None,
    filter_by: FilterBy = FilterBy.OPEN,
    sort_by: SortBy = SortBy.NONE,
) -> t.Sequence[OmenJobAgentMarket]:
    ...


@t.overload
def get_jobs(
    market_type: MarketType,
    limit: int | None,
    filter_by: FilterBy = FilterBy.OPEN,
    sort_by: SortBy = SortBy.NONE,
) -> t.Sequence[JobAgentMarket]:
    ...


def get_jobs(
    market_type: MarketType,
    limit: int | None,
    filter_by: FilterBy = FilterBy.OPEN,
    sort_by: SortBy = SortBy.NONE,
) -> t.Sequence[JobAgentMarket]:
    job_class = JOB_MARKET_TYPE_TO_JOB_AGENT_MARKET[market_type]
    markets = job_class.get_jobs(
        limit=limit,
        sort_by=sort_by,
        filter_by=filter_by,
    )
    return markets
