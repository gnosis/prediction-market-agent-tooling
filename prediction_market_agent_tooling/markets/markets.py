import typing as t
from web3 import Web3
from web3.constants import HASH_ZERO
from prediction_market_agent_tooling.jobs.jobs_models import JobAgentMarket
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    QuestionType,
    SortBy,
)
from prediction_market_agent_tooling.gtypes import ChecksumAddress, HexBytes, OutcomeWei
from prediction_market_agent_tooling.markets.manifold.manifold import ManifoldAgentMarket
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.polymarket.polymarket import PolymarketAgentMarket
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.market_type import MarketType
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.contract import ConditionalTokenContract
from prediction_market_agent_tooling.tools.utils import DatetimeUTC
from prediction_market_agent_tooling.markets.blockchain_utils import get_conditional_tokens_balance_base


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


