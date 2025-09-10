import typing as t

from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    QuestionType,
    SortBy,
)
from prediction_market_agent_tooling.markets.market_type import (
    MARKET_TYPE_TO_AGENT_MARKET,
    MarketType,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


def get_binary_markets(
    limit: int,
    market_type: MarketType,
    filter_by: FilterBy = FilterBy.OPEN,
    sort_by: SortBy = SortBy.NONE,
    excluded_questions: set[str] | None = None,
    created_after: DatetimeUTC | None = None,
    question_type: QuestionType = QuestionType.BINARY,
) -> t.Sequence[AgentMarket]:
    agent_market_class = MARKET_TYPE_TO_AGENT_MARKET[market_type]
    markets = agent_market_class.get_markets(
        limit=limit,
        sort_by=sort_by,
        filter_by=filter_by,
        created_after=created_after,
        excluded_questions=excluded_questions,
        question_type=question_type,
    )
    return markets
