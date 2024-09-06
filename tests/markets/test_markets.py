import pytest

from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.markets import (
    MARKET_TYPE_TO_AGENT_MARKET,
    MarketType,
)


@pytest.mark.parametrize("market_type", list(MarketType))
def test_market_mapping_contains_all_types(market_type: MarketType) -> None:
    assert (
        market_type in MARKET_TYPE_TO_AGENT_MARKET
    ), f"Add {market_type} to the MARKET_TYPE_TO_AGENT_MARKET."


def test_valid_token_pool() -> None:
    market = AgentMarket(
        id="foo",
        question="bar",
        description=None,
        outcomes=["yes", "no"],
        outcome_token_pool={"yes": 1.1, "no": 2.0},
        resolution=None,
        created_time=None,
        close_time=None,
        current_p_yes=0.5,
        url="https://example.com",
        volume=None,
    )
    assert market.has_token_pool() is True
    assert market.get_pool_tokens("yes") == 1.1
    assert market.get_pool_tokens("no") == 2.0


def test_invalid_token_pool() -> None:
    with pytest.raises(ValueError) as e:
        AgentMarket(
            id="foo",
            question="bar",
            description=None,
            outcomes=["yes", "no"],
            outcome_token_pool={"baz": 1.1, "qux": 2.0},
            resolution=None,
            created_time=None,
            close_time=None,
            current_p_yes=0.5,
            url="https://example.com",
            volume=None,
        )
    assert "do not match outcomes" in str(e.value)


@pytest.mark.parametrize("market_type", list(MarketType))
def test_get_pool_tokens(market_type: MarketType) -> None:
    market_types_without_pool_tokens = [
        MarketType.METACULUS,
        MarketType.POLYMARKET,
    ]
    market = market_type.market_class.get_binary_markets(
        limit=1,
        sort_by=SortBy.NONE,
        filter_by=FilterBy.OPEN,
    )[0]
    if market_type in market_types_without_pool_tokens:
        assert market.has_token_pool() is False
    else:
        assert market.has_token_pool() is True
        for outcome in market.outcomes:
            # Sanity check
            assert market.get_pool_tokens(outcome) > 0
