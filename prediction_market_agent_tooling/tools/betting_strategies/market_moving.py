import typing as t
from functools import reduce

import numpy as np

from prediction_market_agent_tooling.gtypes import Probability, wei_type, xDai
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.data_models import OmenMarket
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import (
    ONE_XDAI,
    wei_to_xdai,
    xdai_to_wei,
)

OutcomeIndex = t.Literal[0, 1]


def get_market_moving_bet(
    market: OmenMarket,
    target_p_yes: Probability,
    max_iters: int = 100,
    check_vs_contract: bool = False,  # Disable by default, as it's slow
    verbose: bool = False,
) -> t.Tuple[xDai, OutcomeIndex]:
    """
    Implements a binary search to determine the bet that will move the market's
    `p_yes` to that of the target.

    Consider a binary fixed-product market containing `x` and `y` tokens.
    A trader wishes to aquire `x` tokens by betting an amount `d0`.

    The calculation to determine the number of `x` tokens he acquires, denoted
    by `dx`, is:

    a_x * a_y = fixed_product
    na_x = a_x + d0
    na_y = a_y + d0
    na_x * na_y = new_product
    (na_x - dx) * na_y = fixed_product
    (na_x * na_y) - (dx * na_y) = fixed_product
    new_product - fixed_product = dx * na_y
    dx = (new_product - fixed_product) / na_y
    """
    market_agent = OmenAgentMarket.from_data_model(market)
    amounts = market.outcomeTokenAmounts
    prices = check_not_none(
        market.outcomeTokenProbabilities, "No probabilities, is marked closed?"
    )
    if len(amounts) != 2 or len(prices) != 2:
        raise ValueError("Only binary markets are supported.")

    fixed_product = reduce(lambda x, y: x * y, amounts, 1)
    assert np.isclose(float(sum(prices)), 1)

    # For FPMMs, the probability is equal to the marginal price
    current_p_yes = Probability(prices[0])
    bet_outcome_index: OutcomeIndex = 0 if target_p_yes > current_p_yes else 1

    min_bet_amount = 0
    max_bet_amount = 100 * sum(amounts)  # TODO set a better upper bound

    # Binary search for the optimal bet amount
    for _ in range(max_iters):
        bet_amount = (min_bet_amount + max_bet_amount) // 2
        bet_amount_ = (
            bet_amount
            * (
                xdai_to_wei(ONE_XDAI)
                - check_not_none(market.fee, "No fee for the market.")
            )
            / xdai_to_wei(ONE_XDAI)
        )

        # Initial new amounts are old amounts + equal new amounts for each outcome
        amounts_diff = bet_amount_
        new_amounts = [amounts[i] + amounts_diff for i in range(len(amounts))]

        # Now give away tokens at `bet_outcome_index` to restore invariant
        new_product = reduce(lambda x, y: x * y, new_amounts, 1.0)
        dx = (new_product - fixed_product) / new_amounts[1 - bet_outcome_index]

        # Sanity check the number of tokens against the contract
        if check_vs_contract:
            expected_trade = market_agent.get_contract().calcBuyAmount(
                investment_amount=wei_type(bet_amount),
                outcome_index=bet_outcome_index,
            )
            assert np.isclose(float(expected_trade), dx)

        new_amounts[bet_outcome_index] -= dx
        # Check that the invariant is restored
        assert np.isclose(
            reduce(lambda x, y: x * y, new_amounts, 1.0), float(fixed_product)
        )
        new_p_yes = Probability(new_amounts[1] / sum(new_amounts))
        bet_amount_wei = wei_type(bet_amount)
        if verbose:
            outcome = market_agent.get_outcome_str(bet_outcome_index)
            logger.debug(
                f"Target p_yes: {target_p_yes:.2f}, bet: {wei_to_xdai(bet_amount_wei):.2f}{market_agent.currency} for {outcome}, new p_yes: {new_p_yes:.2f}"
            )
        if abs(target_p_yes - new_p_yes) < 0.01:
            break
        elif new_p_yes > target_p_yes:
            if bet_outcome_index == 0:
                max_bet_amount = bet_amount
            else:
                min_bet_amount = bet_amount
        else:
            if bet_outcome_index == 0:
                min_bet_amount = bet_amount
            else:
                max_bet_amount = bet_amount
    return wei_to_xdai(bet_amount_wei), bet_outcome_index
