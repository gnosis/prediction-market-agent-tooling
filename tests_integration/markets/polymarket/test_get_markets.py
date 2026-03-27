from datetime import timedelta

from prediction_market_agent_tooling.markets.agent_market import (
    ConditionalFilterType,
    FilterBy,
    QuestionType,
    SortBy,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    SHARED_CACHE,
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.utils import utcnow


def test_get_markets() -> None:
    SHARED_CACHE.clear()
    limit = 10
    created_after = utcnow() - timedelta(days=14)
    markets = PolymarketAgentMarket.get_markets(
        limit=limit,
        created_after=created_after,
        filter_by=FilterBy.RESOLVED,
        sort_by=SortBy.NEWEST,
    )

    assert len(markets) == limit
    assert all([m.is_resolved() for m in markets])

    for m in markets:
        assert m.question, "Market should have a non-empty question"
        assert len(m.outcomes) >= 2, "Market should have at least 2 outcomes"
        assert m.resolution is not None, "Resolved market should have a resolution"


def test_open_markets() -> None:
    SHARED_CACHE.clear()
    limit = 50
    created_after = utcnow() - timedelta(days=14)
    markets = PolymarketAgentMarket.get_markets(
        limit=limit, filter_by=FilterBy.OPEN, created_after=created_after
    )
    assert len(markets) == limit
    assert not all([m.is_closed() for m in markets])

    for m in markets:
        assert m.condition_id is not None, "Market should have a condition_id"
        prob_sum = sum(float(p) for p in m.probabilities.values())
        assert (
            0.99 <= prob_sum <= 1.01
        ), f"Probabilities should sum to ~1.0, got {prob_sum}"


def test_many_markets() -> None:
    limit = 1000
    # bad market, see slug
    # 'who-will-win-the-pacers-v-hornets-game-on-october-20th'
    polymarket_markets = PolymarketAgentMarket.get_markets(
        limit=limit,
        filter_by=FilterBy.RESOLVED,
        sort_by=SortBy.NONE,
        question_type=QuestionType.BINARY,
        conditional_filter_type=ConditionalFilterType.ONLY_NOT_CONDITIONAL,
    )

    assert len(polymarket_markets) == limit
