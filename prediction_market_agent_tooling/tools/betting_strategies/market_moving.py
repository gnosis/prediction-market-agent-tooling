from functools import reduce

import numpy as np

from prediction_market_agent_tooling.gtypes import Probability, Wei, xDai
from prediction_market_agent_tooling.markets.omen.omen import (
    MarketFees,
    OmenAgentMarket,
)
from prediction_market_agent_tooling.tools.betting_strategies.utils import SimpleBet
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai, xdai_to_wei


def get_market_moving_bet(
    yes_outcome_pool_size: float,
    no_outcome_pool_size: float,
    market_p_yes: float,
    target_p_yes: float,
    fees: MarketFees,
    max_iters: int = 100,
) -> SimpleBet:
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
    fixed_product = yes_outcome_pool_size * no_outcome_pool_size
    bet_direction: bool = target_p_yes > market_p_yes

    min_bet_amount = 0.0
    max_bet_amount = 100 * (
        yes_outcome_pool_size + no_outcome_pool_size
    )  # TODO set a better upper bound

    # Binary search for the optimal bet amount
    for _ in range(max_iters):
        bet_amount = (min_bet_amount + max_bet_amount) / 2
        amounts_diff = fees.get_bet_size_after_fees(bet_amount)

        # Initial new amounts are old amounts + equal new amounts for each outcome
        yes_outcome_new_pool_size = yes_outcome_pool_size + amounts_diff
        no_outcome_new_pool_size = no_outcome_pool_size + amounts_diff
        new_amounts = {
            True: yes_outcome_new_pool_size,
            False: no_outcome_new_pool_size,
        }

        # Now give away tokens at `bet_outcome_index` to restore invariant
        new_product = yes_outcome_new_pool_size * no_outcome_new_pool_size
        dx = (new_product - fixed_product) / new_amounts[not bet_direction]
        new_amounts[bet_direction] -= dx

        # Check that the invariant is restored
        assert np.isclose(
            reduce(lambda x, y: x * y, list(new_amounts.values()), 1.0),
            float(fixed_product),
        )

        new_p_yes = Probability(new_amounts[False] / sum(list(new_amounts.values())))
        if abs(target_p_yes - new_p_yes) < 1e-6:
            break
        elif new_p_yes > target_p_yes:
            if bet_direction:
                max_bet_amount = bet_amount
            else:
                min_bet_amount = bet_amount
        else:
            if bet_direction:
                min_bet_amount = bet_amount
            else:
                max_bet_amount = bet_amount

    return SimpleBet(direction=bet_direction, size=bet_amount)


def _sanity_check_omen_market_moving_bet(
    bet_to_check: SimpleBet, market: OmenAgentMarket, target_p_yes: float
) -> None:
    """
    A util function for checking that a bet moves the market to the target_p_yes
    by calling the market's calcBuyAmount method from the smart contract, and
    using the adjusted outcome pool sizes to calculate the new p_yes.
    """
    buy_amount_ = market.get_contract().calcBuyAmount(
        investment_amount=xdai_to_wei(xDai(bet_to_check.size)),
        outcome_index=market.get_outcome_index(
            market.get_outcome_str_from_bool(bet_to_check.direction)
        ),
    )
    buy_amount = float(wei_to_xdai(Wei(buy_amount_)))

    outcome_token_pool = check_not_none(market.outcome_token_pool)
    yes_outcome_pool_size = outcome_token_pool[market.get_outcome_str_from_bool(True)]
    no_outcome_pool_size = outcome_token_pool[market.get_outcome_str_from_bool(False)]
    market_const = yes_outcome_pool_size * no_outcome_pool_size

    bet_to_check_size_after_fees = market.fees.get_bet_size_after_fees(
        bet_to_check.size
    )

    # When you buy 'yes' tokens, you add your bet size to the both pools, then
    # subtract `buy_amount` from the 'yes' pool. And vice versa for 'no' tokens.
    new_yes_outcome_pool_size = (
        yes_outcome_pool_size
        + bet_to_check_size_after_fees
        - float(bet_to_check.direction) * buy_amount
    )
    new_no_outcome_pool_size = (
        no_outcome_pool_size
        + bet_to_check_size_after_fees
        - float(not bet_to_check.direction) * buy_amount
    )
    new_market_const = new_yes_outcome_pool_size * new_no_outcome_pool_size
    # Check the invariant is restored
    assert np.isclose(new_market_const, market_const)

    # Now check that the market's new p_yes is equal to the target_p_yes
    new_p_yes = new_no_outcome_pool_size / (
        new_yes_outcome_pool_size + new_no_outcome_pool_size
    )
    if not np.isclose(new_p_yes, target_p_yes, atol=0.01):
        raise ValueError(
            f"Bet does not move market to target_p_yes {target_p_yes=}. Got {new_p_yes=}"
        )
