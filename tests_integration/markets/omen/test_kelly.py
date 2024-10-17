import numpy as np
import pytest

from prediction_market_agent_tooling.deploy.betting_strategy import KellyBettingStrategy
from prediction_market_agent_tooling.markets.agent_market import (
    FilterBy,
    MarketFees,
    SortBy,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet_full,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def test_kelly_price_impact_calculation1() -> None:
    # First case from https://docs.gnosis.io/conditionaltokens/docs/introduction3/#an-example-with-cpmm
    kelly = KellyBettingStrategy(max_bet_amount=1, max_price_impact=0.5)
    yes = 10
    no = 10
    bet_amount = 10
    buy_direction = True
    assert_price_impact(bet_amount, buy_direction, yes, no, kelly)


def test_kelly_price_impact_calculation2() -> None:
    # Follow-up from first case from https://docs.gnosis.io/conditionaltokens/docs/introduction3/#an-example-with-cpmm
    kelly = KellyBettingStrategy(max_bet_amount=1, max_price_impact=0.5)
    # after first bet 10 xDAI on Yes, new yes/no
    yes = 5
    no = 20
    bet_amount = 10
    buy_direction = False
    assert_price_impact(bet_amount, buy_direction, yes, no, kelly)


@pytest.mark.parametrize(
    "max_bet_amount, max_price_impact, p_yes", [(2, 0.5, 0.9), (5, 0.7, 0.8)]
)
def test_kelly_price_impact_works_large_pool(
    max_bet_amount: int, max_price_impact: float, p_yes: float
) -> None:
    large_market = OmenSubgraphHandler().get_omen_binary_markets_simple(
        limit=1, filter_by=FilterBy.OPEN, sort_by=SortBy.HIGHEST_LIQUIDITY
    )[0]
    omen_agent_market = OmenAgentMarket.from_data_model(large_market)
    confidence = 1.0
    assert_price_impact_converges(
        omen_agent_market, max_bet_amount, p_yes, confidence, max_price_impact
    )


@pytest.mark.parametrize(
    "max_bet_amount, max_price_impact, p_yes", [(2, 0.5, 0.9), (5, 0.7, 0.8)]
)
def test_kelly_price_impact_works_small_pool(
    max_bet_amount: int, max_price_impact: float, p_yes: float
) -> None:
    large_market = OmenSubgraphHandler().get_omen_binary_markets_simple(
        limit=1, filter_by=FilterBy.OPEN, sort_by=SortBy.LOWEST_LIQUIDITY
    )[0]
    omen_agent_market = OmenAgentMarket.from_data_model(large_market)
    confidence = 1.0
    assert_price_impact_converges(
        omen_agent_market, max_bet_amount, p_yes, confidence, max_price_impact
    )


def assert_price_impact_converges(
    omen_agent_market: OmenAgentMarket,
    max_bet_amount: float,
    p_yes: float,
    confidence: float,
    max_price_impact: float,
) -> None:
    outcome_token_pool = check_not_none(omen_agent_market.outcome_token_pool)
    yes_outcome_pool_size = outcome_token_pool[
        omen_agent_market.get_outcome_str_from_bool(True)
    ]
    no_outcome_pool_size = outcome_token_pool[
        omen_agent_market.get_outcome_str_from_bool(False)
    ]

    kelly_bet = get_kelly_bet_full(
        yes_outcome_pool_size=yes_outcome_pool_size,
        no_outcome_pool_size=no_outcome_pool_size,
        estimated_p_yes=p_yes,
        max_bet=max_bet_amount,
        confidence=confidence,
        fees=omen_agent_market.fees,
    )

    kelly = KellyBettingStrategy(
        max_bet_amount=max_bet_amount, max_price_impact=max_price_impact
    )

    max_price_impact_bet_amount = kelly.calculate_bet_amount_for_price_impact(
        omen_agent_market, kelly_bet
    )
    price_impact = kelly.calculate_price_impact_for_bet_amount(
        kelly_bet.direction,
        bet_amount=max_price_impact_bet_amount,
        yes=yes_outcome_pool_size,
        no=no_outcome_pool_size,
        fees=omen_agent_market.fees,
    )

    # assert convergence
    assert np.isclose(price_impact, max_price_impact, atol=max_price_impact * 0.001)


def assert_price_impact(
    bet_amount: float,
    buy_direction: bool,
    yes: float,
    no: float,
    kelly: KellyBettingStrategy,
) -> None:
    price_impact = kelly.calculate_price_impact_for_bet_amount(
        buy_direction,
        bet_amount=bet_amount,
        yes=yes,
        no=no,
        fees=MarketFees.get_zero_fees(),
    )

    # Calculation is done assuming buy_direction is True. Else, we invert the reserves.
    if not buy_direction:
        yes, no = no, yes

    expected_price_yes = no / (yes + no)
    k = yes * no
    tokens_bought_yes = (yes + bet_amount) - (k / (no + bet_amount))  # 23.333 # x*y = k
    actual_price_yes = bet_amount / tokens_bought_yes
    expected_price_impact = (actual_price_yes - expected_price_yes) / expected_price_yes
    ####

    assert np.isclose(price_impact, expected_price_impact, rtol=0.01)

    print(price_impact)
