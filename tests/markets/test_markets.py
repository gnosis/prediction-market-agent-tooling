import pytest

from prediction_market_agent_tooling.deploy.agent import (
    DeployablePredictionAgent,
    DeployableTraderAgent,
)
from prediction_market_agent_tooling.gtypes import OutcomeStr, OutcomeToken, Probability
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    MarketFees,
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
    probability_map = {
        OutcomeStr("yes"): Probability(0.5),
        OutcomeStr("no"): Probability(0.5),
    }
    market = AgentMarket(
        id="foo",
        question="bar",
        description=None,
        outcomes=list(probability_map.keys()),
        outcome_token_pool={
            OutcomeStr("yes"): OutcomeToken(1.1),
            OutcomeStr("no"): OutcomeToken(2.0),
        },
        resolution=None,
        created_time=None,
        close_time=None,
        probabilities=probability_map,
        url="https://example.com",
        volume=None,
        fees=MarketFees.get_zero_fees(),
    )
    assert market.has_token_pool() is True
    assert market.get_pool_tokens(OutcomeStr("yes")) == OutcomeToken(1.1)
    assert market.get_pool_tokens(OutcomeStr("no")) == OutcomeToken(2.0)


def test_invalid_token_pool() -> None:
    prob_map = {
        OutcomeStr("yes"): Probability(0.5),
        OutcomeStr("no"): Probability(0.5),
    }
    with pytest.raises(ValueError) as e:
        AgentMarket(
            id="foo",
            question="bar",
            description=None,
            outcomes=list(prob_map.keys()),
            outcome_token_pool={
                OutcomeStr("baz"): OutcomeToken(1.1),
                OutcomeStr("qux"): OutcomeToken(2.0),
            },
            resolution=None,
            created_time=None,
            close_time=None,
            url="https://example.com",
            volume=None,
            fees=MarketFees.get_zero_fees(),
            probabilities=prob_map,
        )
    assert "do not match outcomes" in str(e.value)


@pytest.mark.parametrize(
    "market_type",
    [
        pytest.param(
            MarketType.POLYMARKET,
            marks=pytest.mark.skip(reason="Failing for Polymarket, see issue PMAT-574"),
        ),
        MarketType.MANIFOLD,
        MarketType.OMEN,
        MarketType.METACULUS,
    ],
)
def test_get_pool_tokens(market_type: MarketType) -> None:
    market_types_without_pool_tokens = [
        MarketType.METACULUS,
        MarketType.POLYMARKET,
    ]
    market = market_type.market_class.get_markets(
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
            assert market.get_pool_tokens(outcome).value > 0


@pytest.mark.parametrize(
    "market_type",
    [
        pytest.param(
            MarketType.POLYMARKET,
            marks=pytest.mark.skip(reason="Failing for Polymarket, see issue PMAT-574"),
        ),
        MarketType.MANIFOLD,
        MarketType.OMEN,
        MarketType.METACULUS,
    ],
)
def test_get_markets(market_type: MarketType) -> None:
    limit = 100
    markets = market_type.market_class.get_markets(
        limit=limit, sort_by=SortBy.NONE, filter_by=FilterBy.OPEN
    )
    assert len(markets) <= limit


@pytest.mark.parametrize("market_type", list(MarketType))
def test_market_is_covered(market_type: MarketType) -> None:
    assert (
        market_type in DeployablePredictionAgent.supported_markets
        or market_type in DeployableTraderAgent.supported_markets
    ), f"Market {market_type} isn't supported in any of our deployable agents."
