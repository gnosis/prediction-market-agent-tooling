from itertools import product

import pytest

from prediction_market_agent_tooling.deploy.betting_strategy import BettingStrategy
from prediction_market_agent_tooling.gtypes import USD
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    MarketType,
    SortBy,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket


@pytest.mark.parametrize(
    "bet_amount, market_class, sort_by",
    list(
        product(
            [USD(1), USD(10), USD(100)],
            [OmenAgentMarket],
            [SortBy.CLOSING_SOONEST, SortBy.LOWEST_LIQUIDITY, SortBy.HIGHEST_LIQUIDITY],
        )
    ),
)
def test_on_real_markets(
    bet_amount: USD,
    market_class: type[AgentMarket],
    sort_by: SortBy,
) -> None:
    checked_count = 0  # CoW/pools APIs are flaky, but require at least one sucesful checks across markets and outcomes here.
    markets = market_class.get_markets(
        limit=5, sort_by=sort_by, market_types=[MarketType.CATEGORICAL]
    )

    for market in markets:
        for outcome in market.outcomes:
            actual_bet_amount = BettingStrategy.cap_to_profitable_bet_amount(
                market, bet_amount, outcome
            )
            if actual_bet_amount == 0:
                # This is a valid state that prevents losing money, so store it as checked.
                checked_count += 1
                logger.warning(f"Can not bet anything on {outcome=} at {market.url=}.")
                continue

            buy_token_amount = market.get_buy_token_amount(actual_bet_amount, outcome)
            if buy_token_amount is None:
                # This means we can not actually verify the capped value, so just skip.
                logger.warning(
                    f"Can not get buy_token_amount for {outcome=} at {market.url}"
                )
                continue

            potential_usd_value = market.get_in_usd(buy_token_amount.as_token)
            assert (
                potential_usd_value > actual_bet_amount
            ), f"Doesn't hold for {market_class}, {sort_by}."
            # Increase checked count, as all went fine.
            checked_count += 1

    assert checked_count > 0, "At least some markets should have been checked."
